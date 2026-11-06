"""Embedded-metadata reader for video files (board task 82).

`FbbcoolSaveVideo` (comfyui-fbbcool-suite) writes video masters that carry the
same provenance images do — the enhancer `parent_metadata` envelope plus the
ComfyUI `prompt`/`workflow` JSON — as Matroska container-level tags. This
module is the video branch of the single-point-of-truth entry point
`ait.tools.images.metadata()`: same schema, same extraction code, different
carrier.
"""

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final
from urllib.parse import unquote

import av
import numpy as np
from PIL import Image

from ait.tools.files import suffix_vid

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


# ---------------------------------------------------------------------- #
# H3 clip chains (board task 172)
# ---------------------------------------------------------------------- #
# A chain is built with MiniMaxH3AddGuide continuations (task 171): a root
# clip R, `post` clips that pin the previous clip's last `pin` frames at
# frame_idx 0, and `pre` clips that end on the next clip's first `pin` frames.
# Each continuation names its anchor in the enhancer payload it was rendered
# from: prompts_ref.prompt_data[i].continue = {dir: 'post'|'pre', url, pin}.

CHAIN_PIN: Final = 22  # default pin (17k+5 latent-aligned), payload v6.9
CHAIN_EVAL_SIZE: Final = (168, 96)  # seam metrics resolution (reference script)
CHAIN_PROBE: Final = 3  # frames per side for the exposure statistics
CHAIN_OUT_DIR: Final = Path.home() / 'Downloads' / '000_comfy'
# where a moved / renamed / copied anchor master is looked up by its temp id
_COMFY3: Final = Path('/home/misw/Repos/fbbcool/agent-comfy/installs/comfy3/ComfyUI')
CHAIN_SEARCH_DIRS: Final = (CHAIN_OUT_DIR, _COMFY3 / 'temp', _COMFY3 / 'output')
_TEMP_ID_RE: Final = re.compile(r'fbbcool_temp_([a-z0-9]{5})_')


def _clip_path(url: str | Path) -> Path:
    s = str(url)
    if s.startswith('file://'):
        s = unquote(s[len('file://') :])
    return Path(s).expanduser()


def _temp_id(path: Path) -> str | None:
    m = _TEMP_ID_RE.search(path.name)
    return m.group(1) if m else None


def resolve_clip(url: str | Path, search_dirs: tuple[Path, ...] | None = None) -> Path:
    """Locate a chain clip named by a `continue.url`.

    The path itself wins. Otherwise the clip was moved, copied or renamed:
    it is looked up by the `fbbcool_temp_xxxxx` stem (exact file name first,
    then any video file whose name carries the 5-char temp id — misw renames
    e.g. ``fbbcool_temp_jrfjs_00001_.mkv`` → ``chain2_post_jrfjs.mkv``) in
    `search_dirs` (default: 000_comfy, comfy3 temp / output); the newest match
    wins. Raises FileNotFoundError when it can't be resolved.
    """
    path = _clip_path(url)
    if path.is_file():
        return path
    tid = _temp_id(path)
    dirs = [Path(d) for d in (search_dirs or CHAIN_SEARCH_DIRS)]
    if tid:
        for d in dirs:
            if (d / path.name).is_file():
                return d / path.name
        hits = [
            f
            for d in dirs
            if d.is_dir()
            for f in d.glob(f'*{tid}*')
            if f.is_file() and f.suffix.lower() in suffix_vid()
        ]
        if hits:
            return max(hits, key=lambda f: f.stat().st_mtime)
    raise FileNotFoundError(
        f'chain clip {url} not found (temp id {tid}; searched {", ".join(map(str, dirs))})'
    )


def _rendered_ref_entry(md: dict) -> dict | None:
    """The prompts_ref entry the clip was rendered from: the entry whose prompt
    is the clip's generation prompt, else ``current`` (+ the client's
    ``prompt_offset``)."""
    enh = md.get('enhancer')
    if not isinstance(enh, dict):
        enh = (md.get('parent') or {}).get('enhancer')
    if not isinstance(enh, dict):
        return None
    sec = enh.get('prompts_ref')
    if not isinstance(sec, dict):
        return None
    data = [e for e in sec.get('prompt_data') or [] if isinstance(e, dict)]
    if not data:
        return None
    gen = (md.get('generation') or {}).get('prompt')
    if gen:
        for e in data:
            if (e.get('prompt') or '').strip() == str(gen).strip():
                return e
    cur = sec.get('current', 0)
    off = (md.get('parent') or {}).get('prompt_offset', 0)
    i = (cur if isinstance(cur, int) else 0) + (off if isinstance(off, int) else 0)
    return data[i] if 0 <= i < len(data) else data[0]


