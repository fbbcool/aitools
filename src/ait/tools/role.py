"""Media role — embedded metadata section `ait_role` (board FEATURE t215).

A role says what a media file is for. Structured JSON, today only `descr`
(free text); unknown keys of an existing role survive a write.

    {'schema': 'ait.media.role.v1', 'descr': '<text>'}

Carriers (written in place, no re-encode, atomic temp + rename):
  - PNG: text chunk `ait_role` (IDAT + all other chunks byte-identical)
  - video (mp4 / mov / mkv): container tag `ait_role` via an ffmpeg remux
    `-map 0 -c copy` (every stream incl. anchor streams + all other tags kept)
Other formats (jpg / webp / gif, audio) are unsupported: `role()` returns None,
`role_set()` raises `RoleUnsupported`.

The metadata dicts of `images.metadata()` / `videos.metadata()` carry the same
parsed role under `md['role']`.
"""

import json
import subprocess
from pathlib import Path
from typing import Final

import av

from ait.tools.images import (
    _PNG_SIG,
    ROLE_CHUNK,
    ROLE_SCHEMA,
    _png_text_chunk_upsert,
    role_from_raw,
)

ROLE_SUFFIX_IMG: Final = ('.png',)
ROLE_SUFFIX_VID: Final = ('.mp4', '.mov', '.mkv')
_MP4_LIKE: Final = ('.mp4', '.mov')
# muxer-owned mp4/mov keys: with use_metadata_tags they would be doubled ('512;512')
_MP4_MUXER_KEYS: Final = ('major_brand', 'minor_version', 'compatible_brands')


class RoleUnsupported(ValueError):
    """The file format cannot carry an embedded role."""


def supported(url: str | Path) -> bool:
    return Path(url).suffix.lower() in ROLE_SUFFIX_IMG + ROLE_SUFFIX_VID


def descr(role: dict | None) -> str:
    """The role's description ('' when there is none)."""
    d = (role or {}).get('descr')
    return d.strip() if isinstance(d, str) else ''


def role(url: str | Path) -> dict | None:
    """The embedded role of a media file, None when absent / unsupported / unreadable."""
    p = Path(url)
    if not (p.is_file() and supported(p)):
        return None
    try:
        if p.suffix.lower() in ROLE_SUFFIX_IMG:
            from PIL import Image

            with Image.open(p) as im:
                raw = (im.info or {}).get(ROLE_CHUNK)
        else:
            with av.open(str(p)) as c:
                tags = {k.lower(): v for k, v in (c.metadata or {}).items()}
            raw = tags.get(ROLE_CHUNK)
    except Exception:  # noqa: BLE001 - a broken file never raises here
        return None
    return role_from_raw(raw)


def role_set(url: str | Path, new: dict | None) -> dict | None:
    """Write (or remove) the embedded role of `url`; returns the role now stored.

    `new` is merged over the existing role (unknown keys kept); `schema` is
    always set. `new=None` or an empty `descr` removes the section. Raises
    `RoleUnsupported` for formats without a carrier, `FileNotFoundError` for a
    missing file, `RuntimeError` when the write fails."""
    p = Path(url)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    if not supported(p):
        raise RoleUnsupported(f'role not supported for {p.suffix or p.name}')
    old = role(p)
    merged: dict | None = None
    if new is not None and descr(new):
        merged = {'schema': ROLE_SCHEMA, **(old or {}), **new}
        merged['schema'] = ROLE_SCHEMA
        merged['descr'] = descr(new)
    if merged is None and old is None:
        return None  # nothing to remove: leave the file untouched
    text = json.dumps(merged, ensure_ascii=True) if merged is not None else None
    if p.suffix.lower() in ROLE_SUFFIX_IMG:
        if not p.read_bytes()[:8] == _PNG_SIG:
            raise RoleUnsupported(f'{p.name} is not a png')
        if not _png_text_chunk_upsert(p, ROLE_CHUNK, text):
            raise RuntimeError(f'role write failed: {p.name}')
    else:
        _av_tag_set(p, ROLE_CHUNK, text)
    return merged


def _av_tag_set(p: Path, key: str, text: str | None) -> None:
    """Set / remove one container tag by a lossless remux (all streams, tags kept)."""
    tmp = p.with_name(f'.{p.stem}.tmp_role{p.suffix}')
    cmd = ['ffmpeg', '-v', 'error', '-y', '-i', str(p), '-map', '0', '-c', 'copy',
           '-metadata', f'{key}={text or ""}']  # fmt: skip
    if p.suffix.lower() in _MP4_LIKE:
        for k in _MP4_MUXER_KEYS:
            cmd += ['-metadata', f'{k}=']
        cmd += ['-movflags', 'use_metadata_tags']
    cmd.append(str(tmp))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f'role write failed: {res.stderr.strip()[-300:]}')
        tmp.replace(p)
    finally:
        tmp.unlink(missing_ok=True)
