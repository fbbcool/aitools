"""JoyCaption LoRA fine-tuning for the HINT-generation task.

Companion to `joy_train.py`. The existing module trains on the full caption
target with labels+hint as input — this one trains on the **hint** target
with just an iter-5-style probe as input (no labels, no hint in user
content). The goal is to teach the model to emit curator-style terse
hints (22-95 chars, "she holds him by his chest" form) directly from an
image + a generic probing question.

Why this exists: prompt-engineering on the existing `joy-gts-lora`
plateaued at hint jaccard ~0.10 (target 0.60) — the captioning-trained
LoRA's response distribution doesn't include the curator's terse-hint
style. This LoRA targets that gap directly.

CLI: edit `script/joy_train_hint_prepare.py` and run it.
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

from aidb import SceneConfig, SceneDef, SceneManager
from aidb.scene.scene_set_manager import SceneSetManager
from ait.caption.skin import SkinRegistry
from ait.install import AInstallerDB


# ---------------------------------------------------------------------------
# Hint-task prompt (mirrors iter-5 of /suggest_image)
# ---------------------------------------------------------------------------

# Matches §3.5 of `conf/skins/1xlasm_suggestions.md`. The probe is the
# fixed input the model learns to map to the curator hint.
HINT_PROBE_PROMPT = (
    "In ONE OR TWO SHORT SENTENCES (max 100 chars each), describe ONLY the "
    "central interaction. Subject = 'she' or 'he' (lowercase). Use specific "
    "verbs (holds, strokes, inserts, wraps around). Mention specific body "
    "parts. NO setting, NO clothing, NO lighting, NO hair, NO appearance. "
    "Example style: 'she holds him by his chest. he is laid back between "
    "her thighs.'"
)


def _build_convo(directive: str, probe: str) -> list[dict]:
    """System role = skin.directive (trigger-phrase compliance). User role
    = probe (no labels, no hint as input — that's the differentiator vs
    `joy_train.py`)."""
    return [
        {'role': 'system', 'content': directive},
        {'role': 'user', 'content': probe},
    ]


# ---------------------------------------------------------------------------
# Dataset: hint-only filter (non-prototype + non-empty hint)
# ---------------------------------------------------------------------------

@dataclass
class HintTrainSample:
    img: Image.Image
    hint: str       # curator's hints field — the training target


class HintDataset(Dataset):
    """Iterates SceneImages in a set whose `hints` field is non-empty and
    not the `none` sentinel. Independent of the `caption`/`caption_joy`/
    `labels` fields — only the hint matters for this task.
    """

    def __init__(
        self,
        set_name: str,
        config: SceneConfig = 'prod',
        min_hint_chars: int = 10,
        verbose: int = 0,
    ) -> None:
        self._items: list[dict] = []

        scm = SceneManager(config=config, verbose=verbose)
        ssm = SceneSetManager(scm._dbc, scm, verbose=verbose)
        scene_set = ssm.set_from_id_or_name(set_name)
        if scene_set is None:
            raise ValueError(f'set [{set_name}] not found')

        for img in scene_set.imgs:
            if img.prototype:
                continue
            hint = (img.data.get(SceneDef.FIELD_HINTS) or '').strip()
            if not hint:
                continue
            if hint.lower() == 'none':
                continue
            if len(hint) < min_hint_chars:
                # Skip very-short fragments (e.g. "step.") that don't
                # represent the curator style we want to learn.
                continue
            self._items.append({'id': img.id, 'hint': hint})

        self._sim = scm.scene_image_manager()
        if verbose:
            print(f'[joy_train_hint] dataset: {len(self._items)} pairs')

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, idx: int) -> HintTrainSample:
        item = self._items[idx]
        simg = self._sim.img_from_id(item['id'])
        if simg is None:
            raise RuntimeError(f'image gone: {item["id"]}')
        pil = simg.pil
        if pil is None:
            raise RuntimeError(f'pil load failed: {item["id"]}')
        return HintTrainSample(img=pil, hint=item['hint'])


# ---------------------------------------------------------------------------
# Collator: tokenize prompt + target, mask prompt portion in labels
# ---------------------------------------------------------------------------

@dataclass
class HintCollator:
    processor: Any
    directive: str
    max_length: int = 4096

    def __call__(self, features: list[HintTrainSample]) -> dict[str, torch.Tensor]:
        pad_id = self.processor.tokenizer.pad_token_id
        if pad_id is None:
            pad_id = self.processor.tokenizer.eos_token_id
        eos_token = self.processor.tokenizer.eos_token or ''

        batch_input_ids: list[torch.Tensor] = []
        batch_labels: list[torch.Tensor] = []
        batch_attn: list[torch.Tensor] = []
        batch_pixels: list[torch.Tensor] = []

        for s in features:
            convo = _build_convo(self.directive, HINT_PROBE_PROMPT)
            prompt_str = self.processor.apply_chat_template(
                convo, tokenize=False, add_generation_prompt=True
            )
            full_str = prompt_str + s.hint + eos_token

            full = self.processor(text=[full_str], images=[s.img], return_tensors='pt')
            prompt_only = self.processor(
                text=[prompt_str], images=[s.img], return_tensors='pt'
            )

            input_ids = full['input_ids'][0]
            attn = full['attention_mask'][0]
            pixel_values = full['pixel_values'][0].to(torch.bfloat16)
            prompt_len = prompt_only['input_ids'].shape[1]

            labels = input_ids.clone()
            labels[:prompt_len] = -100

            if input_ids.shape[0] > self.max_length:
                raise RuntimeError(
                    f'sample exceeds max_length={self.max_length} '
                    f'(got {input_ids.shape[0]}); raise max_length'
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
# LoRA targeting (same as joy_train.py — only language-model linears)
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

def train_hint(
    set_name: str = 'gts_v3',
    config: SceneConfig = 'prod',
    skin_name: str = '1xlasm',
    output_dir: Path | str = Path('./out_joy_hint_lora'),
    epochs: int = 4,
    learning_rate: float = 1e-4,
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
    grad_accum: int = 8,
    max_length: int = 4096,
    min_hint_chars: int = 10,
    seed: int = 42,
    verbose: int = 1,
) -> None:
    torch.manual_seed(seed)
    output_dir = Path(output_dir)

    repo_id = AInstallerDB().repo_ids(group='capjoy', variant='common', target='model')[0]
    if verbose:
        print(f'[joy_train_hint] base model: {repo_id}')
        print(f'[joy_train_hint] skin:       {skin_name}')

    skin = SkinRegistry().get(skin_name)
    if verbose:
        print(f'[joy_train_hint] directive:  {len(skin.directive)} chars')
        print(f'[joy_train_hint] probe:      {HINT_PROBE_PROMPT[:80]}...')

    processor = AutoProcessor.from_pretrained(repo_id, use_fast=False)
    processor.tokenizer.padding_side = 'right'

    model = LlavaForConditionalGeneration.from_pretrained(
        repo_id, torch_dtype=torch.bfloat16, device_map={'': 0}
    )
    _freeze_vision_tower(model)

    target_modules = _collect_lm_lora_target_modules(model)
    if not target_modules:
        raise RuntimeError('LoRA: no target modules found in language_model')
    if verbose:
        print(f'[joy_train_hint] LoRA targets: {len(target_modules)} modules')

    lora_cfg = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        bias='none',
        task_type='CAUSAL_LM',
        target_modules=target_modules,
    )
    model = get_peft_model(model, lora_cfg)
    if hasattr(model, 'enable_input_require_grads'):
        model.enable_input_require_grads()
    if verbose:
        model.print_trainable_parameters()

    dataset = HintDataset(
        set_name=set_name,
        config=config,
        min_hint_chars=min_hint_chars,
        verbose=verbose,
    )
    if len(dataset) == 0:
        raise RuntimeError(f'no hint pairs in set [{set_name}]')

    collator = HintCollator(
        processor=processor,
        directive=skin.directive,
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
        print(f'[joy_train_hint] saved adapter to {adapter_dir}')
