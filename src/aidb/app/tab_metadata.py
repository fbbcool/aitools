"""metadata tab of the AIDB scene app (board FEATURE t214).

``⟲ pull`` takes the first media file path of the clipspace (paths only) and
shows everything embedded in the file as readable sections instead of raw
json: Media (preview + file facts), Linked media (every media path found
anywhere in the metadata), Generation, Enhancer (prompt entries, refs,
refdef, steer), Payload, Chain, Parent, Trainer, ComfyUI (models, media
inputs, raw graph/workflow collapsed) and Other (any chunk / container tag
not covered above). Sections only appear when filled.

Data comes from the shared readers ``ait.tools.images.metadata()`` /
``ait.tools.videos.metadata()`` (schema ``ait.image.metadata.v1``) — no
parsing of its own beyond the raw chunk listing for Other.

Linked media render as cards: image thumb, video first frame + ▶, and icon
tiles for audio 🔊, missing file ⛔, remote url 🌐 and other files 📄. A
click on a local media card loads that file into the tab; ◀ goes back.

Card clicks / 📋 copies are handled in METADATA_HEAD (injected into <head>,
since <script> in gr.HTML does not run). All elem_ids / classes are
``md-``-prefixed.
"""

from __future__ import annotations

import base64
import html
import io
import json
import math
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Final

import av
import gradio as gr
import pyperclip
from PIL import Image, ImageOps

from ait.tools import images as imgs
from ait.tools import role as roles
from ait.tools import videos as vids
from ait.tools.files import SUFFIX_AUD, SUFFIX_IMG, SUFFIX_VID, is_aud, is_img, is_vid

THUMB: Final = 200  # linked-media card thumbs
PREVIEW: Final = 720  # main preview
MAX_HISTORY: Final = 50
LONG_STR: Final = 160  # longer strings go into a collapsed <details>
RAW_MAX: Final = 200_000  # raw json blocks are cut beyond this many chars
MAX_PULL_LINES: Final = 50
NOMETA_SUFFIX: Final = '-nometa'

# chunks / tags the v1 reader consumes (shown in their sections, not in Other)
CONSUMED: Final = {
    'prompt',
    'workflow',
    imgs.PARENT_METADATA_CHUNK,
    imgs.PAYLOAD_CHUNK,
    imgs.TRAINER_META_CHUNK,
    imgs.ROLE_CHUNK,  # edited in the role row (t215)
}

TILES: Final = {
    'audio': ('🔊', 'audio'),
    'missing': ('⛔', 'n/a'),
    'remote': ('🌐', 'remote'),
    'other': ('📄', 'file'),
}

_esc = html.escape


# ---------------------------------------------------------------------- #
# media helpers
# ---------------------------------------------------------------------- #
def is_media(url: str | Path) -> bool:
    """Existing local image / video / audio file."""
    return is_img(url) or is_vid(url) or is_aud(url)


def suffix_kind(url: str | Path) -> str | None:
    """image | video | audio by suffix alone (file need not exist), else None."""
    suf = Path(str(url).split('?', 1)[0]).suffix.lower().lstrip('.')
    for kind, sufs in (('image', SUFFIX_IMG), ('video', SUFFIX_VID), ('audio', SUFFIX_AUD)):
        if suf in sufs:
            return kind
    return None


def path_from_clipspace(text: str | None) -> str | None:
    """First line of the clipspace that is an existing local media file (paths only)."""
    lines = [ln.strip() for ln in (text or '').splitlines() if ln.strip()]
    for ln in lines[:MAX_PULL_LINES]:
        ln = ln.strip('\'"')
        if ln.startswith('file://'):
            ln = ln[len('file://') :]
        p = Path(ln).expanduser()
        if p.is_absolute() and p.is_file() and is_media(p):
            return str(p)
    return None


def media_kind(url: str) -> str:
    """image | video | audio | remote | missing | other."""
    if url.startswith(('http://', 'https://')):
        return 'remote'
    p = Path(url).expanduser()
    if not p.is_file():
        return 'missing'
    return suffix_kind(p) or 'other'


def looks_like_media_ref(s: Any) -> bool:
    """A string value that refers to a media file (local absolute path or url)."""
    if not isinstance(s, str) or '\n' in s or len(s) > 1024:
        return False
    s = s.strip()
    if not (s.startswith(('/', '~', 'http://', 'https://'))):
        return False
    return suffix_kind(s) is not None


def _pil_to_b64(im: Image.Image, size: int) -> str:
    im = im.convert('RGB')
    im.thumbnail((size, size))
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=85)
    return base64.b64encode(buf.getvalue()).decode('ascii')


def _video_frame(p: Path) -> Image.Image | None:
    try:
        with av.open(str(p)) as c:
            for frame in c.decode(video=0):
                return frame.to_image()
    except Exception:  # noqa: BLE001 - unreadable -> no preview
        return None
    return None


class _Thumbs:
    """(path, mtime, size) -> base64 jpeg cache."""

    def __init__(self) -> None:
        self._cache: dict[tuple, str | None] = {}

    def get(self, url: str, size: int) -> str | None:
        p = Path(url).expanduser()
        try:
            st = p.stat()
        except OSError:
            return None
        key = (str(p), st.st_mtime, size)
        if key not in self._cache:
            self._cache[key] = self._make(p, size)
        return self._cache[key]

    @staticmethod
    def _make(p: Path, size: int) -> str | None:
        try:
            if is_img(p):
                with Image.open(p) as src:
                    src.draft('RGB', (size, size))
                    return _pil_to_b64(ImageOps.exif_transpose(src), size)
            if is_vid(p):
                im = _video_frame(p)
                return _pil_to_b64(im, size) if im is not None else None
        except Exception:  # noqa: BLE001
            return None
        return None


