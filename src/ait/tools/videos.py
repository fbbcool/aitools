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
from PIL import Image

from ait.tools.images import PARENT_METADATA_CHUNK, _metadata_from_chunks

# Container-level tag names as written by FbbcoolSaveVideo. Matroska stores
# tag names case-insensitively and ffmpeg/PyAV return them UPPERCASED on read
# (PARENT_METADATA, PROMPT, WORKFLOW) — matching is case-insensitive.
METADATA_TAGS: Final = ('prompt', 'workflow', PARENT_METADATA_CHUNK)

# Anchor-frame slots (board task 84). FbbcoolSaveVideo masters carry one
# single-frame lossless FFV1/bgr0 stream per anchor, titled
# `fbbcool_anchor_<slot>` — the payload's `video.anchors` list names the slots.
ANCHOR_SLOTS: Final = ('first', 'last')
ANCHOR_TITLE_PREFIX: Final = 'fbbcool_anchor_'


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


def _stream_title(stream) -> str:
    try:
        return str((stream.metadata or {}).get('title', '')).lower()
    except Exception:
        return ''


def _anchor_frame(url: Path, title: str) -> av.VideoFrame | None:
    """Decode the single frame of the anchor stream titled `title`, if any."""
    with av.open(str(url)) as container:
        anchors = [s for s in container.streams.video if _stream_title(s) == title]
        if not anchors:
            return None
        for packet in container.demux(anchors):
            for frame in packet.decode():
                if isinstance(frame, av.VideoFrame):
                    return frame
    return None


def _bulk_frame(url: Path, slot: str) -> av.VideoFrame | None:
    """Decode the bulk video stream's first or last frame.

    Last frame by seeking to the stream end and decoding to exhaustion
    (keyframe-accurate then forward-decoded), with a sequential decode of the
    whole clip when seeking is unsupported.
    """
    with av.open(str(url)) as container:
        main = [
            s
            for s in container.streams.video
            if not _stream_title(s).startswith(ANCHOR_TITLE_PREFIX)
        ]
        if not main:
            return None
        stream = main[0]
        # Captured while the container is open: a Stream must not be touched
        # after its container closes (PyAV frees the underlying AVStream).
        main_index = stream.index
        if slot == 'first':
            return next(container.decode(stream), None)
        last = None
        try:
            if stream.duration is not None:
                container.seek(stream.duration, stream=stream, backward=True)
                for frame in container.decode(stream):
                    last = frame
        except Exception:
            last = None
    if last is None:
        with av.open(str(url)) as container:
            for tail in container.decode(container.streams[main_index]):
                if isinstance(tail, av.VideoFrame):
                    last = tail
    return last


def ref_frame(url: Path | str, slot: str) -> Image.Image | None:
    """Extract a reference frame from a video (board task 84).

    `slot` is an anchor name from the enhancer payload's `video.anchors`
    ('first' or 'last'). Masters written by FbbcoolSaveVideo carry each anchor
    as a single-frame lossless stream — when the named anchor stream exists its
    frame is returned bit-exact, untouched by the lossy bulk encode. Containers
    without anchor streams (foreign clips) fall back to the bulk video stream's
    first/last decoded frame.

    Returns a PIL image, or None — never raises — for a missing, unreadable or
    non-video file (same contract as `metadata()`). An unknown slot raises
    ValueError.
    """
    if slot not in ANCHOR_SLOTS:
        raise ValueError(f'unknown slot {slot!r}, expected one of {ANCHOR_SLOTS}')
    url = Path(url)
    if not url.is_file():
        return None
    try:
        frame = _anchor_frame(url, ANCHOR_TITLE_PREFIX + slot)
        if frame is None:
            frame = _bulk_frame(url, slot)
        return frame.to_image() if frame is not None else None
    except Exception:
        return None
