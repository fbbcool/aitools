"""Refdef tab of the AIDB scene app (reference definition).

Three fixed reference slots (image + short role text) plus one prompt /
prompt-hint box. The clipspace is the only input (``⟲ pull clipspace``)
and the only output (``⇪ deploy``); the tab is stateless otherwise.

Pull is smart: enhancer data (``1xlasm_enhancer.iteration.*``) or a
refdef.v1 instruction loads as a whole; an img url / url list / img id /
scene id clipspace fills slots (empty slots first); anything else only
shows a 0.5 s toast. What deploy writes depends on what was pulled:

  * **enhancer mode** (enhancer data pulled): the exact payload goes back,
    only image urls the user replaced are patched (slot 1 = ``url``, slots
    2/3 = mmh3 ``prompts_vid.refs.first/last``) and ``edited_by: 'refdef'``
    is set. Prompt and roles are display-only (roles read the per-media
    ``url_desc`` / ``desc`` fields, board task 150). ◀ ▶ step through
    story/batch entries.
  * **instruction mode** (images only / reset): a ``1xlasm_enhancer.refdef.v1``
    instruction with the selected verb (replicate / enh / pickup / inp-mask /
    inp-nomask) that the enhancer builds its enhancer data from (task 150).

Payload logic is in pure module functions (``parse_payload``,
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
# fallback roles when an iteration payload carries no media desc (task 150)
ROLES_ITERATION: Final = ('main img', 'mmh3 first frame', 'mmh3 last frame')
VID_REF_KEYS: Final = ('first', 'last')  # prompts_vid.refs keys for slots 2/3
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


def parse_payload(text: str | None) -> dict | None:
    """Clipspace text → ``{kind: 'iteration'|'refdef', payload, slots, text,
    prompt_kind, verb, idx}``; None when it is no enhancer payload."""
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
        }

    if schema.startswith(SCHEMA_ITERATION):
        slots = empty_slots()
        role = payload.get('url_desc') or ROLES_ITERATION[0]
        slots[0] = {'url': payload.get('url'), 'id': None, 'role': role}
        refs = _vid_refs(payload)
        for i, key in enumerate(VID_REF_KEYS, start=1):
            ref = refs.get(key)
            if isinstance(ref, dict) and ref.get('url'):
                role = ref.get('desc') or ROLES_ITERATION[i]
                slots[i] = {'url': ref['url'], 'id': None, 'role': role}
        idx = _current(payload)
        return {
            'kind': 'iteration',
            'payload': payload,
            'slots': slots,
            'text': entry_prompt(payload, idx),
            'prompt_kind': 'prompt',
            'verb': None,
            'idx': idx,
        }
    return None


def entry_prompt(payload: dict, idx: int) -> str:
    entries = _entries(payload)
    if 0 <= idx < len(entries):
        return str(entries[idx].get('prompt') or '')
    return ''


def patch_iteration(
    payload: dict,
    urls: list[str | None],
) -> tuple[dict, list[str], list[str]]:
    """Copy of an iteration payload with only the image urls patched.

    ``urls`` are the slot urls as edited (slot 1 → ``url``, slots 2/3 →
    ``prompts_vid.refs.first/last.url``). Everything else is deployed
    verbatim. Returns the patched payload, the changed field names and the
    edits that could not be deployed; ``edited_by`` is set only when
    something changed.
    """
    out = copy.deepcopy(payload)
    changed: list[str] = []
    skipped: list[str] = []

    if (urls[0] or None) != (out.get('url') or None):
        out['url'] = urls[0] or None
        changed.append('url')

    refs = _vid_refs(out)
    for i, key in enumerate(VID_REF_KEYS, start=1):
        new = urls[i] or None
        ref = refs.get(key)
        old = ref.get('url') if isinstance(ref, dict) else None
        if new == (old or None):
            continue
        if not refs:
            skipped.append(f'slot {i + 1} (payload has no prompts_vid.refs)')
            continue
        if new is None:
            refs[key] = None
        elif isinstance(ref, dict):
            ref['url'] = new
        else:
            refs[key] = {'url': new}
        changed.append(f'prompts_vid.refs.{key}')

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

    @staticmethod
    def _preview(url: str | None) -> str | None:
        if not url:
            return None
        if url.startswith(('http://', 'https://')):
            return url
        return url if is_img(url) and Path(url).is_file() else None

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
        prompts = p.get('prompts') or {}
        n = len(_entries(p))
        md = (
            '**mode: enhancer data** — deploy writes it back verbatim, only replaced '
            f'img urls patched · `{p.get("schema_id")}` · scene `{p.get("scene_id")}` · '
            f'prompts.type=`{prompts.get("type")}` · entry **{idx + 1}/{n}** '
            f'(current={_current(p) + 1})'
        )
        if p.get('edited_by'):
            md += f' · edited_by=`{p["edited_by"]}`'
        return md

    @classmethod
    def _entry_md(cls, state: dict | None, idx: int) -> str:
        if not cls._is_enh(state):
            return ''
        entries = _entries(state['payload'])  # type: ignore[index]
        if not 0 <= idx < len(entries):
            return ''
        e = entries[idx]
        concepts = ', '.join(e.get('concepts') or []) or '–'
        triggers = ', '.join(e.get('triggers') or []) or '–'
        return f'**concepts:** {concepts}  \n**triggers:** {triggers}'

    # -- handlers ------------------------------------------------------- #
    @staticmethod
    def place_images(n_imgs: int, refs: list[str]) -> list[int]:
        """Slot indices for n pulled images: the empty slots in order when
        they suffice, else slots 1..n (overwrite)."""
        n_imgs = min(n_imgs, N_SLOTS)
        empty = [i for i, r in enumerate(refs) if not (r or '').strip()]
        return empty[:n_imgs] if n_imgs <= len(empty) else list(range(n_imgs))

    def _load(self, st: dict | None) -> list[Any]:
        """Outputs for a freshly loaded state (None = reset to empty instruction).
        Order: state, idx, raw, 3×(img, ref, role), kind, verb, text, source, entry."""
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
        ]

    def _on_pull(self, state: dict | None, *refs: str):
        n_out = 3 + 3 * N_SLOTS + 6
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
        for i, (url, id_img) in zip(slots, imgs, strict=False):
            # enhancer mode keeps the (payload-owned) role; instruction mode starts blank
            role = gr.update() if self._is_enh(state) else ''
            upd[3 * i : 3 * i + 3] = [self._preview(url), id_img or url, role]
        dropped = f' ({len(imgs) - len(slots)} dropped)' if len(imgs) > len(slots) else ''
        status = f'pulled {len(slots)} img(s) → slot {", ".join(str(i + 1) for i in slots)}'
        return [*[gr.update()] * 3, *upd, *[gr.update()] * 5, status + dropped]

    def _on_reset(self):
        return [*self._load(None), 'reset']

    def _on_nav(self, state: dict | None, idx: int, step: int):
        if not self._is_enh(state):
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
            urls = [s['url'] for s in slots]
            out, changed, skipped = patch_iteration(state['payload'], urls)  # type: ignore[index]
            pyperclip.copy(json.dumps(out, ensure_ascii=False))
            note = f' · NOT deployed: {", ".join(skipped)}' if skipped else ''
            what = f'img urls patched: {", ".join(changed)}' if changed else 'unchanged'
            return f'deployed enhancer data ({what}){note}'
        origin = None
        if state and state['kind'] == 'refdef':
            origin = (state['payload'].get('origin') or {}).get('scene_id')
        payload = refdef_payload(slots, verb, kind, text, origin)
        pyperclip.copy(json.dumps(payload, ensure_ascii=False))
        n = sum(1 for s in slots if s['url'])
        msg = f'deployed instruction `{verb}` ({n}/{N_SLOTS} slots, kind={kind})'
        return f'{msg} · {trigger_enhancer()}' if auto else msg

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
                    value=False,
                    label=f'auto-trigger enhancer ({TRIGGER_CMD})',
                    info=f'instruction deploy → {TRIGGER_CMD} to herdr {HERDR_SESSION}/'
                    f'{HERDR_AGENT}, only when idle',
                    scale=1,
                )
            with gr.Row():
                prev_btn = gr.Button('◀', scale=0, min_width=40)
                source_md = gr.Markdown(self._source_md(None, 0))
                next_btn = gr.Button('▶', scale=0, min_width=40)

            # input is the clipspace only: images are display-only, the slot
            # ref (img id or url) rides in a per-slot State
            imgs, refs, roles, clears = [], [], [], []
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
                            clears.append(gr.Button('✕', scale=0, min_width=40))

            status = gr.Markdown()
            text = gr.Textbox(label='prompt / prompt hint', lines=8, max_lines=30)
            with gr.Accordion('concepts / triggers', open=False):
                entry_md = gr.Markdown()
            with gr.Accordion('raw payload (as pulled)', open=False):
                raw = gr.Code(language='json', interactive=False)

            refs_roles = [c for pair in zip(refs, roles, strict=True) for c in pair]
            slot_outs = [c for trip in zip(imgs, refs, roles, strict=True) for c in trip]
            load_outs = [state, idx, raw, *slot_outs, kind, verb, text, source_md, entry_md]

            pull_btn.click(self._on_pull, [state, *refs], [*load_outs, status])
            reset_btn.click(self._on_reset, [], [*load_outs, status])
            for btn, step in ((prev_btn, -1), (next_btn, 1)):
                btn.click(
                    lambda s, i, step=step: self._on_nav(s, i, step),
                    [state, idx],
                    [idx, text, source_md, entry_md],
                )
            for img, ref, clear in zip(imgs, refs, clears, strict=True):
                # role stays: in enhancer mode it is payload-owned
                clear.click(lambda: (None, ''), [], [img, ref])
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
