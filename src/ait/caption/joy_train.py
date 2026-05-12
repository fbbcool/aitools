"""
JoyCaption LoRA fine-tuning on a SceneSet of done images.

Trains a PEFT/LoRA adapter on the language-model linear layers of the
JoyCaption Llava base. Each training example is the curator's stored
`caption_prompt` (built by `/imgs_caption_prompt` upstream) conditioned
on the image, with the curator-edited `caption` field as the target.

By training on the same `caption_prompt` that inference forwards to the
captioner, train and inference share the user-role prompt distribution
— no train/inference mismatch.

Reads images directly from the prod (or test) Mongo via SceneImageManager
- no HF hub round-trip. Run on a box that can reach prod Mongo and the
image filesystem.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from PIL import Image
from torch.utils.data import Dataset
from transformers import (
    AutoProcessor,
    LlavaForConditionalGeneration,
    Trainer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model

from aidb import SceneConfig, SceneDef, SceneManager, SceneSetManager
from ait.install import AInstallerDB
from ait.caption.skin import SkinRegistry


# ---------------------------------------------------------------------------
# Dataset: lazy-loads PIL images from prod Mongo on __getitem__
# ---------------------------------------------------------------------------


@dataclass
class JoyTrainSample:
    img: Image.Image
    caption_prompt: str       # conditioning text (user role)
    caption: str              # target text (assistant role)


class JoyDoneDataset(Dataset):
    """
    Iterates active images of a SceneSet that have both `caption_prompt`
    and `caption` populated. `caption_prompt` is the curator-finalized
    prompt (judgment-mode or deterministic) that `/imgs_caption_joy`
    forwards to the captioner at inference; `caption` is the
    curator-edited target text.

    `labels`, `hints`, and `caption_joy` are upstream that *produced* these
    two fields and are not used by training directly.
    """

    def __init__(
        self,
        set_name: str,
        config: SceneConfig = 'prod',
        verbose: int = 0,
    ) -> None:
        self._items: list[dict] = []

        ssm = SceneSetManager(config=config, verbose=verbose)
        scene_set = ssm.set_from_id_or_name(set_name)
        if scene_set is None:
            raise ValueError(f'set [{set_name}] not found')

        for img in scene_set.imgs:
            if img.prototype:
                continue
            d = img.data
            caption = (d.get(SceneDef.FIELD_CAPTION) or '').strip()
            caption_prompt = (d.get(SceneDef.FIELD_CAPTION_PROMPT) or '').strip()
            if not (caption and caption_prompt):
                continue
            self._items.append(
                {
                    'id': img.id,
                    'caption_prompt': caption_prompt,
                    'caption': caption,
                }
            )

        self._sim = SceneManager(config=config, verbose=verbose).scene_image_manager()

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, idx: int) -> JoyTrainSample:
        item = self._items[idx]
        simg = self._sim.img_from_id(item['id'])
        if simg is None:
            raise RuntimeError(f'image gone: {item["id"]}')
        pil = simg.pil
        if pil is None:
            raise RuntimeError(f'pil load failed: {item["id"]}')
        return JoyTrainSample(
            img=pil,
            caption_prompt=item['caption_prompt'],
            caption=item['caption'],
        )


# ---------------------------------------------------------------------------
# Collator: image-aware tokenization with prompt-portion masking
# ---------------------------------------------------------------------------


@dataclass
class JoyCollator:
    processor: Any
    system_content: str            # = skin.directive (constant across batch)
    max_length: int = 4096

    def __call__(self, features: list[JoyTrainSample]) -> dict[str, torch.Tensor]:
        pad_id = self.processor.tokenizer.pad_token_id
        if pad_id is None:
            pad_id = self.processor.tokenizer.eos_token_id

        eos_token = self.processor.tokenizer.eos_token or ''

        batch_input_ids: list[torch.Tensor] = []
        batch_labels: list[torch.Tensor] = []
        batch_attn: list[torch.Tensor] = []
        batch_pixels: list[torch.Tensor] = []

        for s in features:
            convo = [
                {'role': 'system', 'content': self.system_content},
                {'role': 'user', 'content': s.caption_prompt},
            ]

            prompt_str = self.processor.apply_chat_template(
                convo, tokenize=False, add_generation_prompt=True
            )
            full_str = prompt_str + s.caption + eos_token

            full = self.processor(
                text=[full_str], images=[s.img], return_tensors='pt'
            )
            # Re-tokenize prompt-only with the same image so the image-token
            # expansion is identical and prompt_len is the correct mask
            # boundary into the full sequence.
            prompt_only = self.processor(
                text=[prompt_str], images=[s.img], return_tensors='pt'
            )

            input_ids = full['input_ids'][0]
            attn = full['attention_mask'][0]
            pixel_values = full['pixel_values'][0].to(torch.bfloat16)
            prompt_len = prompt_only['input_ids'].shape[1]

            labels = input_ids.clone()
            labels[:prompt_len] = -100

            # Image tokens span ~hundreds of positions inside input_ids;
            # naive tail truncation would remove image-token slots and break
            # the vision-feature/placeholder count match. Fail loud instead.
            if input_ids.shape[0] > self.max_length:
                raise RuntimeError(
                    f'sample exceeds max_length={self.max_length} '
                    f'(got {input_ids.shape[0]}); raise max_length or shorten the prompt'
                )

            batch_input_ids.append(input_ids)
            batch_labels.append(labels)
            batch_attn.append(attn)
            batch_pixels.append(pixel_values)

        max_len = max(x.shape[0] for x in batch_input_ids)

        def _pad(x: torch.Tensor, pad_value: int) -> torch.Tensor:
            if x.shape[0] == max_len:
                return x
            tail = torch.full((max_len - x.shape[0],), pad_value, dtype=x.dtype)
            return torch.cat([x, tail], dim=0)

        return {
            'input_ids': torch.stack([_pad(x, pad_id) for x in batch_input_ids]),
            'attention_mask': torch.stack([_pad(x, 0) for x in batch_attn]),
            'labels': torch.stack([_pad(x, -100) for x in batch_labels]),
            'pixel_values': torch.stack(batch_pixels),
        }


# ---------------------------------------------------------------------------
# LoRA targeting: only language-model Linears, never the vision tower
# ---------------------------------------------------------------------------


def _collect_lm_lora_target_modules(model: torch.nn.Module) -> list[str]:
    leaf_targets = {
        'q_proj', 'k_proj', 'v_proj', 'o_proj',
        'gate_proj', 'up_proj', 'down_proj',
    }
    names: list[str] = []
    for name, module in model.named_modules():
        if not isinstance(module, torch.nn.Linear):
            continue
        if 'language_model' not in name:
            continue
        if name.rsplit('.', 1)[-1] in leaf_targets:
            names.append(name)
    return names


def _freeze_vision_tower(model: torch.nn.Module) -> None:
    for attr in ('vision_tower', 'vision_model'):
        vt = getattr(model, attr, None)
        if vt is None:
            continue
        for p in vt.parameters():
            p.requires_grad = False
        return


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def train(
    set_name: str = 'gts_v3',
    config: SceneConfig = 'prod',
    skin_name: str = '1xlasm',
    output_dir: Path | str = Path('./out_joy_lora'),
    epochs: int = 4,
    learning_rate: float = 1e-4,
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
    grad_accum: int = 8,
    max_length: int = 4096,
    seed: int = 42,
    verbose: int = 1,
) -> None:
    torch.manual_seed(seed)
    output_dir = Path(output_dir)

    skin = SkinRegistry().get(skin_name)
    if verbose:
        print(f'[joy_train] skin: {skin_name}  directive: {len(skin.directive)} chars')

    repo_id = AInstallerDB().repo_ids(group='capjoy', variant='common', target='model')[0]
    if verbose:
        print(f'[joy_train] base model: {repo_id}')

    processor = AutoProcessor.from_pretrained(repo_id, use_fast=False)
    # Right-pad for causal LM training.
    processor.tokenizer.padding_side = 'right'

    model = LlavaForConditionalGeneration.from_pretrained(
        repo_id, torch_dtype=torch.bfloat16, device_map={'': 0}
    )
    _freeze_vision_tower(model)

    target_modules = _collect_lm_lora_target_modules(model)
    if not target_modules:
        raise RuntimeError('LoRA: no target modules found in language_model')
    if verbose:
        print(f'[joy_train] LoRA targets: {len(target_modules)} modules')

    lora_cfg = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        bias='none',
        task_type='CAUSAL_LM',
        target_modules=target_modules,
    )
    model = get_peft_model(model, lora_cfg)
    # Allow gradients to flow through the (frozen) input embedding when
    # gradient checkpointing is on.
    if hasattr(model, 'enable_input_require_grads'):
        model.enable_input_require_grads()
    if verbose:
        model.print_trainable_parameters()

    dataset = JoyDoneDataset(
        set_name=set_name, config=config, verbose=verbose
    )
    if len(dataset) == 0:
        raise RuntimeError(f'no trainable images in set [{set_name}] '
                           f'(need caption_prompt + caption both non-empty)')
    if verbose:
        print(f'[joy_train] dataset: {len(dataset)} trainable images')

    collator = JoyCollator(
        processor=processor,
        system_content=skin.directive,
        max_length=max_length,
    )

    args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=grad_accum,
        learning_rate=learning_rate,
        bf16=True,
        logging_steps=5,
        save_strategy='epoch',
        save_total_limit=2,
        remove_unused_columns=False,
        gradient_checkpointing=True,
        report_to=[],
        seed=seed,
        dataloader_num_workers=0,
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=dataset,
        data_collator=collator,
    )
    trainer.train()

    output_dir.mkdir(parents=True, exist_ok=True)
    adapter_dir = output_dir / 'adapter'
    model.save_pretrained(str(adapter_dir))
    processor.save_pretrained(str(adapter_dir))
    if verbose:
        print(f'[joy_train] saved adapter to {adapter_dir}')
