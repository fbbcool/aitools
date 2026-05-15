"""Helpers that write `caption_log` entries onto SceneImage documents.

Each entry is appended to `SceneDef.FIELD_CAPTION_LOG` and `db_store()`d
immediately so a crash mid-pipeline still leaves a readable trail.

Three entry shapes are produced by the /imgs_caption pipeline today:

- joy call      — Stage 2 (or any future probe round-trip): the prompt
                  sent to joy_server and the caption returned.
- audit snapshot — Stage 3 'before' and 'after' the auto-fix pass: the
                  caption text plus the categorised flags it triggered.

Storage choices (audit-trail vs noise):
- The `user` content (per-image composed prompt) IS stored — it varies
  per call and is the only field with archival value.
- The `system` content (skin directive) is NOT stored — it's identical
  across every call against the same skin version and would dominate
  document size. Instead each entry carries `skin_name` + the skin's
  `source_hash`, which lets you reconstruct the directive at any time
  by loading that skin version.
- The captioner's `prompt` echo (which equals `user` for the joy_server
  path used by JoySceneDBNG) is dropped; only `response_caption` is
  recorded.

Callers pass the SceneImage instance plus the payload kwargs. The helper
fills in `ts` and `stage`, appends, and persists.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional, TYPE_CHECKING

from aidb import SceneImage
from aidb.scene.scene_common import SceneDef

from . import joy_client

if TYPE_CHECKING:
    from .skin import Skin


def _skin_ref(skin: Optional['Skin']) -> dict[str, str]:
    """Build the {'skin_name', 'skin_source_hash'} marker stored on each
    joy-call entry, replacing the full directive text. Reads the hash
    from the skin's built block; falls back to recomputing if missing.
    """
    if skin is None:
        return {'skin_name': '', 'skin_source_hash': ''}
    name = getattr(skin, 'name', '') or ''
    src = getattr(skin, 'source', {}) or {}
    h = (src.get('_built') or {}).get('source_hash') or ''
    if not h:
        try:
            from .skin import _compute_source_hash
            h = _compute_source_hash(src)
        except Exception:
            h = ''
    return {'skin_name': str(name), 'skin_source_hash': str(h)}


def start_run(simg: SceneImage, *, clear: bool = True, run_tag: str = '') -> None:
    """Open a fresh caption_log run on an image.

    By default the prior log is cleared so the new /imgs_caption invocation
    is not conflated with old ones. Pass `clear=False` to keep appending.
    A leading 'run_start' marker captures the run tag (e.g. command name)
    and timestamp so each run is delimited in the persisted history.
    """
    if clear:
        simg.clear_caption_log()
    simg.append_caption_log({
        'stage': 'run_start',
        'run_tag': run_tag or '',
    })
    simg.db_store()


def log_joy_call(
    simg: SceneImage,
    *,
    stage: str,
    user_content: str,
    skin: Optional['Skin'],
    response_caption: str,
    elapsed_seconds: float,
    adapter: str = 'default',
) -> None:
    """Append one joy round-trip to the image's caption_log.

    `stage` is a free-form tag — typical values: `'caption_joy'` (Stage 2),
    `'audit_probe'` (any Stage 3.5 probe). The shape is identical so
    consumers can filter by stage tag.

    The system directive is NOT stored verbatim; instead the skin's
    `name` + `source_hash` are recorded so the directive can be
    reconstructed by re-loading that skin version. The captioner's
    echoed prompt is dropped — it's identical to `user_content` for the
    joy_server path.
    """
    entry: dict[str, Any] = {
        'stage': stage,
        'user': user_content or '',
        'response_caption': response_caption or '',
        'elapsed_seconds': round(float(elapsed_seconds), 3),
        'adapter': adapter,
    }
    entry.update(_skin_ref(skin))
    simg.append_caption_log(entry)
    simg.db_store()


def log_audit(
    simg: SceneImage,
    *,
    when: str,
    caption: str,
    violations: Optional[list] = None,
    body_warnings: Optional[list] = None,
    missing_triggers: Optional[list] = None,
    extra_flags: Optional[dict[str, Any]] = None,
    fixes_applied: Optional[list] = None,
) -> None:
    """Append a Stage-3 audit snapshot.

    `when` is either `'audit_before'` (state of caption_joy as returned by
    the captioner) or `'audit_after'` (state after auto-fixes were
    applied). `fixes_applied` is only meaningful on the 'after' entry —
    it's the list of fix labels Stage 3 applied (`'naked-multi'`,
    `'opener'`, `'body-type'`, etc.).

    `extra_flags` is a free-form dict for one-off categories Stage 3 wants
    to record (e.g. `'pose_mandate_present'`, `'naked_attributions'`).
    """
    entry: dict[str, Any] = {
        'stage': when,
        'caption': caption or '',
        'violations': list(violations or []),
        'body_warnings': list(body_warnings or []),
        'missing_triggers': list(missing_triggers or []),
    }
    if extra_flags:
        entry['extra_flags'] = dict(extra_flags)
    if fixes_applied is not None:
        entry['fixes_applied'] = list(fixes_applied)
    simg.append_caption_log(entry)
    simg.db_store()


@contextmanager
def joy_call(
    simg: SceneImage,
    *,
    stage: str,
    image_url: str,
    user_content: str,
    skin: Optional['Skin'],
    adapter: str = 'default',
) -> Iterator[tuple[str, str]]:
    """Context manager wrapping `joy_client.caption()` with auto-logging.

    Yields `(prompt, caption)` from joy_client and persists a log entry on
    the way out — including the elapsed seconds. The system directive is
    pulled from `skin.directive` for the API call but is NOT stored in
    the log entry (only `skin_name` + `skin_source_hash` are). Exceptions
    from the underlying call are NOT swallowed; if it raises, no entry
    is recorded.
    """
    system_content = skin.directive if skin is not None else None
    t0 = time.time()
    prompt, caption = joy_client.caption(
        image_url=image_url,
        user_content=user_content,
        system_content=system_content,
        adapter=adapter,
    )
    elapsed = time.time() - t0
    log_joy_call(
        simg,
        stage=stage,
        user_content=user_content,
        skin=skin,
        response_caption=caption,
        elapsed_seconds=elapsed,
        adapter=adapter,
    )
    yield prompt, caption