# ---------------------------------------------------------------------- #
# file facts / raw chunks
# ---------------------------------------------------------------------- #
def _fmt_bytes(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024
    return str(n)


def _fmt_ts(ts: float | None) -> str | None:
    if not isinstance(ts, (int, float)):
        return None
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))


def _ratio(w: int, h: int) -> str | None:
    if not w or not h:
        return None
    g = math.gcd(w, h)
    return f'{w // g}:{h // g} ({w / h:.3f})'


def file_facts(path: str) -> tuple[dict[str, Any], dict[str, str]]:
    """(facts for the Media section, raw embedded chunks / container tags)."""
    p = Path(path)
    st = p.stat()
    facts: dict[str, Any] = {
        'kind': media_kind(path),
        'file size': _fmt_bytes(st.st_size),
        'modified': _fmt_ts(st.st_mtime),
    }
    raw: dict[str, str] = {}
    if is_img(p):
        try:
            with Image.open(p) as im:
                facts['format'] = im.format
                facts['mode'] = im.mode
                facts['w × h'] = f'{im.width} × {im.height}'
                facts['ratio'] = _ratio(im.width, im.height)
                for k, v in (im.info or {}).items():
                    raw[str(k)] = v if isinstance(v, str) else repr(v)
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            with av.open(str(p)) as c:
                facts['format'] = c.format.long_name or c.format.name
                if c.duration:
                    facts['duration'] = f'{c.duration / 1_000_000:.2f} s'
                for s in c.streams.video[:1]:
                    facts['w × h'] = f'{s.width} × {s.height}'
                    facts['ratio'] = _ratio(s.width or 0, s.height or 0)
                    if s.average_rate:
                        facts['fps'] = f'{float(s.average_rate):.3f}'.rstrip('0').rstrip('.')
                    facts['video codec'] = s.codec_context.name
                    if s.frames:
                        facts['frames'] = s.frames
                auds = [
                    f'{s.codec_context.name} {s.sample_rate} Hz {s.channels}ch'
                    for s in c.streams.audio
                ]
                if auds:
                    facts['audio'] = ' · '.join(auds)
                raw = {k.lower(): v for k, v in (c.metadata or {}).items()}
        except Exception:  # noqa: BLE001
            pass
    return facts, raw


def read_metadata(path: str) -> dict | None:
    try:
        if is_img(path):
            return imgs.metadata(path)
        if is_vid(path):
            return vids.metadata(path)
    except Exception:  # noqa: BLE001 - a broken chunk never breaks the tab
        return None
    return None


def has_content(md: dict | None) -> bool:
    """True when the v1 dict carries anything beyond the file facts."""
    if not md:
        return False
    comfy = md.get('comfy') or {}
    gen = md.get('generation') or {}
    return any(
        (
            comfy.get('prompt_graph'),
            comfy.get('workflow'),
            md.get('enhancer'),
            md.get('payload'),
            md.get('parent'),
            md.get('loras'),
            md.get('seed') is not None,
            gen.get('prompt'),
        )
    )


