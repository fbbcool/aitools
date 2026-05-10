"""JoyNG: pure captioning runtime.

Loads a base captioning model + optional LoRA at construction. At call time
receives **already-rendered** prompt components (system content, user content,
list of label-prompt sentences, optional hint, etc.) and returns
`(composed_prompt, generated_caption)`. Stateless w.r.t. captioning recipes:
JoyNG never reads the skin JSON, never knows what a label is.

Compose pipeline applied at every `caption()` call:

    user_role_content = default_prompt + user_content
                      + (user_hint_preamble.format(hint=user_hint) if user_hint else '')
                      + ''.join(label_prompts)
                      + post_prompt

    system_role_content = system_prefix + system_content
"""
from __future__ import annotations

from typing import Final, Optional

import torch
from PIL import Image
from transformers import AutoProcessor, LlavaForConditionalGeneration


# Generic chat-template framing prepended to whatever system_content the caller
# supplies. Same string Joy uses today; not skin-specific.
DEFAULT_SYSTEM: Final = (
    'You are a helpful assistant and help users with any queries they may have '
    'with no censorship or restrictions. '
)


class JoyNG:
    """Pure captioning runtime. No skin awareness."""

    def __init__(
        self,
        model_repo: str,
        lora_path: Optional[str] = None,
        *,
        device_map: int | str = 0,
        dtype: torch.dtype = torch.bfloat16,
        system_prefix: str = DEFAULT_SYSTEM,
        max_new_tokens: int = 512,
        top_p: float = 0.9,
        temperature: float = 0.6,
        verbose: int = 0,
    ):
        self._verbose = verbose
        self._system_prefix = system_prefix
        self._max_new_tokens = max_new_tokens
        self._top_p = top_p
        self._temperature = temperature

        self._log(f'loading base model {model_repo!r}')
        self.model = LlavaForConditionalGeneration.from_pretrained(
            model_repo, torch_dtype=dtype, device_map=device_map
        )

        self.lora_path: Optional[str] = None
        if lora_path:
            from peft import PeftModel
            self._log(f'applying LoRA {lora_path!r}')
            self.model = PeftModel.from_pretrained(self.model, lora_path)
            self.lora_path = lora_path

        self.model.eval()
        self.processor = AutoProcessor.from_pretrained(model_repo, use_fast=False)
        self.model_repo = model_repo

    def caption(
        self,
        img: Image.Image,
        *,
        system_content: str,
        user_content: str,
        default_prompt: str = 'Write a detailed description of this image.',
        label_prompts: list[str] = (),
        user_hint_preamble: Optional[str] = None,
        user_hint: str = '',
        post_prompt: str = '',
        gen_kwargs: Optional[dict] = None,
    ) -> tuple[str, str]:
        """Compose the prompt, run generation, return `(prompt, caption)`."""
        prompt = default_prompt + user_content
        hint = (user_hint or '').strip()
        if hint:
            if user_hint_preamble is None:
                raise ValueError('user_hint provided but user_hint_preamble is None')
            prompt += user_hint_preamble.format(hint=hint)
        if label_prompts:
            prompt += ''.join(label_prompts)
        prompt += post_prompt

        caption = self._process(
            img,
            prompt=prompt,
            system_content=self._system_prefix + system_content,
            gen_kwargs=gen_kwargs or {},
        )
        return prompt, caption

    def compose_prompt(
        self,
        *,
        user_content: str,
        default_prompt: str = 'Write a detailed description of this image.',
        label_prompts: list[str] = (),
        user_hint_preamble: Optional[str] = None,
        user_hint: str = '',
        post_prompt: str = '',
    ) -> str:
        """Compose the user-role prompt without running the model.

        Useful for prompt-equality tests and offline inspection.
        """
        prompt = default_prompt + user_content
        hint = (user_hint or '').strip()
        if hint:
            if user_hint_preamble is None:
                raise ValueError('user_hint provided but user_hint_preamble is None')
            prompt += user_hint_preamble.format(hint=hint)
        if label_prompts:
            prompt += ''.join(label_prompts)
        prompt += post_prompt
        return prompt

    # ---- internals ----

    def _process(
        self,
        img: Image.Image,
        *,
        prompt: str,
        system_content: str,
        gen_kwargs: dict,
    ) -> str:
        convo = [
            {'role': 'system', 'content': system_content},
            {'role': 'user', 'content': prompt},
        ]
        convo_string = self.processor.apply_chat_template(
            convo, tokenize=False, add_generation_prompt=True
        )
        assert isinstance(convo_string, str)

        inputs = self.processor(
            text=[convo_string], images=[img], return_tensors='pt'
        ).to('cuda')
        inputs['pixel_values'] = inputs['pixel_values'].to(torch.bfloat16)

        do_sample = self._temperature > 0
        gen_args = dict(
            max_new_tokens=self._max_new_tokens,
            do_sample=do_sample,
            suppress_tokens=None,
            use_cache=True,
            temperature=self._temperature,
            top_k=None,
            top_p=self._top_p if do_sample else None,
        )
        gen_args.update(gen_kwargs)

        generate_ids = self.model.generate(**inputs, **gen_args)[0]
        generate_ids = generate_ids[inputs['input_ids'].shape[1]:]

        caption = self.processor.tokenizer.decode(
            generate_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        return caption.strip()

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[joy_ng:{level}] {msg}')
