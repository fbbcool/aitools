"""Refdef tab of the AIDB scene app (reference definition).

Three fixed reference slots (image + short role text) plus one prompt /
prompt-hint box. The clipspace is the only input (``⟲ pull``, plus a ⟲ per
slot) and the only output (``⇪ deploy``); the tab is stateless otherwise.

Pull is smart: enhancer data (``1xlasm_enhancer.iteration.*``) or a
refdef.v1 instruction loads as a whole; an img url / url list / img id /
scene id clipspace is added to the free slots (extras dropped); anything
else only shows a 0.5 s toast. A slot's own ⟲ puts the first image of any
pull data into just that slot. What deploy writes depends on what was
pulled:

  * **enhancer mode** (enhancer data pulled): the tab keeps the WHOLE
    payload as a working copy and shows one section at a time — the
    *view* (main / vid / inp / next = ``prompts`` / ``prompts_vid`` /
    ``prompts_inp`` / ``prompts_next``; default = the section the latest
    enhancer step produced). Replaced slot images are patched into the
    working copy (on view switch and on deploy); deploy writes the full
    payload back with ``edited_by: 'refdef'`` and never triggers the
    enhancer, which ignores such payloads (task 150). Prompt and roles are
    display-only (roles = the media ``url_desc`` / ``desc``).
  * **instruction mode** (images only / reset): a ``1xlasm_enhancer.refdef.v1``
    instruction with the selected verb (replicate / enh / pickup / inp-mask /
    inp-nomask) that the enhancer builds its enhancer data from. With
    *auto-trigger* on, deploy then prompts the ``enhancer`` agent in herdr
    session ``xlasm`` with ``/refdef`` — only when it is idle.

Payload logic is in pure module functions (``parse_payload``, ``with_view``,
``patch_iteration``, ``refdef_payload``) so it can be tested without gradio.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote

import gradio as gr
import pyperclip
from PIL import Image, ImageOps

from ait.tools.files import is_img
from aidb.scene.scene_common import SceneDef
from aidb.scene.scene_image_manager import SceneImageManager
from aidb.scene.scene_manager import SceneManager

N_SLOTS: Final = 3
SCHEMA_ITERATION: Final = '1xlasm_enhancer.iteration'  # version-tolerant prefix
SCHEMA_REFDEF: Final = '1xlasm_enhancer.refdef.v1'
EDITED_BY: Final = 'refdef'
KINDS: Final = ('prompt', 'hint')
VERBS: Final = ('replicate', 'enh', 'pickup', 'inp-mask', 'inp-nomask')
VID_REF_KEYS: Final = ('first', 'last')  # prompts_vid.refs keys for slots 2/3
PREVIEW_SIZE: Final = 768  # slot preview edge (px)
MAX_PULL_LINES: Final = 50  # longer clipspaces are no image lists
# auto-trigger: after an instruction deploy, prompt the enhancer agent in its
# herdr session with TRIGGER_CMD (board task 150) — only when it is idle
HERDR_SESSION: Final = 'xlasm'
HERDR_AGENT: Final = 'enhancer'
TRIGGER_CMD: Final = '/refdef'
HERDR_READY: Final = ('idle', 'done')
HERDR_TIMEOUT_S: Final = 10


# ---------------------------------------------------------------------- #
# pure payload logic
# ---------------------------------------------------------------------- #
def empty_slots() -> list[dict]:
    return [{'url': None, 'id': None, 'role': ''} for _ in range(N_SLOTS)]


def _entries(payload: dict) -> list[dict]:
    prompts = payload.get('prompts') or {}
    return [e for e in prompts.get('prompt_data') or [] if isinstance(e, dict)]


def _current(payload: dict) -> int:
    n = len(_entries(payload))
    cur = (payload.get('prompts') or {}).get('current', 0)
    return cur if isinstance(cur, int) and 0 <= cur < n else 0


def _vid_refs(payload: dict) -> dict:
    refs = (payload.get('prompts_vid') or {}).get('refs')
    return refs if isinstance(refs, dict) else {}


# enhancer data views: each payload section the tab can show in the 3 slots
VIEWS: Final = ('main', 'vid', 'inp', 'next')
VIEW_SECTION: Final = {'vid': 'prompts_vid', 'inp': 'prompts_inp', 'next': 'prompts_next'}
# fallback roles per view when a media object carries no desc (task 150)
VIEW_ROLES: Final = {
    'main': ('main img', '', ''),
    'vid': ('first frame', 'last frame', ''),
    'inp': ('edit target', 'image 2', 'image 3'),
    'next': ('src', 'identity ref', ''),
}


def _section_entry(payload: dict, view: str) -> dict | None:
    """Current entry of a prompts_vid/_inp/_next section, None when absent."""
    sec = payload.get(VIEW_SECTION.get(view, ''))
    if not isinstance(sec, dict):
        return None
    data = [e for e in sec.get('prompt_data') or [] if isinstance(e, dict)]
    cur = sec.get('current', 0)
    if not data:
        return None
    return data[cur] if isinstance(cur, int) and 0 <= cur < len(data) else data[0]


def available_views(payload: dict) -> list[str]:
    return ['main'] + [v for v in VIEW_SECTION if _section_entry(payload, v) is not None]


def default_view(payload: dict) -> str:
    """The section the latest enhancer step produced: its entry's ``from_rev``
    is the payload's ``rev`` (newest ``ts`` wins); else ``main``."""
    rev = payload.get('rev')
    fresh = []
    for v in available_views(payload)[1:]:
        e = _section_entry(payload, v) or {}
        if rev is not None and e.get('from_rev') == rev:
            fresh.append((str(e.get('ts') or ''), v))
    return max(fresh)[1] if fresh else 'main'