def collect_media(obj: Any, where: str = '', out: dict[str, list[str]] | None = None):
    """Every media reference anywhere in `obj` -> {url: [json paths]} (insertion order)."""
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            collect_media(v, f'{where}.{k}' if where else str(k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            collect_media(v, f'{where}[{i}]', out)
    elif looks_like_media_ref(obj):
        out.setdefault(obj.strip(), []).append(where)
    return out


# ---------------------------------------------------------------------- #
# metaless copy
# ---------------------------------------------------------------------- #
def nometa_path(src: str | Path, dst_dir: str | Path | None = None) -> Path:
    """``<stem>-nometa<suffix>`` next to the original (or in `dst_dir`)."""
    src = Path(src)
    return Path(dst_dir or src.parent) / f'{src.stem}{NOMETA_SUFFIX}{src.suffix}'


def _metaless_image(src: Path, dst: Path) -> None:
    """Re-save the pixels only: no text chunks, EXIF, XMP, ICC (orientation baked in)."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode == 'P':
            im = im.convert('RGBA')
        clean = Image.new(im.mode, im.size)
        clean.paste(im)
    fmt = (Image.registered_extensions().get(src.suffix.lower()) or 'PNG').upper()
    kw: dict[str, Any] = {}
    if fmt == 'JPEG':
        clean = clean.convert('RGB')
        kw = {'quality': 95, 'subsampling': 0}
    elif fmt == 'WEBP':
        kw = {'lossless': True}
    clean.save(dst, format=fmt, **kw)


def _metaless_av(src: Path, dst: Path) -> None:
    """Remux (no re-encode) the main video stream + audio streams; drop container /
    stream / chapter metadata, anchor streams, attachments and data streams."""
    keep: list[int] = []
    with av.open(str(src)) as c:
        main = [
            s.index
            for s in c.streams.video
            if not vids._stream_title(s).startswith(vids.ANCHOR_TITLE_PREFIX)
        ]
        keep = main[:1] + [s.index for s in c.streams.audio]
    if not keep:
        raise ValueError(f'no audio/video stream in {src.name}')
    maps = [a for i in keep for a in ('-map', f'0:{i}')]
    cmd = ['ffmpeg', '-v', 'error', '-y', '-i', str(src), *maps, '-c', 'copy',
           '-map_metadata', '-1', '-map_chapters', '-1',
           '-map_metadata:s:v', '-1', '-map_metadata:s:a', '-1',
           '-fflags', '+bitexact', '-flags:v', '+bitexact', '-flags:a', '+bitexact',
           str(dst)]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def metaless_copy(src: str | Path, dst_dir: str | Path | None = None) -> Path:
    """Fully metadata-free copy of an image / video / audio file at
    ``<stem>-nometa<suffix>`` in the original's dir (or `dst_dir`), overwriting.
    Returns the new path."""
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    kind = suffix_kind(src)
    if kind is None:
        raise ValueError(f'not a media file: {src.name}')
    dst = nometa_path(src, dst_dir)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f'.{dst.stem}.tmp{dst.suffix}')
    try:
        (_metaless_image if kind == 'image' else _metaless_av)(src, tmp)
        tmp.replace(dst)
    finally:
        tmp.unlink(missing_ok=True)
    return dst


# ---------------------------------------------------------------------- #
# html rendering
# ---------------------------------------------------------------------- #
class MetadataView:
    """Builds the tab HTML for one file. Pure (no gradio) — unit-testable."""

    def __init__(self, thumbs: _Thumbs | None = None) -> None:
        self._thumbs = thumbs or _Thumbs()
        self._gen_prompt: str | None = None
        self.has_md = False

    # -- atoms ---------------------------------------------------------- #
    @staticmethod
    def copy_btn(value: Any, title: str = 'copy') -> str:
        if value is None or value == '':
            return ''
        v = _esc(str(value), quote=True)
        return f'<button type="button" class="md-copy" data-v="{v}" title="{title}">📋</button>'

    @staticmethod
    def chips(items: list) -> str:
        return ''.join(f'<span class="md-chip">{_esc(str(x))}</span>' for x in items)

    def card(self, url: str, caption: str = '', sub: str = '') -> str:
        kind = media_kind(url)
        name = url.rstrip('/').rsplit('/', 1)[-1]
        b64 = self._thumbs.get(url, THUMB) if kind in ('image', 'video') else None
        if b64:
            badge = '<span class="md-play">▶</span>' if kind == 'video' else ''
            pic = f'<img src="data:image/jpeg;base64,{b64}" loading="lazy">{badge}'
        else:
            icon, label = TILES.get(kind, TILES['other'])
            if kind in ('image', 'video'):  # exists but unreadable
                icon, label = '🖼' if kind == 'image' else '🎬', 'no preview'
            pic = f'<div class="md-tile"><span>{icon}</span><small>{label}</small></div>'
        loadable = kind in ('image', 'video', 'audio')
        cls = 'md-card md-load' if loadable else 'md-card'
        data = f' data-url="{_esc(url, quote=True)}"' if loadable else ''
        tip = _esc(url, quote=True)
        cap = f'<div class="md-cap">{_esc(caption)}</div>' if caption else ''
        subl = f'<div class="md-sub">{_esc(sub)}</div>' if sub else ''
        return (
            f'<div class="{cls}"{data} title="{tip}"><div class="md-pic">{pic}</div>'
            f'{cap}<div class="md-name">{_esc(name)}{self.copy_btn(url, "copy path")}</div>'
            f'{subl}</div>'
        )

    def cards(self, items: list[tuple[str, str, str]]) -> str:
        if not items:
            return ''
        return '<div class="md-cards">' + ''.join(self.card(*it) for it in items) + '</div>'

    def value(self, v: Any, depth: int = 0) -> str:
        """Generic readable rendering of any json value."""
        if v is None:
            return '<span class="md-null">—</span>'
        if isinstance(v, bool):
            return '✔' if v else '✘'
        if isinstance(v, (int, float)):
            return _esc(str(v))
        if isinstance(v, str):
            if looks_like_media_ref(v):
                return self.cards([(v, '', '')])
            if '\n' in v or len(v) > LONG_STR:
                head = _esc(v.strip().splitlines()[0][:LONG_STR] if v.strip() else '')
                return (
                    f'<details class="md-long"><summary>{head}…</summary>'
                    f'<pre>{_esc(v)}</pre>{self.copy_btn(v)}</details>'
                )
            return _esc(v)
        if isinstance(v, list):
            if not v:
                return '<span class="md-null">[ ]</span>'
            if all(isinstance(x, (str, int, float)) and not looks_like_media_ref(x) for x in v):
                if all(len(str(x)) <= 40 for x in v):
                    return self.chips(v)
            if all(isinstance(x, dict) for x in v) and depth < 6:
                return ''.join(
                    f'<div class="md-item"><span class="md-idx">#{i}</span>{self.kv(x, depth + 1)}</div>'
                    for i, x in enumerate(v)
                )
            return (
                '<ol class="md-list">'
                + ''.join(f'<li>{self.value(x, depth + 1)}</li>' for x in v)
                + '</ol>'
            )
        if isinstance(v, dict):
            if depth >= 6:
                return self.raw_json(v)
            return self.kv(v, depth + 1)
        return _esc(repr(v))

    def kv(self, d: dict, depth: int = 0, skip: tuple = ()) -> str:
        rows = [
            f'<tr><th>{_esc(str(k))}</th><td>{self.value(v, depth)}</td></tr>'
            for k, v in d.items()
            if k not in skip
        ]
        return f'<table class="md-kv">{"".join(rows)}</table>' if rows else ''

    @staticmethod
    def raw_json(obj: Any, title: str = 'raw json') -> str:
        s = json.dumps(obj, indent=1, ensure_ascii=False, default=str)
        cut = len(s) > RAW_MAX
        s = s[:RAW_MAX]
        note = ' (cut)' if cut else ''
        return (
            f'<details class="md-raw"><summary>{_esc(title)}{note}</summary>'
            f'<pre>{_esc(s)}</pre></details>'
        )

    @staticmethod
    def section(title: str, body: str, open_: bool = True, note: str = '') -> str:
        if not body:
            return ''
        op = ' open' if open_ else ''
        n = f' <span class="md-note">{_esc(note)}</span>' if note else ''
        return (
            f'<details class="md-sec"{op}><summary>{_esc(title)}{n}</summary>'
            f'<div class="md-body">{body}</div></details>'
        )

    # -- sections ------------------------------------------------------- #
    def _sec_media(self, path: str, facts: dict, md: dict | None) -> str:
        kind = facts.get('kind')
        b64 = self._thumbs.get(path, PREVIEW) if kind in ('image', 'video') else None
        if b64:
            badge = '<span class="md-play big">▶</span>' if kind == 'video' else ''
            pic = f'<img src="data:image/jpeg;base64,{b64}">{badge}'
        else:
            icon, label = TILES['audio'] if kind == 'audio' else ('🖼', 'no preview')
            pic = f'<div class="md-tile big"><span>{icon}</span><small>{label}</small></div>'
        rows = dict(facts)
        if md:
            rows['created'] = _fmt_ts((md.get('image') or {}).get('timestamp_created'))
            rows['schema'] = md.get('schema')
        else:
            rows['schema'] = 'no embedded metadata'
        name = Path(path).name
        return (
            '<div class="md-media">'
            f'<div class="md-preview">{pic}</div>'
            f'<div><div class="md-title">{_esc(name)}{self.copy_btn(path, "copy path")}</div>'
            f'<div class="md-path">{_esc(path)}</div>'
            f'{self.kv({k: v for k, v in rows.items() if v is not None})}</div></div>'
        )

    def _sec_linked(self, md: dict, path: str) -> str:
        found = collect_media({k: v for k, v in md.items() if k != 'url'})
        found.pop(path, None)
        items = []
        for url, wheres in found.items():
            sub = wheres[0] + (f' +{len(wheres) - 1}' if len(wheres) > 1 else '')
            items.append((url, '', sub))
        return self.cards(items)

    def _sec_generation(self, md: dict) -> str:
        gen = md.get('generation') or {}
        inh = set(md.get('inherited') or [])
        parts = []
        prompt = gen.get('prompt')
        if prompt:
            parts.append(
                f'<div class="md-label">prompt{self.copy_btn(prompt, "copy prompt")}</div>'
                f'<pre class="md-prompt">{_esc(prompt)}</pre>'
            )
        facts = {
            'prompt_index': gen.get('prompt_index'),
            'prompt_offset': gen.get('prompt_offset'),
            'seed': md.get('seed'),
        }
        rows = ''.join(
            f'<tr><th>{k}</th><td>{_esc(str(v))}'
            f'{self.copy_btn(v) if k == "seed" else ""}'
            f'{" <span class=md-inh>inherited</span>" if k in inh or (k != "seed" and "generation" in inh) else ""}'
            '</td></tr>'
            for k, v in facts.items()
            if v is not None
        )
        if rows:
            parts.append(f'<table class="md-kv">{rows}</table>')
        loras = md.get('loras') or []
        if loras:
            lrows = ''.join(
                f'<tr><td>{_esc(str(lo.get("name")))}{self.copy_btn(lo.get("name"))}</td>'
                f'<td class="md-num">{_esc(str(lo.get("strength")))}</td>'
                f'<td class="md-dim">{_esc(str(lo.get("source", "")))}</td></tr>'
                for lo in loras
            )
            flag = ' <span class="md-inh">inherited</span>' if 'loras' in inh else ''
            parts.append(
                f'<div class="md-label">LoRAs{flag}</div><table class="md-grid">'
                '<tr><th>name</th><th>strength</th><th>source</th></tr>'
                f'{lrows}</table>'
            )
        return ''.join(parts)

    def _refs_cards(self, refs: list) -> str:
        items = []
        for r in refs or []:
            if not isinstance(r, dict) or not r.get('url'):
                continue
            cap = ' · '.join(
                str(x)
                for x in (
                    f'slot {r["slot"]}' if r.get('slot') else None,
                    r.get('role') or r.get('desc'),
                )
                if x
            )
            sub = ' · '.join(
                str(x)
                for x in (
                    r.get('media') or r.get('kind'),
                    f'use {r["use"]}' if r.get('use') else 'use open',
                    f'pic {r["pic"]}' if r.get('pic') else None,
                    '🎭 mask' if r.get('mask') else None,
                    f'{r["size"]["w"]}×{r["size"]["h"]}'
                    if isinstance(r.get('size'), dict)
                    else None,
                )
                if x
            )
            items.append((str(r['url']), cap, sub))
        return self.cards(items)

    def _prompt_entry(self, e: Any, rendered: bool) -> str:
        if not isinstance(e, dict):
            return self.value(e)
        parts = []
        if e.get('prompt'):
            pr = str(e['prompt'])
            cp = self.copy_btn(pr, 'copy prompt')
            if self._gen_prompt and pr.strip() == self._gen_prompt.strip():
                parts.append(
                    f'<details class="md-long"><summary>prompt = generation prompt</summary>'
                    f'<pre class="md-prompt">{_esc(pr)}</pre>{cp}</details>'
                )
            else:
                parts.append(
                    f'<div class="md-label">prompt{cp}</div><pre class="md-prompt">{_esc(pr)}</pre>'
                )
        for k in ('concepts', 'triggers'):
            if e.get(k):
                parts.append(f'<div class="md-label">{k}</div>{self.chips(e[k])}')
        if e.get('refs'):
            parts.append(f'<div class="md-label">refs</div>{self._refs_cards(e["refs"])}')
        link = e.get('continue')
        if isinstance(link, dict) and link.get('url'):
            parts.append(
                '<div class="md-label">continue</div>'
                + self.cards(
                    [(str(link['url']), f'{link.get("dir")}-vid', f'pin {link.get("pin")}')]
                )
            )
        rd = e.get('refdef')
        if isinstance(rd, dict):
            head = {k: rd.get(k) for k in ('verb', 'kind', 'auto', 'origin', 'schema_id')}
            body = self.kv({k: v for k, v in head.items() if v is not None})
            if rd.get('text'):
                body += f'<div class="md-label">text</div><pre class="md-prompt">{_esc(rd["text"])}</pre>'
            body += self._refs_cards(rd.get('refs') or [])
            rest = {k: v for k, v in rd.items() if k not in head and k not in ('text', 'refs')}
            body += self.kv(rest)
            parts.append(self.section('refdef', body, open_=False))
        rest = {
            k: v
            for k, v in e.items()
            if k not in ('prompt', 'concepts', 'triggers', 'refs', 'continue', 'refdef')
        }
        parts.append(self.kv(rest))
        cls = 'md-entry md-rendered' if rendered else 'md-entry'
        return f'<div class="{cls}">{"".join(parts)}</div>'

    def _prompts_block(self, name: str, sec: Any, rendered_idx: int | None) -> str:
        if not isinstance(sec, dict):
            return ''
        data = sec.get('prompt_data') or []
        cur = sec.get('current')
        head = (
            f'{name} · {sec.get("type", "?")} · {len(data)} entr{"y" if len(data) == 1 else "ies"}'
        )
        entries = []
        for i, e in enumerate(data):
            rendered = i == (rendered_idx if rendered_idx is not None else cur)
            tag = ' ★ rendered' if rendered else ''
            tag += ' · current' if i == cur else ''
            entries.append(
                self.section(f'#{i}{tag}', self._prompt_entry(e, rendered), open_=rendered)
            )
        rest = {k: v for k, v in sec.items() if k not in ('prompt_data', 'current', 'type')}
        return self.section(head, ''.join(entries) + self.kv(rest))

    def _sec_enhancer(self, enh: dict, rendered_idx: int | None) -> str:
        head = {k: enh.get(k) for k in ('schema_id', 'scene_id', 'rev', 'prompt_index')}
        rows = ''.join(
            f'<tr><th>{k}</th><td>{_esc(str(v))}{self.copy_btn(v) if k == "scene_id" else ""}</td></tr>'
            for k, v in head.items()
            if v is not None
        )
        parts = [f'<table class="md-kv">{rows}</table>']
        if enh.get('url'):
            parts.append(
                '<div class="md-label">url</div>' + self.cards([(str(enh['url']), '', '')])
            )
        prompt_keys = [k for k, v in enh.items() if isinstance(v, dict) and 'prompt_data' in v]
        for k in prompt_keys:
            parts.append(self._prompts_block(k, enh[k], rendered_idx))
        for k in ('steer', 'steer_applied'):
            if enh.get(k):
                parts.append(self.section(k, self.kv(enh[k]), open_=False))
        rest = {
            k: v
            for k, v in enh.items()
            if k not in head and k not in prompt_keys and k not in ('url', 'steer', 'steer_applied')
        }
        parts.append(self.kv(rest))
        return ''.join(parts)

    def _sec_chain(self, path: str) -> str:
        if not is_vid(path):
            return ''
        try:
            link = vids.chain_link(path)
        except Exception:  # noqa: BLE001
            link = None
        parts = []
        if link:
            parts.append(
                '<div class="md-label">continues</div>'
                + self.cards([(link['url'], f'{link["dir"]}-vid', f'pin {link["pin"]}')])
            )
            try:
                clips, root, _pins = vids.chain_clips(path)
            except Exception:  # noqa: BLE001 - broken chain -> link card only
                clips = []
            if len(clips) > 1:
                items = [
                    (str(c), f'{i + 1}{" · root" if i == root else ""}', '')
                    for i, c in enumerate(clips)
                ]
                parts.append('<div class="md-label">chain (play order)</div>' + self.cards(items))
        return ''.join(parts)

    def _sec_parent(self, parent: dict, own_enh: Any, rendered_idx: int | None) -> str:
        skip = ('enhancer',)
        parts = [self.kv(parent, skip=skip)]
        penh = parent.get('enhancer')
        if isinstance(penh, dict):
            same = isinstance(own_enh, dict) and all(penh.get(k) == own_enh.get(k) for k in own_enh)
            if same:
                extra = {k: v for k, v in penh.items() if k not in own_enh}
                parts.append('<div class="md-label">enhancer = own enhancer, plus</div>')
                parts.append(self.kv(extra))
            else:
                parts.append(self.section('enhancer', self._sec_enhancer(penh, rendered_idx)))
        return ''.join(parts)

    def _sec_comfy(self, comfy: dict) -> str:
        graph = comfy.get('prompt_graph')
        wf = comfy.get('workflow')
        parts = []
        if isinstance(graph, dict):
            nodes = {k: n for k, n in graph.items() if isinstance(n, dict)}
            types = Counter(str(n.get('class_type')) for n in nodes.values())
            parts.append(
                f'<div class="md-label">{len(nodes)} nodes</div>'
                + self.chips([f'{t} ×{c}' if c > 1 else t for t, c in types.most_common()])
            )
            models, media = [], []
            for nid, n in nodes.items():
                for k, v in (n.get('inputs') or {}).items():
                    if not isinstance(v, str):
                        continue
                    if looks_like_media_ref(v):
                        media.append((v, str(n.get('class_type')), f'node {nid} · {k}'))
                    elif v.endswith(('.safetensors', '.ckpt', '.pt', '.pth', '.gguf', '.bin')):
                        models.append((v, str(n.get('class_type')), f'{nid}/{k}'))
            if models:
                mrows = ''.join(
                    f'<tr><td>{_esc(m)}{self.copy_btn(m)}</td><td>{_esc(c)}</td>'
                    f'<td class="md-dim">{_esc(s)}</td></tr>'
                    for m, c, s in models
                )
                parts.append(
                    '<div class="md-label">models</div><table class="md-grid">'
                    f'<tr><th>file</th><th>node</th><th>input</th></tr>{mrows}</table>'
                )
            if media:
                parts.append('<div class="md-label">media inputs</div>' + self.cards(media))
            parts.append(self.raw_json(graph, 'prompt graph (API)'))
        if isinstance(wf, dict):
            parts.append(self.raw_json(wf, f'workflow ({len(wf.get("nodes") or [])} nodes)'))
        return ''.join(parts)

    def _sec_other(self, raw: dict[str, str]) -> str:
        rows = {}
        for k, v in raw.items():
            if k in CONSUMED:
                continue
            if k.startswith(imgs.EMBED_CHUNK_PREFIX):
                try:
                    e = json.loads(v)
                    rows[k] = {
                        'model': e.get('model'),
                        'dim': e.get('dim'),
                        'schema_id': e.get('schema_id'),
                    }
                    continue
                except Exception:  # noqa: BLE001
                    pass
            try:
                parsed = json.loads(v) if isinstance(v, str) and v[:1] in '{[' else v
            except Exception:  # noqa: BLE001
                parsed = v
            rows[k] = parsed
        return self.kv(rows)

    # -- page ----------------------------------------------------------- #
    def render(self, path: str | None) -> str:
        if not path:
            return '<div id="md-root" class="md-empty">⟲ pull a media file path</div>'
        if not Path(path).is_file():
            return f'<div id="md-root" class="md-empty">⛔ {_esc(path)}</div>'
        facts, raw = file_facts(path)
        md = read_metadata(path)
        self._gen_prompt = None
        self.has_md = has_content(md)
        if not self.has_md:
            md = None
        out = [self.section('Media', self._sec_media(path, facts, md))]
        if md:
            rendered_idx = (md.get('generation') or {}).get('prompt_index')
            self._gen_prompt = (md.get('generation') or {}).get('prompt')
            out.append(self.section('Linked media', self._sec_linked(md, path)))
            out.append(self.section('Generation', self._sec_generation(md)))
            enh = md.get('enhancer')
            if isinstance(enh, dict):
                flag = 'inherited' if 'enhancer' in (md.get('inherited') or []) else ''
                out.append(
                    self.section('Enhancer', self._sec_enhancer(enh, rendered_idx), note=flag)
                )
            if md.get('payload'):
                out.append(self.section('Payload', self.value(md['payload']), open_=False))
            out.append(self.section('Chain', self._sec_chain(path)))
            if isinstance(md.get('parent'), dict):
                out.append(
                    self.section(
                        'Parent', self._sec_parent(md['parent'], enh, rendered_idx), open_=False
                    )
                )
            out.append(self.section('ComfyUI', self._sec_comfy(md.get('comfy') or {}), open_=False))
        tmeta = imgs.trainer_meta_from_info(raw) if raw else None
        if tmeta:
            out.append(self.section('Trainer', self.kv(tmeta)))
        out.append(self.section('Other', self._sec_other(raw), open_=False))
        return f'<div id="md-root">{"".join(out)}</div>'


# ---------------------------------------------------------------------- #
# tab
# ---------------------------------------------------------------------- #
class MetadataTab:
    def __init__(self, verbose: int = 0) -> None:
        self._view = MetadataView()
        self._verbose = verbose

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[metadata_tab:{level}] {msg}')

    def _render(self, path: str) -> str:
        try:
            return self._view.render(path)
        except Exception as e:  # noqa: BLE001 - never break the tab
            self._log(f'render {path} failed: {e}', 'error')
            return f'<div id="md-root" class="md-empty">⚠ {_esc(str(e))}</div>'

    def _load(self, path: str, cur: str | None, hist: list[str] | None):
        hist = list(hist or [])
        if cur and cur != path:
            hist = (hist + [cur])[-MAX_HISTORY:]
        page = self._render(path)
        role_text = roles.descr(roles.role(path))
        if not self._view.has_md and not role_text:
            gr.Info('no embedded metadata', duration=1)
        return path, hist, page, gr.update(interactive=bool(hist)), role_text

    def _on_pull(self, cur: str | None, hist: list[str] | None):
        path = path_from_clipspace(pyperclip.paste())
        if path is None:
            gr.Info('no media file path in the clipspace', duration=1)
            return (gr.update(),) * 5
        return self._load(path, cur, hist)

    def _on_card(self, url: str | None, cur: str | None, hist: list[str] | None):
        url = (url or '').strip()
        if not url or not Path(url).is_file():
            gr.Info('⛔ n/a', duration=1)
            return (gr.update(),) * 5
        return self._load(url, cur, hist)

    def _on_back(self, hist: list[str] | None):
        hist = list(hist or [])
        if not hist:
            return gr.update(), hist, gr.update(), gr.update(interactive=False), gr.update()
        path = hist.pop()
        return (
            path,
            hist,
            self._render(path),
            gr.update(interactive=bool(hist)),
            roles.descr(roles.role(path)),
        )

    def _on_role(self, cur: str | None, text: str | None, remove: bool = False):
        """💾 writes / 🗑 removes the embedded role (t215); re-renders from the file."""
        if not cur:
            gr.Info('nothing loaded', duration=1)
            return gr.update(), gr.update()
        if not roles.supported(cur):
            gr.Info(f'role unsupported for {Path(cur).suffix or "this file"}', duration=1.5)
            return gr.update(), gr.update()
        try:
            stored = roles.role_set(cur, None if remove else {'descr': text or ''})
        except Exception as e:  # noqa: BLE001 - report, never break the tab
            self._log(f'role {cur} failed: {e}', 'error')
            gr.Warning(f'role failed: {e}')
            return gr.update(), gr.update()
        gr.Info('role saved' if stored else 'role removed', duration=1)
        return self._render(cur), roles.descr(roles.role(cur))

    def _on_metaless(self, cur: str | None):
        if not cur:
            gr.Info('nothing loaded', duration=1)
            return
        try:
            dst = metaless_copy(cur)
        except Exception as e:  # noqa: BLE001 - report, never break the tab
            self._log(f'metaless {cur} failed: {e}', 'error')
            gr.Warning(f'metaless failed: {e}')
            return
        gr.Info(f'saved {dst.name}', duration=1.5)

    def build(self) -> None:
        with gr.Tab('metadata', elem_id='md_tab'):
            hist = gr.State([])
            # fixed top-left stack (like refdef's t207 buttons)
            with gr.Row(elem_id='md-actions'):
                pull_btn = gr.Button('⟲ pull', variant='primary', elem_id='md-pull')
                back_btn = gr.Button('◀', elem_id='md-back', interactive=False)
                metaless_btn = gr.Button('metaless', elem_id='md-metaless')
            url_box = gr.Textbox(show_label=False, interactive=False, container=False)
            with gr.Row(equal_height=True):
                with gr.Column(scale=0, min_width=60):
                    gr.Markdown('role:')
                role_box = gr.Textbox(
                    show_label=False, container=False, lines=2, max_lines=8, scale=8
                )
                role_save = gr.Button('💾', scale=0, min_width=40)
                role_del = gr.Button('🗑', scale=0, min_width=40)
            bus = gr.Textbox(visible='hidden', elem_id='md-bus')
            go = gr.Button('md go', visible='hidden', elem_id='md-go')
            page = gr.HTML(self._view.render(None))

            outs = [url_box, hist, page, back_btn, role_box]
            pull_btn.click(self._on_pull, [url_box, hist], outs)
            go.click(self._on_card, [bus, url_box, hist], outs)
            back_btn.click(self._on_back, [hist], outs)
            metaless_btn.click(self._on_metaless, [url_box], [])
            role_save.click(self._on_role, [url_box, role_box], [page, role_box])
            role_del.click(
                lambda cur: self._on_role(cur, None, remove=True), [url_box], [page, role_box]
            )


METADATA_HEAD = r"""
<style>
/* fixed top-left button stack (hidden with the tab like refdef's) */
#md-actions { display: contents !important; }
#md-pull, #md-back, #md-metaless {
  position: fixed !important; left: 8px; z-index: 900; height: 40px;
  width: 110px !important; min-width: 110px !important; max-width: 110px !important;
  flex: none !important; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5); }
