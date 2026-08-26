"""Embedded-metadata reader for video files (board task 82).

`FbbcoolSaveVideo` (comfyui-fbbcool-suite) writes video masters that carry the
same provenance images do — the enhancer `parent_metadata` envelope plus the
ComfyUI `prompt`/`workflow` JSON — as Matroska container-level tags. This
module is the video branch of the single-point-of-truth entry point
`ait.tools.images.metadata()`: same schema, same extraction code, different
carrier.
"""

from pathlib import Path
from typing import Final

import av

from ait.tools.images import PARENT_METADATA_CHUNK, _metadata_from_chunks

# Container-level tag names as written by FbbcoolSaveVideo. Matroska stores
# tag names case-insensitively and ffmpeg/PyAV return them UPPERCASED on read
# (PARENT_METADATA, PROMPT, WORKFLOW) — matching is case-insensitive.
METADATA_TAGS: Final = ('prompt', 'workflow', PARENT_METADATA_CHUNK)


def metadata(url: Path | str) -> dict | None:
    """Video branch of the embedded-metadata entry point.

    Reads the container-level tags (`av.open(url).metadata`, any container
    PyAV can demux — no codec special-casing) and returns the same
    `ait.image.metadata.v1` dict as `ait.tools.images.metadata()`:
    `PARENT_METADATA` feeds the `parent` key with identical normalization,
    `PROMPT`/`WORKFLOW` go through the same generation-prompt reconstruction
    and `prompt_index` attribution as the PNG path. The `image` block carries
    the first video stream's dimensions.

    Returns None — never raises — for unreadable/non-media files and for
    videos carrying none of the known tags.
    """
    url = Path(url)
    if not url.is_file():
        return None
    try:
        with av.open(str(url)) as container:
            tags = {k.lower(): v for k, v in (container.metadata or {}).items()}
            width = height = 0
            for stream in container.streams.video:
                width, height = stream.width or 0, stream.height or 0
                break
    except Exception:
        return None

    info_ext = {name: tags[name] for name in METADATA_TAGS if name in tags}
    if not info_ext:
        return None
    return _metadata_from_chunks(url, info_ext, width, height)