def chain_link(url: str | Path) -> dict | None:
    """The clip's continuation link ``{dir, url, pin}`` from its embedded
    enhancer payload; None for a chain root / a clip without a payload."""
    md = metadata(url)
    entry = _rendered_ref_entry(md) if md else None
    link = (entry or {}).get('continue')
    if not isinstance(link, dict) or link.get('dir') not in ('post', 'pre') or not link.get('url'):
        return None
    pin = link.get('pin')
    return {
        'dir': link['dir'],
        'url': str(link['url']),
        'pin': pin if isinstance(pin, int) else CHAIN_PIN,
    }


def _walk(start: Path, direction: str, search_dirs) -> list[tuple[Path, int]]:
    """[(clip, pin to its anchor), …] from `start` back to the root (pin 0)."""
    out: list[tuple[Path, int]] = []
    seen: set[Path] = set()
    cur = start
    while True:
        key = cur.resolve()
        if key in seen:
            raise ValueError(f'chain loop at {cur}')
        seen.add(key)
        link = chain_link(cur)
        if link is None:
            out.append((cur, 0))
            return out
        if link['dir'] != direction:
            raise ValueError(
                f'{cur.name} is a {link["dir"]} continuation, expected {direction} '
                f'(slot 1 = last clip of the chain, slot 2 = first clip)'
            )
        out.append((cur, link['pin']))
        search = (cur.parent, *(search_dirs or CHAIN_SEARCH_DIRS))
        cur = resolve_clip(link['url'], search)


def _same_clip(a: Path, b: Path) -> bool:
    try:
        if a.samefile(b):
            return True
    except OSError:
        pass
    ta, tb = _temp_id(a), _temp_id(b)
    return ta is not None and ta == tb


def chain_clips(
    last: str | Path, first: str | Path | None = None, search_dirs=None
) -> tuple[list[Path], int, list[int]]:
    """Walk the parent links: ``(clips in play order, root index, pin per seam)``.

    From `last`, follow dir-post links back to the root; from `first`, follow
    dir-pre links to the same root. Order = pre… → root → post….
    """
    post = _walk(_clip_path(last), 'post', search_dirs)
    if not post[0][0].is_file():
        raise FileNotFoundError(f'last clip {last} not found')
    root = post[-1][0]
    pre: list[tuple[Path, int]] = []
    if first:
        pre = _walk(_clip_path(first), 'pre', search_dirs)
        if not _same_clip(pre[-1][0], root):
            raise ValueError(
                f'first clip chain ends at {pre[-1][0].name}, last clip chain at {root.name}'
            )
        pre = pre[:-1]
    # seams: pre clip i pins to its right neighbour, post clip i to its left one
    clips = [c for c, _ in pre] + [root] + [c for c, _ in reversed(post[:-1])]
    pins = [p for _, p in pre] + [p for _, p in reversed(post[:-1])]
    return clips, len(pre), pins