#md-pull { top: 8px; }
#md-back { top: 56px; }
#md-metaless { top: 104px; background: #2e7d32 !important; border-color: #2e7d32 !important;
  color: #fff !important; }
#md-metaless:hover { background: #388e3c !important; }
#md-root { display: flex; flex-direction: column; gap: 6px; }
#md-root.md-empty, .md-empty { opacity: 0.6; padding: 24px; text-align: center; }
#md-root details.md-sec { border: 1px solid var(--border-color-primary); border-radius: 6px; }
#md-root details.md-sec > summary { cursor: pointer; padding: 4px 8px; font-weight: 600; }
#md-root details.md-sec details.md-sec > summary { font-weight: 500; }
#md-root .md-body { padding: 4px 8px 8px; }
#md-root .md-note, #md-root .md-inh { font-size: 0.75em; padding: 0 6px; border-radius: 8px;
  background: #b26a00; color: #fff; font-weight: 400; }
#md-root .md-media { display: grid; grid-template-columns: minmax(200px, 45%) 1fr; gap: 12px; }
#md-root .md-preview { position: relative; display: flex; justify-content: center; }
#md-root .md-preview img { max-width: 100%; max-height: 70vh; object-fit: contain; border-radius: 4px; }
#md-root .md-title { font-weight: 600; font-size: 1.05em; }
#md-root .md-path { font-family: monospace; font-size: 0.8em; opacity: 0.6; word-break: break-all;
  margin-bottom: 6px; }
