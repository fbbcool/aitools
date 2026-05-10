"""JoySceneDBNG: orchestrator that wires `Skin` to `JoyNG` and the SceneDB.

At construction: resolve a skin by name from `SkinRegistry`, look up the
base-model and (optional) LoRA paths via `AInstallerDB`, and lazily build a
`JoyNG` runtime against them. At call time: pull labels and hint from the
SceneImage, ask the skin to render label-prompt sentences, call `JoyNG`, and
run the skin's post-caption validators (forbidden / body-type / trigger
presence) as logged warnings.
"""
from __future__ import annotations

from typing import Final, Optional, Union, cast

from aidb import SceneDef, SceneConfig, SceneManager, SceneImageManager, SceneImage, Scene
from ait.install import AInstallerDB
from ait.tools.scenes import scene_id_from_url

from .joy_ng import JoyNG
from .skin import Skin, SkinRegistry


class JoySceneDBNG:
    SKIN_DEFAULT: Final = '1xlasm'

    def __init__(
        self,
        config: SceneConfig,
        skin: Union[str, Skin] = '',
        *,
        verbose: int = 0,
        force: bool = False,
        lora: bool = True,
    ):
        self._dbconfig: SceneConfig = config
        self._verbose = verbose
        self._force = force
        self._use_lora = lora

        self._scm: SceneManager = SceneManager(config=self._dbconfig, verbose=self._verbose)
        self._sim: SceneImageManager = self._scm.scene_image_manager()

        if not skin:
            skin = self.SKIN_DEFAULT
            self._log(f'skin not set, using default [{skin}].')
        self.skin: Skin = (
            skin if isinstance(skin, Skin)
            else SkinRegistry(log=lambda m: self._log(m, 'warn')).get(skin)
        )

        self.__joy: Optional[JoyNG] = None

    @property
    def _joy(self) -> JoyNG:
        if self.__joy is None:
            base_ids = AInstallerDB().repo_ids(*self.skin.model_key)
            if not base_ids:
                raise IndexError(
                    f'AInstallerDB: no model configured for {self.skin.model_key}'
                )
            base_repo = base_ids[0]
            lora_path: Optional[str] = None
            if self._use_lora and self.skin.lora_key is not None:
                lora_ids = AInstallerDB().repo_ids(*self.skin.lora_key)
                if lora_ids:
                    lora_path = lora_ids[0]
                    self._log(f'applying LoRA: {lora_path}')
            self.__joy = JoyNG(
                model_repo=base_repo,
                lora_path=lora_path,
                verbose=self._verbose,
            )
        return self.__joy

    # ---- public API ----

    def caption_image(
        self, image_id: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Caption a single SceneImage. Returns (prompt, caption) or (None, None).

        Mirrors `JoySceneDB._id_caption` semantics:
        - skips if SceneImage already has caption_joy and `force=False`,
        - prefers per-image labels; falls back to scene-level labels,
        - forwards user hint verbatim,
        - runs post-caption validators as logged warnings.
        """
        try:
            simg = cast(SceneImage, self._sim.img_from_id(image_id))
        except Exception as e:
            self._log(f'id [{image_id}]: {e}', 'warn')
            return None, None

        img = simg.pil
        if img is None:
            return None, None

        caption_joy_current = simg.data.get(SceneDef.FIELD_CAPTION_JOY, None)
        if (caption_joy_current is not None) and (not self._force):
            return None, None

        url = simg.url_from_data
        if url is None:
            return None, None

        labels = self._collect_labels(simg, url)
        hint = simg.data.get(SceneDef.FIELD_HINTS, '') or ''
        if hint:
            self._log(f'id [{image_id}]: using image hints [{hint}].')

        prompt, caption = self._joy.caption(
            img=img,
            system_content=self.skin.directive,
            user_content=self.skin.directive,
            default_prompt=self.skin.default_prompt,
            label_prompts=self.skin.render_label_prompts(labels),
            user_hint_preamble=self.skin.user_hint_preamble,
            user_hint=hint,
            post_prompt=self.skin.post_prompt,
        )
        self._log(f'prompt[{prompt}] caption[{caption}]')

        for v in self.skin.caption_violations(caption):
            self._log(f'forbidden: {v!r}', 'warn')
        for w in self.skin.body_type_warnings(caption, labels):
            self._log(w, 'warn')
        for m in self.skin.missing_triggers(caption):
            self._log(f'missing trigger phrase: {m!r}', 'warn')

        return prompt, caption

    def caption_images(self, image_ids: list[str]) -> dict[str, dict[str, str]]:
        """Batch helper: returns {image_id: {prompt, caption}} for every
        successfully captioned image. Mirrors `JoySceneDB._ids_caption`.
        """
        ret: dict[str, dict[str, str]] = {}
        for iid in image_ids:
            prompt, caption = self.caption_image(iid)
            if caption is None:
                continue
            ret[iid] = {
                SceneDef.FIELD_PROMPT: prompt or '',
                SceneDef.FIELD_CAPTION: caption,
            }
        return ret

    # ---- internals ----

    def _collect_labels(self, simg: SceneImage, url) -> list[str]:
        """Prefer the image's own labels; fall back to the scene's labels when
        the image carries none. Same precedence as `JoySceneDB._id_caption`.
        """
        labels = simg.data.get(SceneDef.FIELD_LABELS, []) or []
        if labels:
            self._log(f'id [{simg.id}]: using image labels {labels}.')
            return labels
        id_scene = scene_id_from_url(url)
        if id_scene is None:
            return []
        try:
            scene: Scene = self._scm.scene_from_id_or_url(id_scene)
        except Exception:
            return []
        labels = scene.data.get(SceneDef.FIELD_LABELS, []) or []
        if labels:
            self._log(f'id [{simg.id}]: no image labels, falling back to scene labels {labels}.')
        return labels

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[JoySceneDBNG:{level}] {msg}')