def _view_media(payload: dict, view: str) -> list[dict | None]:
    """Live media objects ({url[, desc, w, h]}) of a view, slot order.
    ``main`` is the top-level url — returned as a detached dict."""
    if view == 'main':
        return [{'url': payload.get('url'), 'desc': payload.get('url_desc')}]
    if view == 'vid':
        refs = _vid_refs(payload)
        return [refs.get(k) if isinstance(refs.get(k), dict) else None for k in VID_REF_KEYS]
    e = _section_entry(payload, view) or {}
    src = e.get('src') if isinstance(e.get('src'), dict) else None
    if view == 'inp':
        inp_refs = [r if isinstance(r, dict) else None for r in e.get('refs') or []]
        return [src, *inp_refs[: N_SLOTS - 1]]
    if view == 'next':
        ref = e.get('ref') if isinstance(e.get('ref'), dict) else None
        return [src, ref]
    return []


def view_slots(payload: dict, view: str) -> list[dict]:
    slots = empty_slots()
    for i, m in enumerate(_view_media(payload, view)[:N_SLOTS]):
        if m and m.get('url'):
            role = m.get('desc') or VIEW_ROLES[view][i]
            slots[i] = {'url': m['url'], 'id': None, 'role': role}
    return slots


def view_text(payload: dict, view: str, idx: int = 0) -> str:
    if view == 'main':
        return entry_prompt(payload, idx)
    e = _section_entry(payload, view) or {}
    if view == 'vid':
        return str(e.get('prompt') or '')
    # inp: one engine per entry (qwen21 default, frozen krea2 on request)
    return str(e.get('prompt_qwen21') or e.get('prompt') or '')