#md-root table { border-collapse: collapse; font-size: 0.88em; }
#md-root table.md-kv { width: 100%; }
#md-root table.md-kv > tbody > tr > th { text-align: left; vertical-align: top; white-space: nowrap;
  opacity: 0.7; font-weight: 500; padding: 2px 10px 2px 0; width: 1%; }
#md-root table.md-kv > tbody > tr > td { padding: 2px 0; word-break: break-word; }
#md-root table.md-grid th, #md-root table.md-grid td { padding: 2px 8px; text-align: left;
  border-bottom: 1px solid var(--border-color-primary); }
#md-root .md-num { text-align: right; }
#md-root .md-dim, #md-root .md-null { opacity: 0.55; }
#md-root .md-label { font-size: 0.8em; opacity: 0.7; margin: 6px 0 2px; }
#md-root pre { white-space: pre-wrap; word-break: break-word; font-size: 0.85em; margin: 2px 0;
  max-height: 50vh; overflow: auto; }
#md-root pre.md-prompt { background: var(--background-fill-secondary); padding: 6px;
  border-radius: 4px; }
#md-root details.md-long > summary, #md-root details.md-raw > summary { cursor: pointer; opacity: 0.8; }
#md-root .md-chip { display: inline-block; font-size: 0.8em; padding: 0 6px; margin: 1px 2px;
  border-radius: 8px; border: 1px solid var(--border-color-primary); }