def _probe_av(path: Path) -> dict:
    out = subprocess.run(
        [
            'ffprobe', '-v', 'error', '-show_entries',
            'stream=index,codec_type,width,height,r_frame_rate,sample_rate', '-of', 'json',
            str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    streams = json.loads(out)['streams']
    v = next(s for s in streams if s['codec_type'] == 'video')
    a = next((s for s in streams if s['codec_type'] == 'audio'), None)
    num, den = map(int, v['r_frame_rate'].split('/'))
    return {
        'w': v['width'],
        'h': v['height'],
        'fps': num / den,
        'sr': int(a['sample_rate']) if a else None,
    }


def _iter_frames(path: Path, w: int, h: int, scale: tuple[int, int] | None = None):
    """Stream the bulk video stream (0:v:0) as rgb24 frames — one in memory at a time."""
    vf = ['-vf', f'scale={scale[0]}:{scale[1]}'] if scale else []
    if scale:
        w, h = scale
    size = w * h * 3
    proc = subprocess.Popen(
        ['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0', *vf,
         '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
        stdout=subprocess.PIPE,
    )  # fmt: skip
    assert proc.stdout is not None
    try:
        while len(buf := proc.stdout.read(size)) == size:
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        if proc.poll() is None:  # consumer stopped early: no broken-pipe noise
            proc.kill()
        proc.stdout.close()
        proc.wait()


def _exposure_offset(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Per-channel exposure offset src→dst: median of the pixel-wise difference
    of the mean frames on both sides of the cut (moved regions drop out)."""
    d = dst.astype(np.float32).mean(0) - src.astype(np.float32).mean(0)
    return np.median(d.reshape(-1, 3), axis=0)


def _best_strength(left: np.ndarray, right: np.ndarray, off: np.ndarray, side: str) -> float:
    """Strength in [0, 1] minimising the cut MAD — matching never makes a seam worse."""
    best = (float(np.abs(left - right).mean()), 0.0)
    for g in np.linspace(0.1, 1.0, 10):
        lf, rf = (left + g * off, right) if side == 'left' else (left, right + g * off)
        cand = float(np.abs(np.clip(lf, 0, 255) - np.clip(rf, 0, 255)).mean())
        best = min(best, (cand, float(g)))
    return best[1]


def _cosine_ramp(n: int) -> np.ndarray:
    """Weights 1 → 0 over n frames (index 0 = full correction)."""
    return 0.5 * (1 + np.cos(np.pi * np.arange(n) / n))


def _geo_jump(left: np.ndarray, right: np.ndarray) -> float:
    d = left - right
    return float(np.abs(d - np.median(d.reshape(-1, 3), axis=0)).mean())


def _mad(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.abs(x - y).mean())


def _default_chain_out(root: Path, n: int) -> Path:
    out = CHAIN_OUT_DIR / f'chain_{root.stem}_{n}clips.mkv'
    k = 2
    while out.exists():
        out = CHAIN_OUT_DIR / f'chain_{root.stem}_{n}clips_{k}.mkv'
        k += 1
    return out


def join_clips(
    clips: Sequence[str | Path],
    root: int = 0,
    out: str | Path | None = None,
    pin: int | list[int] = CHAIN_PIN,
    ramp: int = 48,
    search: bool = True,
    match: bool = True,
    probe: int = CHAIN_PROBE,
    crf: int = 14,
    verbose: int = 1,
) -> dict:
    """Join an explicit H3 continuation chain (play order; `root` = R's index).

    Port of agent-comfy ``scripts/h3_chain_join.py`` (task 171), frames
    streamed instead of held in memory. At each seam the right clip's first
    `pin` frames re-render the left clip's last `pin` frames; the cut sits at
    overlap offset i (left[:nL-pin+i] + right[i:], same total length) — with
    `search` the i with the smallest exposure-free jump, else i = pin (plain
    join). With `match`, every non-root clip gets a per-channel exposure
    offset toward its root-side neighbour, at the strength minimising the cut
    jump, faded over `ramp` frames (cosine): post clips at their start, pre
    clips toward their end. The root is never altered. Audio is cut
    sample-exact at the same cuts; output H.264 crf `crf` + AAC.

    Returns a report dict: ``out``, ``frames``, ``seconds``, ``clips``, ``root``,
    ``seams`` (per seam: left/right names, ``cut`` offset, ``pin``, ``plain`` /
    ``written`` MAD /255 on 168×96, motion ``before`` / ``after`` the cut) and
    ``corrections``.
    """
    paths = [Path(c) for c in clips]
    if not paths:
        raise ValueError('no clips')
    if not 0 <= root < len(paths):
        raise ValueError(f'root index {root} out of range')
    pins = list(pin) if isinstance(pin, (list, tuple)) else [pin] * (len(paths) - 1)
    if len(pins) != len(paths) - 1:
        raise ValueError(f'{len(paths) - 1} seams but {len(pins)} pins')
    names = [
        'root' if i == root else (f'pre{root - i}' if i < root else f'post{i - root}')
        for i in range(len(paths))
    ]

    def log(msg: str) -> None:
        if verbose > 0:
            print(f'[chain_join:info] {msg}', flush=True)

    info = _probe_av(paths[root])
    W, H, fps, sr = info['w'], info['h'], info['fps'], info['sr']
    for p in paths:
        pi = _probe_av(p)
        if (pi['w'], pi['h']) != (W, H) or abs(pi['fps'] - fps) > 1e-6 or pi['sr'] != sr:
            raise ValueError(f'{p}: format {pi} differs from the root {info}')

    log(f'decoding {len(paths)} clips ({W}x{H} @ {fps:g} fps)')
    small = [
        np.stack(list(_iter_frames(p, W, H, CHAIN_EVAL_SIZE))).astype(np.float32) for p in paths
    ]
    n = [len(s) for s in small]

    seam_cut, seams = [], []
    for j in range(len(paths) - 1):
        L, R, pj = small[j], small[j + 1], pins[j]
        if pj > min(n[j], n[j + 1]):
            raise ValueError(f'pin {pj} longer than clip {names[j]} / {names[j + 1]}')
        cands = range(pj + 1) if search else [pj]
        scores = {i: _geo_jump(L[n[j] - pj + i - 1], R[i]) for i in cands}
        best = min(scores, key=lambda i: scores[i])
        seam_cut.append(best)
        seams.append({'left': names[j], 'right': names[j + 1], 'cut': best, 'pin': pj,
                      'jump': scores[best], 'plain': _mad(L[n[j] - 1], R[pj])})  # fmt: skip
        log(f'cut {names[j]}->{names[j + 1]}: overlap frame {best}/{pj} (jump {scores[best]:.1f})')

    keep = []
    for ci in range(len(paths)):
        s = seam_cut[ci - 1] if ci > 0 else 0
        e = n[ci] - pins[ci] + seam_cut[ci] if ci < len(paths) - 1 else n[ci]
        keep.append((s, e))

    # full-res probe frames each correction needs, gathered in one streaming pass
    k = probe
    need: dict[int, set[int]] = {ci: set() for ci in range(len(paths))}
    plan = []  # (clip, neighbour, side)
    if match:
        for ci in range(len(paths)):
            if ci == root:
                continue
            nb = ci + 1 if ci < root else ci - 1
            (s, e), (ns, ne) = keep[ci], keep[nb]
            if ci < root:
                need[ci] |= set(range(e - k, e))
                need[nb] |= set(range(ns, ns + k))
            else:
                need[ci] |= set(range(s, s + k))
                need[nb] |= set(range(ne - k, ne))
            plan.append((ci, nb))
    full: dict[tuple[int, int], np.ndarray] = {}
    for ci, idx in need.items():
        if idx:
            for fi, f in enumerate(_iter_frames(paths[ci], W, H)):
                if fi in idx:
                    full[(ci, fi)] = f.copy()

    corr: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    corrections = []
    for ci, nb in plan:
        (s, e), (ns, ne) = keep[ci], keep[nb]
        w = np.zeros(e - s)
        r = min(ramp, e - s)
        if ci < root:  # pre side: this clip before the cut -> neighbour after it
            src = np.stack([full[(ci, f)] for f in range(e - k, e)])
            dst = np.stack([full[(nb, f)] for f in range(ns, ns + k)])
            off = _exposure_offset(src, dst)
            g = _best_strength(small[ci][e - 1], small[nb][ns], off, 'left')
            w[-r:] = _cosine_ramp(r)[::-1]  # 0 -> 1 toward the cut
        else:  # post side: this clip after the cut -> neighbour before it
            src = np.stack([full[(ci, f)] for f in range(s, s + k)])
            dst = np.stack([full[(nb, f)] for f in range(ne - k, ne)])
            off = _exposure_offset(src, dst)
            g = _best_strength(small[nb][ne - 1], small[ci][s], off, 'right')
            w[:r] = _cosine_ramp(r)
        corr[ci] = (off * g, w)
        corrections.append({'clip': names[ci], 'offset': [round(float(x), 2) for x in off],
                            'strength': round(g, 2), 'ramp': r})  # fmt: skip
        log(f'{names[ci]}: offset R{off[0]:+.1f} G{off[1]:+.1f} B{off[2]:+.1f}, strength {g:.1f}')
    full.clear()

    out_path = Path(out) if out else _default_chain_out(paths[root], len(paths))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    chain_tag = json.dumps({'clips': [str(p) for p in paths], 'root': root, 'cuts': seam_cut})
    with tempfile.TemporaryDirectory() as tmp:
        audio_in: list[str] = []
        if sr:
            ins, fc, cc = [], '', ''
            for i, p in enumerate(paths):
                s, e = keep[i]
                ins += ['-i', str(p)]
                a0, a1 = round(s / fps * sr), round(e / fps * sr)
                fc += (
                    f'[{i}:a:0]atrim=start_sample={a0}:end_sample={a1},asetpts=PTS-STARTPTS[a{i}];'
                )
                cc += f'[a{i}]'
            wav = os.path.join(tmp, 'audio.wav')
            subprocess.run(
                ['ffmpeg', '-v', 'error', '-y', *ins, '-filter_complex',
                 f'{fc}{cc}concat=n={len(paths)}:v=0:a=1[a]', '-map', '[a]',
                 '-c:a', 'pcm_s16le', wav],
                check=True,
            )  # fmt: skip
            audio_in = ['-i', wav, '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k',
                        '-shortest']  # fmt: skip
        enc = subprocess.Popen(
            ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
             '-s', f'{W}x{H}', '-r', f'{fps:g}', '-i', '-', *audio_in,
             '-c:v', 'libx264', '-crf', str(crf), '-preset', 'slow', '-pix_fmt', 'yuv420p',
             '-metadata', f'AIT_CHAIN={chain_tag}', str(out_path)],
            stdin=subprocess.PIPE,
        )  # fmt: skip
        assert enc.stdin is not None
        cuts, total = [], 0
        try:
            for ci, p in enumerate(paths):
                s, e = keep[ci]
                if total:
                    cuts.append(total)
                c = corr.get(ci)
                for fi, f in enumerate(_iter_frames(p, W, H)):
                    if fi < s:
                        continue
                    if fi >= e:
                        break
                    if c is not None and c[1][fi - s] > 0:
                        f = np.clip(f.astype(np.float32) + c[1][fi - s] * c[0], 0, 255)
                        f = f.round().astype(np.uint8)
                    enc.stdin.write(np.ascontiguousarray(f).tobytes())
                total += e - s
        finally:
            enc.stdin.close()
            rc = enc.wait()
        if rc:
            raise RuntimeError(f'ffmpeg encoder failed ({rc}) writing {out_path}')
    log(f'wrote {out_path}: {total} frames, {total / fps:.2f} s')

    written = np.stack(list(_iter_frames(out_path, W, H, CHAIN_EVAL_SIZE))).astype(np.float32)

    def step(rng) -> float:
        vals = [_mad(written[i], written[i + 1]) for i in rng]
        return float(np.median(vals)) if vals else 0.0

    for cut, seam in zip(cuts, seams, strict=True):
        seam['written'] = _mad(written[cut - 1], written[cut])
        seam['before'] = step(range(max(0, cut - 11), cut - 1))
        seam['after'] = step(range(cut, min(len(written) - 1, cut + 10)))
        seam['frame'] = cut
        log(f'seam {seam["left"]:>6} -> {seam["right"]:<6} {seam["plain"]:5.1f} -> '
            f'{seam["written"]:5.1f} | {seam["before"]:.1f} / {seam["after"]:.1f}')  # fmt: skip
    return {
        'out': str(out_path),
        'frames': total,
        'seconds': total / fps,
        'clips': [str(p) for p in paths],
        'root': root,
        'seams': seams,
        'corrections': corrections,
    }


def chain_join(
    last: str | Path,
    first: str | Path | None = None,
    out: str | Path | None = None,
    ramp: int = 48,
    search: bool = True,
    match: bool = True,
    verbose: int = 1,
) -> dict:
    """Join an H3 continuation chain found by walking its parent links (task 172).

    `last` = the chain's last clip (a post continuation, or the root itself);
    `first` = optionally its first clip (a pre continuation). The links are
    each clip's embedded ``prompts_ref`` entry ``continue = {dir, url, pin}``
    (see `chain_clips` / `resolve_clip`); the join itself is `join_clips`.
    `out` defaults to ``~/Downloads/000_comfy/chain_<root>_<n>clips.mkv``.
    Returns `join_clips`' report. Raises on an unresolvable / broken chain.
    """
    clips, root, pins = chain_clips(last, first)
    return join_clips(clips, root, out, pins, ramp, search, match, verbose=verbose)


def seam_summary(report: dict) -> str:
    """One line per seam: ``pre1→root 8.0→1.6 (1.3/2.2)`` (MAD /255, motion in brackets)."""
    return ' · '.join(
        f'{s["left"]}→{s["right"]} {s["plain"]:.1f}→{s.get("written", s["jump"]):.1f} '
        f'({s.get("before", 0):.1f}/{s.get("after", 0):.1f})'
        for s in report.get('seams', [])
    )


# ---------------------------------------------------------------------- #
# voice reference cut (board task 172)
# ---------------------------------------------------------------------- #
VOICE_SR: Final = 16000  # analysis rate (whisper input)
VOICE_WIN_S: Final = 0.1  # RMS scan window
VOICE_PAD_S: Final = 0.15
VOICE_SNAP_S: Final = 0.5  # max push of a line edge past whisper's word edge
VOICE_EDGE_DB: Final = 20.0  # edge push continues while within this of speech
# a line is music-free when its quietest gap drops to the silence floor: below
# this absolute level, or this far below the line's speech level
VOICE_FLOOR_DB: Final = -50.0
VOICE_DROP_DB: Final = 30.0
VOICE_MODEL: Final = 'large-v3'


def _audio_mono(url: Path, sr: int = VOICE_SR) -> np.ndarray:
    raw = subprocess.run(
        ['ffmpeg', '-v', 'error', '-i', str(url), '-map', '0:a:0', '-ac', '1', '-ar', str(sr),
         '-f', 'f32le', '-'],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    return np.frombuffer(raw, np.float32)


def _rms_db(audio: np.ndarray, sr: int = VOICE_SR, win_s: float = VOICE_WIN_S) -> np.ndarray:
    """RMS level (dBFS) per `win_s` window; index i covers [i*win_s, (i+1)*win_s)."""
    hop = int(sr * win_s)
    n = len(audio) // hop
    if n == 0:
        return np.zeros(0)
    frames = audio[: n * hop].reshape(n, hop)
    return 20 * np.log10(np.sqrt((frames**2).mean(1)) + 1e-9)


def _transcribe_words(audio: np.ndarray, model: str, device: str | None) -> list[list[dict]]:
    """faster-whisper segments as lists of ``{start, end, word}`` (seconds)."""
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]  # heavy, lazy

    devices = [device] if device else ['cuda', 'cpu']
    last_err: Exception | None = None
    for dev in devices:
        try:
            ct = 'float16' if dev == 'cuda' else 'int8'
            wm = WhisperModel(model, device=dev, compute_type=ct)
            segs, _ = wm.transcribe(audio, word_timestamps=True, beam_size=5)
            return [
                [{'start': w.start, 'end': w.end, 'word': w.word} for w in s.words or []]
                for s in segs
            ]
        except Exception as e:  # e.g. no CUDA / VRAM held by ComfyUI → next device
            last_err = e
    raise RuntimeError(f'whisper failed on {devices}: {last_err}')


def _win(db: np.ndarray, t0: float, t1: float) -> np.ndarray:
    i0, i1 = int(t0 / VOICE_WIN_S), int(np.ceil(t1 / VOICE_WIN_S))
    return db[max(0, i0) : min(len(db), max(i1, i0 + 1))]


def _line_bounds(
    db: np.ndarray, words: list[dict], dur: float
) -> tuple[float, float, float, float]:
    """``(t0, t1, floor, speech)`` for a word run.

    Whisper's word edges sit inside the voiced sound, so each line edge is
    first pushed outward (≤ VOICE_SNAP_S) while the level stays within
    VOICE_EDGE_DB of the speech level, then padded by VOICE_PAD_S. `floor` =
    the quietest 0.1 s window over the padded line — its inter-word gaps and
    pads: with music under the voice it never drops.
    """
    speech_w = [float(np.median(w)) for wd in words if len(w := _win(db, wd['start'], wd['end']))]
    speech = float(np.median(speech_w)) if speech_w else 0.0
    loud = speech - VOICE_EDGE_DB
    nwin = int(VOICE_SNAP_S / VOICE_WIN_S)
    i0 = int(words[0]['start'] / VOICE_WIN_S)
    i1 = int(np.ceil(words[-1]['end'] / VOICE_WIN_S))
    for _ in range(nwin):
        if i0 > 0 and db[i0 - 1] > loud:
            i0 -= 1
    for _ in range(nwin):
        if i1 < len(db) and db[i1] > loud:
            i1 += 1
    t0 = max(0.0, i0 * VOICE_WIN_S - VOICE_PAD_S)
    t1 = min(dur, i1 * VOICE_WIN_S + VOICE_PAD_S)
    span = _win(db, t0, t1)
    floor = float(span.min()) if len(span) else 0.0
    return t0, t1, floor, speech


def voice_ref(
    url: str | Path,
    out: str | Path | None = None,
    min_s: float = 3,
    max_s: float = 6,
    model: str = VOICE_MODEL,
    device: str | None = None,
    verbose: int = 1,
) -> Path | None:
    """Auto-cut a voice reference wav from a clip (board task 172).

    Transcribes with faster-whisper (word timestamps), then takes the longest
    spoken line of `min_s`–`max_s` seconds — whole whisper segments first,
    else runs of consecutive words — whose gaps (inter-word pauses + the
    pads) drop to the silence floor (RMS scan at 0.1 s: below
    ``VOICE_FLOOR_DB`` or ``VOICE_DROP_DB`` under the speech level). Music
    under the voice keeps the floor high → the line is rejected. The line
    edges are snapped past whisper's word edges while still voiced, padded
    by 0.15 s and written as a mono pcm_s16le wav at the clip's sample
    rate — `out`, default ``<clip stem>_voice.wav`` next to the clip (stable,
    so later chain links reference the same file).

    Returns the wav path, or None when the clip has no music-free line (or no
    audio). v1: one speaking character.
    """
    src = _clip_path(url)
    if not src.is_file():
        raise FileNotFoundError(src)

    def log(msg: str) -> None:
        if verbose > 0:
            print(f'[voice_ref:info] {msg}', flush=True)

    try:
        audio = _audio_mono(src)
    except subprocess.CalledProcessError:
        log(f'{src.name}: no audio stream')
        return None
    if not len(audio):
        return None
    dur = len(audio) / VOICE_SR
    db = _rms_db(audio)
    segments = [s for s in _transcribe_words(audio, model, device) if s]

    cands: list[tuple[int, float, list[dict]]] = []  # (priority, -length, words)
    for words in segments:
        span = words[-1]['end'] - words[0]['start']
        if min_s <= span <= max_s:
            cands.append((0, -span, words))
        for i in range(len(words)):
            for j in range(i, len(words)):
                span = words[j]['end'] - words[i]['start']
                if span > max_s:
                    break
                if span >= min_s and (i, j) != (0, len(words) - 1):
                    cands.append((1, -span, words[i : j + 1]))
    cands.sort(key=lambda c: (c[0], c[1]))
    for _, _neg, words in cands:
        t0, t1, floor, speech = _line_bounds(db, words, dur)
        if t1 - t0 > max_s + 2 * VOICE_PAD_S:
            continue
        text = ''.join(w['word'] for w in words).strip()
        ok = floor <= VOICE_FLOOR_DB or speech - floor >= VOICE_DROP_DB
        log(f'{"take" if ok else "reject"} {t0:.2f}–{t1:.2f} s '
            f'(floor {floor:.0f} dB, speech {speech:.0f} dB): {text[:60]!r}')  # fmt: skip
        if not ok:
            continue
        dst = Path(out) if out else src.with_name(f'{src.stem}_voice.wav')
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-map', '0:a:0',
             '-ss', f'{t0:.3f}', '-to', f'{t1:.3f}', '-ac', '1', '-c:a', 'pcm_s16le', str(dst)],
            check=True,
        )  # fmt: skip
        log(f'wrote {dst} ({t1 - t0:.2f} s)')
        return dst
    log(f'{src.name}: no music-free line of {min_s:g}–{max_s:g} s')
    return None