def parse_payload(text: str | None) -> dict | None:
    """Clipspace text → ``{kind: 'iteration'|'refdef', payload, slots, text,
    prompt_kind, verb, idx, views, view}``; None when it is no enhancer
    payload."""
    try:
        payload = json.loads(text or '')
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    schema = str(payload.get('schema_id', ''))

    if schema == SCHEMA_REFDEF:
        slots = empty_slots()
        for ref in payload.get('refs') or []:
            n = ref.get('slot') if isinstance(ref, dict) else None
            if isinstance(n, int) and 1 <= n <= N_SLOTS:
                slots[n - 1] = {
                    'url': ref.get('url'),
                    'id': ref.get('id'),
                    'role': ref.get('role') or '',
                }
        kind = payload.get('kind')
        verb = payload.get('verb')
        return {
            'kind': 'refdef',
            'payload': payload,
            'slots': slots,
            'text': payload.get('text') or '',
            'prompt_kind': kind if kind in KINDS else 'hint',
            'verb': verb if verb in VERBS else VERBS[0],
            'idx': 0,
            'views': [],
            'view': None,
        }

    if schema.startswith(SCHEMA_ITERATION):
        return with_view(
            {
                'kind': 'iteration',
                'payload': payload,
                'prompt_kind': 'prompt',
                'verb': None,
                'views': available_views(payload),
                'changed': [],  # field names patched into the working copy so far
            },
            default_view(payload),
        )
    return None


def with_view(st: dict, view: str) -> dict:
    """Iteration state switched to ``view`` (slots + text re-derived)."""
    p = st['payload']
    idx = _current(p)
    return dict(st, view=view, idx=idx, slots=view_slots(p, view), text=view_text(p, view, idx))


def entry_prompt(payload: dict, idx: int) -> str:
    entries = _entries(payload)
    if 0 <= idx < len(entries):
        return str(entries[idx].get('prompt') or '')
    return ''


def _img_dims(url: str) -> tuple[int, int] | None:
    try:
        with Image.open(url) as im:
            return im.size
    except Exception:  # noqa: BLE001 - remote/unreadable -> keep the old dims
        return None


def _replace_media(obj: dict, url: str) -> None:
    obj['url'] = url
    obj.pop('frame', None)  # src-clip frame provenance no longer applies
    if 'w' in obj or 'h' in obj:
        dims = _img_dims(url)
        if dims:
            obj['w'], obj['h'] = dims


def patch_iteration(
    payload: dict,
    view: str,
    urls: list[str | None],
) -> tuple[dict, list[str], list[str]]:
    """Copy of an iteration payload with only the image urls of ``view``
    patched (slot order as in ``view_slots``). Everything else is deployed
    verbatim.

    Replacing an image is always allowed (``w``/``h`` follow the new file).
    Structural changes are reported, not deployed, where the prompt names
    images by number: adding/removing an inp ref, clearing an inp/next src
    or the next ref. Returns the patched payload, the changed field names
    and the skipped edits; ``edited_by`` is set only when something changed.
    """
    out = copy.deepcopy(payload)
    changed: list[str] = []
    skipped: list[str] = []
    urls = [u or None for u in urls]

    if view == 'main':
        if urls[0] != (out.get('url') or None):
            out['url'] = urls[0]
            changed.append('url')
        skipped += [f'slot {i + 1} (main has one image)' for i in (1, 2) if urls[i]]

    elif view == 'vid':
        refs = _vid_refs(out)
        for i, key in enumerate(VID_REF_KEYS):
            new = urls[i]
            ref = refs.get(key)
            old = ref.get('url') if isinstance(ref, dict) else None
            if new == (old or None):
                continue
            if new is None:
                refs[key] = None
            elif isinstance(ref, dict):
                _replace_media(ref, new)
            else:
                refs[key] = {'url': new}
            changed.append(f'prompts_vid.refs.{key}')
        if urls[2]:
            skipped.append('slot 3 (vid has first/last only)')

    elif view in ('inp', 'next'):
        sec = VIEW_SECTION[view]
        media = _view_media(out, view)
        names = ['src', 'refs[0]', 'refs[1]'] if view == 'inp' else ['src', 'ref', '']
        for i in range(N_SLOTS):
            obj = media[i] if i < len(media) else None
            old = obj.get('url') if obj else None
            new = urls[i]
            if new == (old or None):
                continue
            if obj is not None and new is not None:
                _replace_media(obj, new)
                changed.append(f'{sec}.{names[i]}')
            elif not names[i]:
                skipped.append(f'slot {i + 1} ({view} has no slot {i + 1})')
            else:
                what = 'removing' if new is None else 'adding'
                skipped.append(f'slot {i + 1} ({what} {names[i]} would renumber the prompt)')

    if changed:
        out['edited_by'] = EDITED_BY
    return out, changed, skipped