#md-root .md-item { display: flex; gap: 6px; border-top: 1px dashed var(--border-color-primary);
  padding: 2px 0; }
#md-root .md-idx { opacity: 0.5; font-size: 0.8em; }
#md-root .md-entry.md-rendered { border-left: 3px solid #2e7d32; padding-left: 6px; }
#md-root .md-cards { display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0; }
#md-root .md-card { width: 150px; border: 1px solid var(--border-color-primary); border-radius: 6px;
  padding: 4px; font-size: 0.75em; display: flex; flex-direction: column; gap: 2px; }
#md-root .md-card.md-load { cursor: pointer; }
#md-root .md-card.md-load:hover { border-color: #2e7d32; }
#md-root .md-pic { position: relative; height: 120px; display: flex; align-items: center;
  justify-content: center; overflow: hidden; }
#md-root .md-pic img { max-width: 100%; max-height: 100%; object-fit: contain; }
#md-root .md-play { position: absolute; font-size: 28px; color: #fff;
  text-shadow: 0 0 6px #000; pointer-events: none; }
#md-root .md-play.big { font-size: 64px; top: 50%; left: 50%; transform: translate(-50%, -50%); }
#md-root .md-tile { width: 100%; height: 100%; display: flex; flex-direction: column;
  align-items: center; justify-content: center; background: var(--background-fill-secondary);
  border-radius: 4px; }
