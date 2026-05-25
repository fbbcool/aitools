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

    @classmethod
    def from_skin(cls, skin, *, use_lora: bool = True, verbose: int = 0) -> 'JoyNG':
        """Construct a `JoyNG` configured per a `Skin`'s model + LoRA refs.

        Resolves `skin.model_key` and `skin.lora_key` through `AInstallerDB`,
        attaches `skin.lora_hint_path` as the `'hint'` adapter when set.
        This is the canonical way to bring up a captioner from a skin;
        the joy_server uses it directly, and `JoySceneDBNG` no longer
        constructs its own JoyNG (it routes through the server instead).
        """
        from ait.install import AInstallerDB

        base_ids = AInstallerDB().repo_ids(*skin.model_key)
        if not base_ids:
            raise IndexError(
                f'AInstallerDB: no model configured for {skin.model_key}'
            )
        base_repo = base_ids[0]
        lora_path = None
        if use_lora and skin.lora_key is not None:
            lora_ids = AInstallerDB().repo_ids(*skin.lora_key)
            if lora_ids:
                lora_path = lora_ids[0]
        extra_adapters: dict[str, str] = {}
        if use_lora and skin.lora_hint_path:
            extra_adapters['hint'] = skin.lora_hint_path
        return cls(
            model_repo=base_repo,
            lora_path=lora_path,
            extra_adapters=extra_adapters or None,
            verbose=verbose,
        )

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
        extra_adapters: Optional[dict[str, str]] = None,
        verbose: int = 0,
    ):
        """`extra_adapters` is a `{name: path}` map of additional LoRA
        adapters to load alongside the main `lora_path`. The main adapter
        is registered as `'default'` (PEFT convention); switching to an
        extra one at call time uses `caption(..., adapter=name)`.

        Multi-adapter is currently used to route /img_suggest's iter-5
        through the hint-specific LoRA while iters 1-4 + all of
        /img_caption use the captioning LoRA.
        """
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
        # adapter_name → path (for inspection / debugging).
        self.adapters: dict[str, str] = {}
        self._default_adapter = 'default'
        # HF auth for downloading LoRA adapters from private repos. Prefer
        # HF_TOKEN_RW (a write-scoped token can read private repos owned by
        # the same account), fall back to HF_TOKEN, then None (no auth →
        # works for public repos only).
        import os as _os
        hf_token = _os.environ.get('HF_TOKEN_RW') or _os.environ.get('HF_TOKEN') or None
        if lora_path:
            from peft import PeftModel
            self._log(f'applying LoRA (adapter=default) {lora_path!r}')
            self.model = PeftModel.from_pretrained(
                self.model, lora_path, adapter_name='default', token=hf_token,
            )
            self.lora_path = lora_path
            self.adapters['default'] = lora_path
            if extra_adapters:
                for name, path in extra_adapters.items():
                    if name == 'default':
                        raise ValueError(
                            "extra_adapter name 'default' collides with the main lora_path"
                        )
                    self._log(f'loading extra adapter {name!r} from {path!r}')
                    self.model.load_adapter(path, adapter_name=name, token=hf_token)
                    self.adapters[name] = path
            # ensure default is active after all loads
            self.model.set_adapter('default')

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
        adapter: str = 'default',
    ) -> tuple[str, str]:
        """Compose the prompt, run generation, return `(prompt, caption)`.

        `adapter` selects which PEFT adapter is active for this call. The
        main `lora_path` is registered as `'default'`. Extra adapters
        passed to `__init__(extra_adapters={...})` can be selected by
        their name. The adapter is restored to `'default'` after the call
        so concurrent callers in the same process don't see leftover state.
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

        # Adapter switch (no-op when single-adapter or adapter='default')
        active_adapter = self._set_adapter(adapter)
        try:
            caption = self._process(
                img,
                prompt=prompt,
                system_content=self._system_prefix + system_content,
                gen_kwargs=gen_kwargs or {},
            )
        finally:
            # Restore the default to keep behaviour deterministic for next caller.
            if active_adapter != self._default_adapter:
                self._set_adapter(self._default_adapter)
        return prompt, caption

    def _set_adapter(self, adapter: str) -> str:
        """Switch the active LoRA adapter. Returns the name set.
        No-op when no adapters are loaded. Raises on unknown name."""
        if not self.adapters:
            # Single-LoRA or no-LoRA mode; nothing to switch.
            return adapter
        if adapter not in self.adapters:
            raise ValueError(
                f'unknown adapter {adapter!r}; available: {sorted(self.adapters)}'
            )
        self.model.set_adapter(adapter)
        return adapter

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