def refdef_payload(
    slots: list[dict],
    verb: str,
    prompt_kind: str,
    text: str,
    origin_scene_id: str | None = None,
) -> dict:
    """The instruction payload the enhancer builds its enhancer data from."""
    return {
        'schema_id': SCHEMA_REFDEF,
        'verb': verb if verb in VERBS else VERBS[0],
        'refs': [
            {
                'slot': i + 1,
                'url': s.get('url') or None,
                'id': s.get('id') or None,
                'role': (s.get('role') or '').strip(),
            }
            for i, s in enumerate(slots[:N_SLOTS])
        ],
        'kind': prompt_kind if prompt_kind in KINDS else 'hint',
        'text': text or '',
        'origin': {'scene_id': origin_scene_id} if origin_scene_id else None,
    }


def clip_copy(text: str) -> None:
    """Write the clipspace so it outlives the app.

    pyperclip's wl-copy daemon stays in the app's process group, so the
    Ctrl-C that restarts the app (tmux) kills it and empties the clipboard.
    On Wayland, run wl-copy in its own session instead.
    """
    exe = shutil.which('wl-copy')
    if exe and os.environ.get('WAYLAND_DISPLAY'):
        subprocess.run(
            [exe],
            input=text,
            text=True,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=True,
        )
        return
    pyperclip.copy(text)


def _herdr(*args: str) -> dict:
    """Run a herdr CLI command against HERDR_SESSION → parsed JSON.

    The app runs outside herdr, so caller-context HERDR_* vars are dropped
    and the session is addressed explicitly. Raises RuntimeError on failure.
    """
    exe = shutil.which('herdr') or str(Path.home() / '.local' / 'bin' / 'herdr')
    env = {k: v for k, v in os.environ.items() if not k.startswith('HERDR_')}
    try:
        res = subprocess.run(
            [exe, '--session', HERDR_SESSION, *args],
            capture_output=True,
            text=True,
            timeout=HERDR_TIMEOUT_S,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f'herdr: {e}') from e
    if res.returncode != 0:
        raise RuntimeError(f'herdr: {(res.stderr or res.stdout).strip()[:200]}')
    try:
        return json.loads(res.stdout or '{}')
    except json.JSONDecodeError as e:
        raise RuntimeError(f'herdr: bad json: {res.stdout[:200]}') from e


def trigger_enhancer() -> str:
    """Send TRIGGER_CMD to the enhancer agent if it is ready for input.

    Never types into a working/blocked agent. Fire-and-forget: does not wait
    for the enhancer to finish. Returns a short status note.
    """
    try:
        agent = _herdr('agent', 'get', HERDR_AGENT).get('result', {}).get('agent', {})
    except RuntimeError as e:
        return f'enhancer not reachable ({e})'
    status = agent.get('agent_status')
    if status not in HERDR_READY:
        return f'enhancer {status or "unknown"} — {TRIGGER_CMD} NOT sent'
    try:
        _herdr('agent', 'prompt', HERDR_AGENT, TRIGGER_CMD)
    except RuntimeError as e:
        return f'{TRIGGER_CMD} failed ({e})'
    return f'{TRIGGER_CMD} sent to enhancer'


