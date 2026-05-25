"""JoySceneDB: enrichment layer over a running joy_server.

At construction: resolve a skin by name from `SkinRegistry` and ensure
the persistent `joy_server` is running with that skin (spawning it on
demand via `joy_client.ensure_running`). At call time: pull labels and
hint from the SceneImage, ask the skin to render label-prompt
sentences, route the caption call through `joy_client.caption` to the
running Joy instance, and run the skin's post-caption validators
(forbidden / body-type / trigger presence) as logged warnings.

JoySceneDB NEVER loads model weights itself. The captioner lives in
the joy_server process; this class is a thin enrichment + persistence
client.
"""
from __future__ import annotations

from typing import Final, Optional, Union, cast

from aidb import SceneDef, SceneConfig, SceneManager, SceneImageManager, SceneImage, Scene
from ait.tools.scenes import scene_id_from_url

import time

from . import caption_log, joy_client
from .skin import Skin, SkinRegistry, compute_labels_ng


class JoySceneDB:
    SKIN_DEFAULT: Final = '1xlasm'

    def __init__(
        self,
        config: SceneConfig,
        skin: Union[str, Skin] = '',
        *,
        verbose: int = 0,
        force: bool = False,
    ):
        self._dbconfig: SceneConfig = config
        self._verbose = verbose
        self._force = force

        self._scm: SceneManager = SceneManager(config=self._dbconfig, verbose=self._verbose)
        self._sim: SceneImageManager = self._scm.scene_image_manager()

        if not skin:
            skin = self.SKIN_DEFAULT
            self._log(f'skin not set, using default [{skin}].')
        self.skin: Skin = (
            skin if isinstance(skin, Skin)
            else SkinRegistry(log=lambda m: self._log(m, 'warn')).get(skin)
        )

        # Bring up the persistent joy_server with this skin (no-op if
        # already running with the same skin; auto-restart on mismatch).
        joy_client.ensure_running(skin=self.skin.name)

    # ---- public API ----

    def caption_image(
        self, image_id: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Caption a single SceneImage. Returns (prompt, caption) or (None, None).

        - skips if SceneImage already has caption_joy and `force=False`,
        - prefers per-image labels; falls back to scene-level labels,
        - forwards user hint verbatim,
        - routes the caption call through joy_client to the running
          joy_server,
        - runs post-caption validators as logged warnings.
        """
        try:
            simg = cast(SceneImage, self._sim.img_from_id(image_id))
        except Exception as e:
            self._log(f'id [{image_id}]: {e}', 'warn')
            return None, None

        caption_joy_current = simg.data.get(SceneDef.FIELD_CAPTION_JOY, None)
        if (caption_joy_current is not None) and (not self._force):
            return None, None

        url = simg.url_from_data
        if url is None:
            return None, None

        labels = self._collect_labels(simg, url)
        hint_raw = simg.data.get(SceneDef.FIELD_HINTS, '') or ''
        # Treat literal 'none' (case-insensitive) as a no-hint sentinel.
        hint = hint_raw if hint_raw.strip().lower() != 'none' else ''
        if hint:
            self._log(f'id [{image_id}]: using image hints [{hint}].')
        elif hint_raw.strip().lower() == 'none':
            self._log(f'id [{image_id}]: hint is "none" sentinel — skipped.')

        # Prompt-pickup: if the SceneImage has a non-empty caption_prompt
        # in the DB, use it verbatim — that is the canonical (possibly
        # human-edited) prompt to send. Otherwise compose fresh from skin
        # rules + label expansions + hint.
        stored_prompt = (simg.data.get(SceneDef.FIELD_CAPTION_PROMPT) or '').strip()
        if stored_prompt:
            self._log(f'id [{image_id}]: using stored caption_prompt ({len(stored_prompt)} chars).')
            user_content = stored_prompt
        else:
            user_content = self.skin.compile_user_prompt(labels, hint)
            self._log(
                f'id [{image_id}]: composed fresh caption_prompt '
                f'({len(user_content)} chars).'
            )

        t0 = time.time()
        prompt, caption = joy_client.caption(
            image_url=str(url),
            user_content=user_content,
            system_content=self.skin.directive,
        )
        elapsed = time.time() - t0
        self._log(f'prompt[{prompt}] caption[{caption}]')

        # Append the Stage-2 round-trip to the image's caption_log so
        # /imgs_caption preserves a full audit trail per image. Failures
        # here are non-fatal: the caption succeeded; logging is bonus.
        try:
            caption_log.log_joy_call(
                simg,
                stage='caption_joy',
                user_content=user_content,
                skin=self.skin,
                response_caption=caption or '',
                elapsed_seconds=elapsed,
                adapter='default',
            )
        except Exception as e:
            self._log(f'caption_log append failed: {e}', 'warn')

        for v in self.skin.caption_violations(caption):
            self._log(f'forbidden: {v!r}', 'warn')
        for w in self.skin.body_type_warnings(caption, labels):
            self._log(w, 'warn')
        for m in self.skin.missing_triggers(caption):
            self._log(f'missing trigger phrase: {m!r}', 'warn')

        return prompt, caption

    def caption_images(self, image_ids: list[str]) -> dict[str, dict[str, str]]:
        """Batch helper: returns {image_id: {prompt, caption}} for every
        successfully captioned image.
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
        """Return the structured label paths to feed into the captioner.

        Precedence:
        1. `FIELD_LABELS_NG` on the image (the canonical, path-keyed list
           edited via the per-cell ng-buttons). Returned verbatim.
        2. legacy `FIELD_LABELS` on the image, translated to paths via
           `compute_labels_ng`. The legacy field is preserved for backward
           compatibility but is not the source of truth for ng captioning.
        3. legacy labels on the parent scene (translated the same way).
        """
        # 1) labels_ng on the image
        ng_paths = simg.data.get(SceneDef.FIELD_LABELS_NG) or []
        if ng_paths:
            self._log(f'id [{simg.id}]: using labels_ng {ng_paths}.')
            return list(ng_paths)

        # 2) legacy image labels → translated paths
        legacy = simg.data.get(SceneDef.FIELD_LABELS, []) or []
        if not legacy:
            # 3) legacy scene labels → translated paths
            id_scene = scene_id_from_url(url)
            if id_scene is None:
                return []
            try:
                scene: Scene = self._scm.scene_from_id_or_url(id_scene)
            except Exception:
                return []
            legacy = scene.data.get(SceneDef.FIELD_LABELS, []) or []
            if legacy:
                self._log(
                    f'id [{simg.id}]: no labels_ng or image labels, '
                    f'falling back to scene labels {legacy}.'
                )
        else:
            self._log(
                f'id [{simg.id}]: no labels_ng; translating legacy labels {legacy}.'
            )

        if not legacy:
            return []
        paths, unknown = compute_labels_ng(legacy, self.skin)
        if unknown:
            self._log(
                f'id [{simg.id}]: legacy labels with no skin path: {unknown}',
                'warn',
            )
        return paths

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[JoySceneDB:{level}] {msg}')