#md-root .md-tile span { font-size: 40px; }
#md-root .md-tile.big { min-height: 240px; }
#md-root .md-tile.big span { font-size: 96px; }
#md-root .md-tile small { opacity: 0.7; }
#md-root .md-cap { font-weight: 600; }
#md-root .md-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#md-root .md-sub { opacity: 0.6; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#md-root .md-copy { border: none; background: none; cursor: pointer; padding: 0 3px;
  font-size: 0.9em; opacity: 0.6; }
#md-root .md-copy:hover { opacity: 1; }
#md-root .md-copy.md-copied { opacity: 1; filter: hue-rotate(90deg); }
</style>
<script>
(() => {
  // navigator.clipboard needs a secure context (LAN http has none) -> textarea fallback
  function copy(btn){
    const v = btn.dataset.v; if (v === undefined) return;
    const ok = () => { btn.classList.add('md-copied'); btn.textContent = '✔';
      setTimeout(() => { btn.classList.remove('md-copied'); btn.textContent = '📋'; }, 800); };
    const fallback = () => {
      const ta = document.createElement('textarea');
      ta.value = v; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { if (document.execCommand('copy')) ok(); } catch(_) {}
      ta.remove();
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(v).then(ok).catch(fallback);
    else fallback();
  }
  function load(url){
    const bus = document.querySelector('#md-bus textarea, #md-bus input');
    const go = document.getElementById('md-go');
    if (!bus || !go) return;
    bus.value = url;
    bus.dispatchEvent(new Event('input', { bubbles: true }));
    setTimeout(() => go.click(), 0);
  }
  document.addEventListener('click', (e) => {
    if (!e.target.closest) return;
    const btn = e.target.closest('#md-root .md-copy');
    if (btn) { e.preventDefault(); e.stopPropagation(); copy(btn); return; }
    const card = e.target.closest('#md-root .md-card.md-load');
    if (card && card.dataset.url) { e.preventDefault(); load(card.dataset.url); window.scrollTo(0, 0); }
  }, true);
})();
</script>
"""