# ---------------------------------------------------------------------- #
# tab
# ---------------------------------------------------------------------- #
class RefdefTab:
    def __init__(self, dbc, verbose: int = 0) -> None:
        self._sim = SceneImageManager(dbc=dbc, verbose=0)
        self._scm = SceneManager(dbc=dbc, verbose=0)
        self._verbose = verbose

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[refdef_tab:{level}] {msg}')

    # -- ref resolution ------------------------------------------------- #
    def _id_from_path(self, path: str | Path) -> str | None:
        parsed = SceneDef.id_and_prefix_from_filename(path)
        return parsed[0] if parsed and self._sim.is_id(parsed[0]) else None

    def resolve_ref(self, ref: str | None) -> tuple[str | None, str | None]:
        """img id / scene id / local path / http url → (url, img_id).

        A scene id resolves to the image the app displays for the scene
        (``SceneManager.display_image``, same as the enhancer's resolve).
        """
        ref = (ref or '').strip().strip('"\'')
        if ref.startswith('file://'):
            ref = unquote(ref.removeprefix('file://'))
        if not ref:
            return None, None
        if ref.startswith(('http://', 'https://')):
            return ref, None
        path = Path(ref).expanduser()
        if path.is_absolute():
            return str(path), self._id_from_path(path)
        if self._sim.is_id(ref):
            img = self._sim.img_from_id(ref)
            url = img.url_from_data if img is not None else None
            return (str(url) if url else None), ref
        if self._scm.is_id(ref):
            url = self._scm.display_image(ref)
            return url, (self._id_from_path(url) if url else None)
        return None, None

    @staticmethod
    def _is_usable(url: str | None) -> bool:
        if not url or not is_img(url):
            return False
        return url.startswith(('http://', 'https://')) or Path(url).is_file()

    def images_from_clipspace(self, text: str | None) -> list[tuple[str, str | None]]:
        """Clipspace → [(url, img_id)] for an img url / url list / img id /
        scene id clipspace; [] when any non-blank line is not a usable image
        (so freeform text never half-fills slots)."""
        lines = [ln.strip() for ln in (text or '').splitlines() if ln.strip()]
        if not lines or len(lines) > MAX_PULL_LINES:
            return []
        out: list[tuple[str, str | None]] = []
        for ln in lines:
            url, id_img = self.resolve_ref(ln)
            if url is None or not self._is_usable(url):
                return []
            out.append((url, id_img))
        return out

    def first_image_from_clipspace(self, text: str | None) -> tuple[str, str | None] | None:
        """First type-matching (image) entry of any pull data: enhancer data
        (top-level url, then every section's media), a refdef instruction
        (slots in order) or an img/id list (first usable line)."""
        st = parse_payload(text)
        if st is not None:
            p = st['payload']
            if st['kind'] == 'refdef':
                cands = [(s.get('id') or s.get('url')) for s in st['slots']]
            else:
                cands = [p.get('url')] + [
                    (m or {}).get('url') for v in st['views'] for m in _view_media(p, v)
                ]
        else:
            lines = [ln.strip() for ln in (text or '').splitlines() if ln.strip()]
            cands = lines[:MAX_PULL_LINES]
        for c in cands:
            url, id_img = self.resolve_ref(c)
            if url is not None and self._is_usable(url):
                return url, id_img
        return None

    def _on_slot_pull(self):
        hit = self.first_image_from_clipspace(pyperclip.paste())
        if hit is None:
            gr.Info('nothing usable to pull', duration=0.5)
            return gr.update(), gr.update()
        url, id_img = hit
        return self._preview(url), id_img or url

    @staticmethod
    def _preview(url: str | None) -> Image.Image | str | None:
        """Slot display value. Local files go in as a downscaled PIL image:
        gradio refuses to serve paths outside cwd/tmp (allowed_paths), and
        refs live anywhere (scenes, comfy output, …). The slot ref keeps the
        real path for deploy."""
        if not url:
            return None
        if url.startswith(('http://', 'https://')):
            return url
        if not (is_img(url) and Path(url).is_file()):
            return None
        try:
            with Image.open(url) as src:
                src.draft('RGB', (PREVIEW_SIZE, PREVIEW_SIZE))
                im = ImageOps.exif_transpose(src).convert('RGB')
            im.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE))
            return im
        except Exception:  # noqa: BLE001 - unreadable file -> empty slot preview
            return None

    # -- state helpers -------------------------------------------------- #
    @staticmethod
    def _is_enh(state: dict | None) -> bool:
        return bool(state) and state['kind'] == 'iteration'  # type: ignore[index]

    @classmethod
    def _source_md(cls, state: dict | None, idx: int) -> str:
        if not cls._is_enh(state):
            return (
                '**mode: instruction** — deploy writes `refdef.v1` + verb '
                '(pull enhancer data to switch to enhancer mode)'
            )
        p = state['payload']  # type: ignore[index]
        view = state['view']  # type: ignore[index]
        md = (
            '**mode: enhancer data** — deploy writes it back verbatim, only replaced '
            f'img urls of the view patched · `{p.get("schema_id")}` · scene '
            f'`{p.get("scene_id")}` · rev {p.get("rev")} · view **{view}**'
        )
        if view == 'main':
            prompts = p.get('prompts') or {}
            md += (
                f' · prompts.type=`{prompts.get("type")}` · entry **{idx + 1}/'
                f'{len(_entries(p))}** (current={_current(p) + 1})'
            )
        else:
            e = _section_entry(p, view) or {}
            md += f' · from_rev {e.get("from_rev")}'
        if p.get('edited_by'):
            md += f' · edited_by=`{p["edited_by"]}`'
        return md

    @classmethod
    def _entry_md(cls, state: dict | None, idx: int) -> str:
        if not cls._is_enh(state):
            return ''
        p, view = state['payload'], state['view']  # type: ignore[index]
        if view == 'main':
            entries = _entries(p)
            e = entries[idx] if 0 <= idx < len(entries) else {}
        else:
            e = _section_entry(p, view) or {}
        concepts = ', '.join(e.get('concepts') or []) or '–'
        triggers = ', '.join(e.get('triggers') or []) or '–'
        md = f'**concepts:** {concepts}  \n**triggers:** {triggers}'
        if view == 'inp':
            md += (
                f'  \n**engine:** {e.get("engine") or "krea2"} · **mode:** {e.get("mode")} '
                f'· **mask:** {"yes" if e.get("mask") else "none"}'
            )
        if e.get('hints'):
            md += f'  \n**hints:** {e["hints"]}'
        return md

    # -- handlers ------------------------------------------------------- #
    @staticmethod
    def place_images(n_imgs: int, refs: list[str]) -> list[int]:
        """Slot indices for n pulled images: pulls add to what is there, so
        only empty slots (in order) are used; images beyond them are dropped
        (reset first to start over)."""
        empty = [i for i, r in enumerate(refs) if not (r or '').strip()]
        return empty[:n_imgs]

    def _load(self, st: dict | None) -> list[Any]:
        """Outputs for a freshly loaded state (None = reset to empty instruction).
        Order: state, idx, raw, 3×(img, ref, role), kind, verb, text, source, entry,
        view."""
        enh = self._is_enh(st)
        slots = st['slots'] if st else empty_slots()
        slot_vals: list[Any] = []
        for s in slots:
            ref = s.get('id') or s.get('url') or ''
            role = gr.update(value=s.get('role') or '', interactive=not enh)
            slot_vals += [self._preview(s.get('url')), ref, role]
        idx = st['idx'] if st else 0
        raw = json.dumps(st['payload'], indent=2, ensure_ascii=False) if st else ''
        return [
            st,
            idx,
            raw,
            *slot_vals,
            gr.update(value=st['prompt_kind'] if st else 'hint', interactive=not enh),
            st['verb'] if st and st['verb'] else gr.update(),
            gr.update(value=st['text'] if st else '', interactive=not enh),
            self._source_md(st, idx),
            self._entry_md(st, idx),
            gr.update(
                choices=st['views'] if st and enh else [],
                value=st['view'] if st and enh else None,
                visible=enh,
            ),
        ]

    def _commit(self, state: dict, refs: list[str]) -> tuple[dict, list[str], list[str]]:
        """Patch the current view's slot images into the working payload
        (``state['payload']``), so every view's replacements reach deploy."""
        urls = [self.resolve_ref(r)[0] for r in refs]
        work, changed, skipped = patch_iteration(state['payload'], state['view'], urls)
        before = state.get('changed', [])
        merged = before + [c for c in changed if c not in before]
        return dict(state, payload=work, changed=merged), changed, skipped

    def _on_view(self, state: dict | None, view: str | None, *refs: str):
        """Switch the enhancer-data view; the old view's slot replacements
        are committed to the working payload first."""
        if not self._is_enh(state) or not view or view == state['view']:  # type: ignore[index]
            return [gr.update()] * (3 + 3 * N_SLOTS + 7)
        st, changed, skipped = self._commit(state, list(refs))  # type: ignore[arg-type]
        note = f' · kept: {", ".join(changed)}' if changed else ''
        note += f' · NOT kept: {", ".join(skipped)}' if skipped else ''
        return [*self._load(with_view(st, view)), f'view `{view}`{note}']

    def _on_pull(self, state: dict | None, *refs: str):
        n_out = 3 + 3 * N_SLOTS + 7
        text = pyperclip.paste()
        st = parse_payload(text)
        if st is not None:
            return [*self._load(st), f'pulled `{st["payload"].get("schema_id")}`']
        imgs = self.images_from_clipspace(text)
        if not imgs:
            gr.Info('nothing usable to pull', duration=0.5)
            return [gr.update()] * n_out
        upd: list[Any] = [gr.update()] * (3 * N_SLOTS)
        slots = self.place_images(len(imgs), list(refs))
        n_drop = len(imgs) - len(slots)
        if n_drop:
            gr.Info(f'no free slot: {n_drop} img(s) dropped', duration=0.5)
        if not slots:
            return [gr.update()] * n_out
        for i, (url, id_img) in zip(slots, imgs, strict=False):
            # enhancer mode keeps the (payload-owned) role; instruction mode starts blank
            role = gr.update() if self._is_enh(state) else ''
            upd[3 * i : 3 * i + 3] = [self._preview(url), id_img or url, role]
        dropped = f' ({n_drop} dropped, no free slot)' if n_drop else ''
        status = f'pulled {len(slots)} img(s) → slot {", ".join(str(i + 1) for i in slots)}'
        return [*[gr.update()] * 3, *upd, *[gr.update()] * 6, status + dropped]

    def _on_reset(self):
        return [*self._load(None), 'reset']

    def _on_nav(self, state: dict | None, idx: int, step: int):
        if not self._is_enh(state) or state['view'] != 'main':  # type: ignore[index]
            return idx, gr.update(), gr.update(), gr.update()
        p = state['payload']  # type: ignore[index]
        new = max(0, min(len(_entries(p)) - 1, idx + step))
        return new, entry_prompt(p, new), self._source_md(state, new), self._entry_md(state, new)

    def _slots_from_ui(self, refs_roles: list[str]) -> list[dict]:
        slots = []
        for i in range(N_SLOTS):
            url, id_img = self.resolve_ref(refs_roles[2 * i])
            slots.append({'url': url, 'id': id_img, 'role': refs_roles[2 * i + 1]})
        return slots

    def _on_deploy(
        self,
        state: dict | None,
        verb: str,
        kind: str,
        auto: bool,
        text: str,
        *refs_roles,
    ):
        slots = self._slots_from_ui(list(refs_roles))
        if self._is_enh(state):
            refs = [refs_roles[2 * i] for i in range(N_SLOTS)]
            st, _, skipped = self._commit(state, refs)  # type: ignore[arg-type]
            # the full payload (all sections) goes back; never triggers the enhancer
            clip_copy(json.dumps(st['payload'], ensure_ascii=False))
            note = f' · NOT deployed: {", ".join(skipped)}' if skipped else ''
            changed = st['changed']
            what = f'img urls patched: {", ".join(changed)}' if changed else 'unchanged'
            return f'deployed enhancer data ({what}){note}'
        origin = None
        if state and state['kind'] == 'refdef':
            origin = (state['payload'].get('origin') or {}).get('scene_id')
        payload = refdef_payload(slots, verb, kind, text, origin)
        clip_copy(json.dumps(payload, ensure_ascii=False))
        n = sum(1 for s in slots if s['url'])
        msg = f'deployed instruction `{verb}` ({n}/{N_SLOTS} slots, kind={kind})'
        note = trigger_enhancer() if auto else 'auto-trigger off'
        print(f'[refdef_tab:info] deploy {verb}: {note}')
        return f'{msg} · {note}'

    # -- UI build (call inside the app's gr.Blocks context) ------------- #
    def build(self) -> None:
        with gr.Tab('refdef', elem_id='refdef_tab'):
            state = gr.State(None)  # parse_payload() result of the last enhancer pull
            idx = gr.State(0)  # pointed prompt_data entry (display only)

            with gr.Row():
                pull_btn = gr.Button('⟲ pull', variant='primary', scale=1)
                deploy_btn = gr.Button('⇪ deploy', elem_id='refdef-deploy', scale=1)
                reset_btn = gr.Button('reset', scale=0, min_width=80)
            with gr.Row():
                verb = gr.Radio(
                    list(VERBS),
                    value=VERBS[0],
                    label='instruction verb (instruction mode)',
                    scale=3,
                )
                kind = gr.Radio(list(KINDS), value='hint', label='text is a', scale=1)
                auto = gr.Checkbox(
                    value=True,
                    label=f'auto-trigger enhancer ({TRIGGER_CMD})',
                    info=f'instruction deploy → {TRIGGER_CMD} to herdr {HERDR_SESSION}/'
                    f'{HERDR_AGENT}, only when idle',
                    scale=1,
                )
            view = gr.Radio([], label='view (enhancer data section)', visible=False)
            with gr.Row():
                prev_btn = gr.Button('◀', scale=0, min_width=40)
                source_md = gr.Markdown(self._source_md(None, 0))
                next_btn = gr.Button('▶', scale=0, min_width=40)

            # input is the clipspace only: images are display-only, the slot
            # ref (img id or url) rides in a per-slot State
            imgs, refs, roles, slot_pulls, clears = [], [], [], [], []
            with gr.Row(equal_height=True):
                for i in range(N_SLOTS):
                    with gr.Column():
                        imgs.append(
                            gr.Image(
                                type='filepath',
                                label=f'slot {i + 1}',
                                height=360,
                                interactive=False,
                            )
                        )
                        refs.append(gr.State(''))
                        with gr.Row():
                            roles.append(
                                gr.Textbox(
                                    placeholder='role: what this ref is for',
                                    show_label=False,
                                    lines=2,
                                    scale=5,
                                )
                            )
                            slot_pulls.append(gr.Button('⟲', scale=0, min_width=40))
                            clears.append(gr.Button('✕', scale=0, min_width=40))

            status = gr.Markdown()
            text = gr.Textbox(label='prompt / prompt hint', lines=8, max_lines=30)
            with gr.Accordion('concepts / triggers', open=False):
                entry_md = gr.Markdown()
            with gr.Accordion('raw payload (as pulled / last view switch)', open=False):
                raw = gr.Code(language='json', interactive=False)

            refs_roles = [c for pair in zip(refs, roles, strict=True) for c in pair]
            slot_outs = [c for trip in zip(imgs, refs, roles, strict=True) for c in trip]
            load_outs = [state, idx, raw, *slot_outs, kind, verb, text, source_md, entry_md, view]

            pull_btn.click(self._on_pull, [state, *refs], [*load_outs, status])
            reset_btn.click(self._on_reset, [], [*load_outs, status])
            view.input(self._on_view, [state, view, *refs], [*load_outs, status])
            for btn, step in ((prev_btn, -1), (next_btn, 1)):
                btn.click(
                    lambda s, i, step=step: self._on_nav(s, i, step),
                    [state, idx],
                    [idx, text, source_md, entry_md],
                )
            for img, ref, clear in zip(imgs, refs, clears, strict=True):
                # role stays: in enhancer mode it is payload-owned
                clear.click(lambda: (None, ''), [], [img, ref])
            for img, ref, slot_pull in zip(imgs, refs, slot_pulls, strict=True):
                slot_pull.click(self._on_slot_pull, [], [img, ref])
            deploy_btn.click(
                self._on_deploy,
                [state, verb, kind, auto, text, *refs_roles],
                [status],
            )


REFDEF_HEAD = r"""
<style>
#refdef-deploy { background: #2e7d32 !important; border-color: #2e7d32 !important;
  color: #fff !important; }
#refdef-deploy:hover { background: #388e3c !important; }
</style>
"""
