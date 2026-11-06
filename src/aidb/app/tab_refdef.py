"""Refdef tab of the AIDB scene app (reference definition).

Three fixed reference slots (image + short role text) plus one prompt /
prompt-hint box. The clipspace is the only input (``⟲ pull``, plus a ⟲ per
slot) and the only output (``⇪ deploy``, ``⇄ update``); the tab is stateless
otherwise.

``⇄ update`` is script-only (no agent, no trigger): it re-reads the CURRENT
clipspace and rewrites its reference image urls from the filled slots —
enhancer data via ``patch_iteration`` on the tab's view (else the clipspace's
default view), a refdef.v1 instruction slot by slot (url/id only). Empty
slots leave the clipspace's ref untouched.

Pull is smart: enhancer data (``1xlasm_enhancer.iteration.*``) or a
refdef.v1 instruction loads as a whole; an img url / url list / img id /
scene id clipspace is added to the free slots (extras dropped); anything
else only shows a 0.5 s toast. A slot's own ⟲ puts the first image of any
pull data into just that slot. What deploy writes depends on what was
pulled:

  * **enhancer mode** (enhancer data pulled): the tab keeps the WHOLE
    payload as a working copy and shows one section at a time — the
    *view* (main / vid / inp / next / ref = ``prompts`` / ``prompts_vid`` /
    ``prompts_inp`` / ``prompts_next`` / ``prompts_ref``; default = the section the latest
    enhancer step produced). Replaced slot images are patched into the
    working copy (on view switch and on deploy); deploy writes the full
    payload back with ``edited_by: 'refdef'`` and never triggers the
    enhancer, which ignores such payloads (task 150). Prompt and roles are
    display-only (roles = the media ``url_desc`` / ``desc``).
  * **instruction mode** (images/clips only / reset): a ``1xlasm_enhancer.refdef.v1``
    instruction with the selected verb (replicate / enh / pickup / inp-mask /
    inp-nomask / sketch / ref) that the enhancer builds its enhancer data from.
    ``sketch`` = a fresh scene from the hint text alone (slots may be empty).
    ``ref-novis`` = like ``ref``, but the enhancer never looks at the media (no
    vision, saves tokens): the ref prompt is built from the slot roles (+ hint)
    alone. Slot 1 needs media + a role (``missing_roles``); it references the
    other slots by refdef slot number ("slot 3"), whose roles may be empty.
    ``ref`` = the slots are MiniMax H3 ref2va picture references
    (``<Picture i>``, board task 159); like ``enh``: slot 1 required, stills. With
    *auto-trigger* on, deploy then prompts the ``enhancer`` agent in herdr
    session ``xlasm`` with ``/refdef`` — only when it is idle.

``pre-vid`` / ``post-vid`` (H3 clip chains, board task 172): slot 1 = the
anchor clip (video), the other slots optional NEW image / audio refs; the text
is the beat hint. Deploys like ``ref`` (+ a ``continue`` hint ``{dir, url,
pin}``); the enhancer writes ``prompts_ref[].continue``. ``⛓ join`` is
script-only like ⇄ update: slot 1 = the LAST clip of a chain, slot 2 = the
FIRST (a pre, optional) → ``ait.tools.videos.chain_join`` writes the joined
master to ``~/Downloads/000_comfy/`` and toasts path + seam summary.

``💾 save`` stores the whole tab config (state + slots + roles + verb / kind /
text) in the Mongo collection ``refdef_saves``; ◀ / ▶ step through those saves
(oldest … newest), and the current — possibly unsaved — config always sits
after the newest save, so ▶ past the newest save brings it back. Pull / reset /
save make the shown config the current one; 🗑 deletes the shown save (click
twice). The category dropdown next to 💾
filters ◀ / ▶ and files a save under it; ``(all)`` = no filter / uncategorized,
a typed-in name starts a new category.

Payload logic is in pure module functions (``parse_payload``, ``with_view``,
``patch_iteration``, ``refdef_payload``) so it can be tested without gradio.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote

import av
import gradio as gr
import pyperclip
from PIL import Image, ImageDraw, ImageOps

from ait.tools.files import (
    is_aud,
    is_img,
    is_img_or_vid,
    is_vid,
    suffix_aud,
    suffix_img,
    suffix_vid,
)
from ait.tools.videos import CHAIN_PIN, chain_join, ref_frame, seam_summary
from aidb.scene.scene_common import SceneDef
from aidb.scene.scene_image_manager import SceneImageManager
from aidb.scene.scene_manager import SceneManager

N_SLOTS: Final = 6
SLOTS_PER_ROW: Final = 3
SCHEMA_ITERATION: Final = '1xlasm_enhancer.iteration'  # version-tolerant prefix
SCHEMA_REFDEF: Final = '1xlasm_enhancer.refdef.v1'
EDITED_BY: Final = 'refdef'
KINDS: Final = ('prompt', 'hint')
VERBS: Final = (
    'replicate',
    'enh',
    'pickup',
    'inp-mask',
    'inp-nomask',
    'sketch',
    'ref',
    'ref-novis',
    'pre-vid',
    'post-vid',
)
# H3 clip-chain continuations (board task 172): slot 1 = the anchor clip
# (FbbcoolSaveVideo master, video only), the other slots optional NEW refs
# (images / audio); the enhancer writes prompts_ref[].continue = {dir, url, pin}
CONTINUE_VERBS: Final = {'pre-vid': 'pre', 'post-vid': 'post'}
# verbs whose prompt is built from the slot roles alone (enhancer never looks at
# the media): slot 1 needs media + a role; it references the other slots by number
ROLE_ONLY_VERBS: Final = ('ref-novis',)
# ⇄ update: the enhancer-data view (section) a verb owns (board task 162). A verb
# here patches ONLY its view; the other verbs never touch these views.
VERB_VIEW: Final = {'inp-mask': 'inp', 'inp-nomask': 'inp', 'ref': 'ref', 'ref-novis': 'ref'}
STILL_VIEWS: Final = ('inp',)  # qwen21 still slots: images only
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
SAVES_COLLECTION: Final = 'refdef_saves'  # 💾 save history (see build)
CAT_ALL: Final = '(all)'  # category filter = every save; saved as uncategorized
SNAP_KEYS: Final = ('state', 'idx', 'refs', 'roles', 'verb', 'kind', 'text')


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
VIEWS: Final = ('main', 'vid', 'inp', 'next', 'ref')
VIEW_SECTION: Final = {
    'vid': 'prompts_vid',
    'inp': 'prompts_inp',
    'next': 'prompts_next',
    'ref': 'prompts_ref',  # H3 ref2va: refs[i] = <Picture i+1> (v6.6, task 159)
}
# fallback roles per view when a media object carries no desc (task 150)
VIEW_ROLES: Final = {
    'main': ('main img',),
    'vid': ('first frame', 'last frame'),
    'inp': ('edit target', *(f'image {i}' for i in range(2, N_SLOTS + 1))),
    'next': ('src', 'identity ref'),
    'ref': tuple(f'picture {i}' for i in range(1, N_SLOTS + 1)),
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


def _ref_slots(entry: dict) -> list[dict | None]:
    """``prompts_ref`` refs placed at their slot. The list is compacted in slot
    order; since v6.8 each ref carries ``slot`` (1..6), older refs go by
    list position."""
    out: list[dict | None] = [None] * N_SLOTS
    for i, r in enumerate(entry.get('refs') or []):
        if not isinstance(r, dict):
            continue
        n = r.get('slot')
        k = n - 1 if isinstance(n, int) and 1 <= n <= N_SLOTS else i
        if k < N_SLOTS and out[k] is None:
            out[k] = r
    return out


def _view_media(payload: dict, view: str) -> list[dict | None]:
    """Live media objects ({url[, desc, w, h]}) of a view, slot order.
    ``main`` is the top-level url — returned as a detached dict."""
    if view == 'main':
        return [{'url': payload.get('url'), 'desc': payload.get('url_desc')}]
    if view == 'vid':
        refs = _vid_refs(payload)
        return [refs.get(k) if isinstance(refs.get(k), dict) else None for k in VID_REF_KEYS]
    e = _section_entry(payload, view) or {}
    if view == 'ref':
        return _ref_slots(e)
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
            roles = VIEW_ROLES[view]
            role = m.get('desc') or (roles[i] if i < len(roles) else '')
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
    """(w, h) of a local image or clip (first video stream); None keeps the old dims."""
    try:
        if is_vid(url):
            with av.open(url) as container:
                for stream in container.streams.video:
                    if stream.width and stream.height:
                        return stream.width, stream.height
            return None
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
    images by number: adding/removing an inp/ref ref, clearing an inp/next src
    or the next ref. Returns the patched payload, the changed field names
    and the skipped edits; ``edited_by`` is set only when something changed.
    """
    out = copy.deepcopy(payload)
    changed: list[str] = []
    skipped: list[str] = []
    urls = ([u or None for u in urls] + [None] * N_SLOTS)[:N_SLOTS]

    if view == 'main':
        if urls[0] != (out.get('url') or None):
            out['url'] = urls[0]
            changed.append('url')
        skipped += [f'slot {i + 1} (main has one image)' for i in range(1, N_SLOTS) if urls[i]]

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
        skipped += [
            f'slot {i + 1} (vid has first/last only)'
            for i in range(len(VID_REF_KEYS), N_SLOTS)
            if urls[i]
        ]

    elif view in ('inp', 'next', 'ref'):
        sec = VIEW_SECTION[view]
        media = _view_media(out, view)
        if view == 'ref':  # refs sit at their slot, named by list position
            refs_list = (_section_entry(out, 'ref') or {}).get('refs') or []
            pos = {id(r): j for j, r in enumerate(refs_list)}
            names = [f'refs[{pos[id(m)]}]' if m is not None else 'a ref' for m in media]
        else:
            names = {
                'inp': ['src', *(f'refs[{i}]' for i in range(N_SLOTS - 1))],
                'next': ['src', 'ref', *([''] * (N_SLOTS - 2))],
            }[view]
        for i in range(N_SLOTS):
            obj = media[i] if i < len(media) else None
            old = obj.get('url') if obj else None
            new = urls[i]
            if new == (old or None):
                continue
            if view in STILL_VIEWS and new and media_kind(new) != 'image':
                skipped.append(f'slot {i + 1} ({media_kind(new)} in a qwen21 still slot)')
                continue
            # a ref's kind sets its <Picture/Video/Audio N> tag: no kind swaps
            kind_old = (obj or {}).get('kind') or 'image'
            if view == 'ref' and obj is not None and new and media_kind(new) != kind_old:
                skipped.append(
                    f'slot {i + 1} ({kind_old} → {media_kind(new)} would renumber the prompt)'
                )
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


def media_kind(url: str | None) -> str | None:
    """'image' / 'video' / 'audio' by file suffix (None when empty / unknown)."""
    if not url:
        return None
    suf = Path(url.split('?')[0]).suffix.lower()
    if suf in suffix_img():
        return 'image'
    if suf in suffix_vid():
        return 'video'
    if suf in suffix_aud():
        return 'audio'
    return None


def missing_roles(slots: list[dict], verb: str) -> list[int]:
    """1-based slots whose role a role-only verb requires but lacks. Only slot 1
    must carry media + a role: it holds the prompt and references the other
    slots by their refdef slot number, whose roles may stay empty."""
    if verb not in ROLE_ONLY_VERBS or not slots:
        return []
    s1 = slots[0]
    return [] if s1.get('url') and (s1.get('role') or '').strip() else [1]


def continue_problems(slots: list[dict], verb: str) -> list[str]:
    """Why a pre-vid / post-vid instruction can't deploy: slot 1 must be the
    anchor clip (video), the other slots images / audio only."""
    if verb not in CONTINUE_VERBS or not slots:
        return []
    probs = []
    if media_kind(slots[0].get('url')) != 'video':
        probs.append('slot 1 needs the anchor clip (video)')
    probs += [
        f'slot {i + 1} is a video (new refs: images / audio)'
        for i, s in enumerate(slots[1:], 1)
        if media_kind(s.get('url')) == 'video'
    ]
    return probs


def join_args(slots: list[dict]) -> tuple[str, str | None]:
    """``chain_join`` inputs from the slots: slot 1 = the LAST clip of the
    chain, slot 2 = optionally the FIRST clip (a pre). Raises ValueError."""
    last = slots[0].get('url') if slots else None
    if media_kind(last) != 'video':
        raise ValueError('slot 1 needs the last clip of the chain (video)')
    first = slots[1].get('url') if len(slots) > 1 else None
    if first and media_kind(first) != 'video':
        raise ValueError('slot 2 (first clip, optional) must be a video')
    return str(last), (str(first) if first else None)


def refdef_payload(
    slots: list[dict],
    verb: str,
    prompt_kind: str,
    text: str,
    origin_scene_id: str | None = None,
) -> dict:
    """The instruction payload the enhancer builds its enhancer data from."""
    payload: dict[str, Any] = {
        'schema_id': SCHEMA_REFDEF,
        'verb': verb if verb in VERBS else VERBS[0],
        'refs': [
            {
                'slot': i + 1,
                'url': s.get('url') or None,
                'id': s.get('id') or None,
                'role': (s.get('role') or '').strip(),
                'media': media_kind(s.get('url')),
            }
            for i, s in enumerate(slots[:N_SLOTS])
        ],
        'kind': prompt_kind if prompt_kind in KINDS else 'hint',
        'text': text or '',
        'origin': {'scene_id': origin_scene_id} if origin_scene_id else None,
    }
    if verb in CONTINUE_VERBS:  # convenience: what the enhancer writes to continue
        payload['continue'] = {
            'dir': CONTINUE_VERBS[verb],
            'url': (slots[0].get('url') or None) if slots else None,
            'pin': CHAIN_PIN,
        }
    return payload


def update_payload(
    text: str | None,
    slots: list[dict],
    view: str | None = None,
    verb: str | None = None,
) -> tuple[dict, str, list[str], list[str]] | None:
    """Clipspace text with its reference urls replaced by the filled
    ``slots`` (``{url, id}``; empty slot = keep the clipspace's ref).

    Enhancer data: one view is patched with ``patch_iteration`` rules — the
    first that takes every filled slot without skips, in the order ``view``
    (the tab's), the payload's default view, then the other views newest
    first. The ``verb`` decides first (board task 162): a verb in
    ``VERB_VIEW`` (inp-* → ``inp``, ref / ref-novis → ``ref``) patches only
    that view, every other verb only the views no verb owns (main / vid /
    next), so sections the verb doesn't address stay byte-identical. If none
    fits cleanly, the first candidate is patched and its skips are reported;
    a missing section changes nothing. refdef.v1: url/id of each
    filled slot replaced; roles, verb and text stay. Returns
    ``(payload, view, changed, skipped)``; None when the clipspace is no
    enhancer payload.
    """
    st = parse_payload(text)
    if st is None:
        return None
    p = st['payload']
    slots = (list(slots) + empty_slots())[:N_SLOTS]

    if st['kind'] == 'refdef':
        out = copy.deepcopy(p)
        refs = out.setdefault('refs', [])
        by_slot = {r.get('slot'): r for r in refs if isinstance(r, dict)}
        changed: list[str] = []
        for i, s in enumerate(slots):
            if not s.get('url'):
                continue
            new = {'url': s.get('url'), 'id': s.get('id') or None}
            new_media = media_kind(s.get('url'))
            ref = by_slot.get(i + 1)
            if ref is None:
                refs.append({'slot': i + 1, **new, 'role': '', 'media': new_media})
            elif (ref.get('url'), ref.get('id') or None) != (new['url'], new['id']):
                ref.update(new, media=new_media)
            else:
                continue
            changed.append(f'refs[slot {i + 1}]')
        refs.sort(key=lambda r: r.get('slot', 0) if isinstance(r, dict) else 0)
        return out, '', changed, []

    def ts(v: str) -> str:
        return str((_section_entry(p, v) or {}).get('ts') or '')

    owned = set(VERB_VIEW.values())
    if verb in VERB_VIEW:
        target = VERB_VIEW[verb]
        if target not in st['views']:
            sec = VIEW_SECTION.get(target, target)
            return copy.deepcopy(p), target, [], [f'payload has no {sec} for verb {verb}']
        cands = [target]
    else:
        others = sorted(st['views'], key=ts, reverse=True)
        chain = (view, st['view'], *others)
        cands = list(dict.fromkeys(v for v in chain if v in st['views'] and v not in owned))
        if not cands:
            return copy.deepcopy(p), '', [], [f'no section for verb {verb} in the payload']
    results = []
    for v in cands:
        olds = [s.get('url') for s in view_slots(p, v)]
        urls = [s.get('url') or old for s, old in zip(slots, olds, strict=True)]
        out, changed, skipped = patch_iteration(p, v, urls)
        if not skipped:
            return out, v, changed, skipped
        results.append((out, v, changed, skipped))
    return results[0]


def hist_step(pos: int | None, n: int, step: int) -> int | None:
    """Save-history pointer after one ◀ (-1) / ▶ (+1) step over ``n`` saves
    (oldest first). ``None`` = the current (working) config, which always sits
    after the newest save."""
    cur = n if pos is None else min(pos, n)
    new = max(0, min(n, cur + step))
    return None if new >= n else new


def enh_clip(text: str | None) -> str | None:
    """Clipspace text → compact enhancer-data JSON, None for anything else."""
    st = parse_payload(text)
    if st is None or st['kind'] != 'iteration':
        return None
    return json.dumps(st['payload'], ensure_ascii=False)


def snap_to_doc(snap: dict) -> dict:
    """UI snapshot → Mongo doc. The state rides as a JSON string (enhancer
    payloads may hold keys Mongo rejects); verb / mode / scene are queryable."""
    st = snap.get('state') or {}
    p = st.get('payload') or {}
    return {
        **{k: snap.get(k) for k in SNAP_KEYS if k != 'state'},
        'state_json': json.dumps(snap.get('state'), ensure_ascii=False),
        'mode': 'enhancer' if st.get('kind') == 'iteration' else 'instruction',
        'scene_id': p.get('scene_id') or (p.get('origin') or {}).get('scene_id'),
        # the clipspace's enhancer data at save time (restored while browsing)
        'clip_json': snap.get('clip'),
        'has_clip': bool(snap.get('clip')),
    }


def norm_cat(cat: str | None) -> str | None:
    """Category dropdown value → stored category / filter (None = all / none)."""
    cat = (cat or '').strip()
    return None if not cat or cat == CAT_ALL else cat


def doc_to_snap(doc: dict) -> dict:
    snap = {k: doc.get(k) for k in SNAP_KEYS if k != 'state'}
    snap['state'] = json.loads(doc.get('state_json') or 'null')
    snap['clip'] = doc.get('clip_json')
    return snap


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
        self._dbc = dbc
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
        """Pullable slot media: an existing image, video/clip or audio file."""
        if not url or not (is_img_or_vid(url) or is_aud(url)):
            return False
        return url.startswith(('http://', 'https://')) or Path(url).is_file()

    def images_from_clipspace(self, text: str | None) -> list[tuple[str, str | None]]:
        """Clipspace → [(url, img_id)] for an img/clip url / url list / img id /
        scene id clipspace; [] when any non-blank line is not a usable image or
        clip (so freeform text never half-fills slots)."""
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
        """First type-matching (image or clip) entry of any pull data: enhancer data
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
        real path for deploy. A clip shows its first frame with a ▶ mark."""
        if not url:
            return None
        if url.startswith(('http://', 'https://')):
            return url
        if is_aud(url):
            return RefdefTab._waveform(url)
        if is_vid(url):
            frame = ref_frame(url, 'first')
            if frame is None:
                return None
            im = frame.convert('RGB')
            im.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE))
            return RefdefTab._mark_clip(im)
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

    @staticmethod
    def _waveform(url: str) -> Image.Image | None:
        """Audio slot preview: min/max waveform + ♪ badge + name/duration."""
        w, h = PREVIEW_SIZE, PREVIEW_SIZE // 2
        try:
            peaks: list[float] = []
            dur = 0.0
            with av.open(url) as container:
                stream = container.streams.audio[0]
                for frame in container.decode(stream):
                    a = frame.to_ndarray()
                    peaks.append(float(abs(a).max()) if a.size else 0.0)
                    dur += frame.samples / (frame.sample_rate or 1)
        except Exception:  # noqa: BLE001 - unreadable audio -> empty preview
            return None
        im = Image.new('RGB', (w, h), (24, 28, 36))
        draw = ImageDraw.Draw(im)
        if peaks:
            top = max(peaks) or 1.0
            mid = h // 2
            for x in range(w):
                v = peaks[min(len(peaks) - 1, x * len(peaks) // w)] / top
                d = max(1, int(v * (h // 2 - 16)))
                draw.line([(x, mid - d), (x, mid + d)], fill=(110, 170, 255))
        badge = ImageDraw.Draw(im, 'RGBA')
        badge.rectangle((0, h - 30, w, h), fill=(0, 0, 0, 150))
        badge.text((10, h - 24), f'♪ {Path(url).name} · {dur:.1f}s', fill=(255, 255, 255))
        return im

    @staticmethod
    def _mark_clip(im: Image.Image) -> Image.Image:
        """Overlay a play badge (top-left) so clip slots read as clips."""
        r = max(12, min(im.size) // 14)
        cx = cy = r + r // 2
        draw = ImageDraw.Draw(im, 'RGBA')
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(0, 0, 0, 160))
        k = r * 0.55
        draw.polygon(
            [(cx - k * 0.6, cy - k), (cx - k * 0.6, cy + k), (cx + k, cy)],
            fill=(255, 255, 255, 230),
        )
        return im

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
            gr.Info(f'no free slot: {n_drop} item(s) dropped', duration=0.5)
        if not slots:
            return [gr.update()] * n_out
        for i, (url, id_img) in zip(slots, imgs, strict=False):
            # enhancer mode keeps the (payload-owned) role; instruction mode starts blank
            role = gr.update() if self._is_enh(state) else ''
            upd[3 * i : 3 * i + 3] = [self._preview(url), id_img or url, role]
        dropped = f' ({n_drop} dropped, no free slot)' if n_drop else ''
        placed = [url for _, (url, _id) in zip(slots, imgs, strict=False)]
        n_clips = sum(1 for url in placed if is_vid(url))
        n_aud = sum(1 for url in placed if is_aud(url))
        what = f'{len(placed) - n_clips - n_aud} img(s)'
        what += (f' + {n_clips} clip(s)' if n_clips else '') + (
            f' + {n_aud} audio' if n_aud else ''
        )
        status = f'pulled {what} → slot {", ".join(str(i + 1) for i in slots)}'
        return [*[gr.update()] * 3, *upd, *[gr.update()] * 6, status + dropped]

    def _on_reset(self):
        return [*self._load(None), 'reset']

    # -- save history ------------------------------------------------- #
    @staticmethod
    def _snap(state, idx, verb, kind, text, *refs_roles) -> dict:
        """UI config + the clipspace's enhancer data (if it holds any)."""
        return {
            'clip': enh_clip(pyperclip.paste()),
            'state': state,
            'idx': idx,
            'refs': [refs_roles[2 * i] or '' for i in range(N_SLOTS)],
            'roles': [refs_roles[2 * i + 1] or '' for i in range(N_SLOTS)],
            'verb': verb,
            'kind': kind,
            'text': text or '',
        }

    @staticmethod
    def _restore_clip(snap: dict | None) -> str:
        """Put a snapshot's enhancer data back on the (volatile) clipspace →
        status note ('' when it carries none)."""
        clip = (snap or {}).get('clip')
        if not clip:
            return ''
        clip_copy(clip)
        p = json.loads(clip)
        return f' · clipspace ← enhancer data (scene `{p.get("scene_id")}`, rev {p.get("rev")})'

    def _load_snap(self, snap: dict) -> list[Any]:
        """``_load`` outputs for a saved / drafted UI snapshot."""
        st = snap.get('state')
        enh = self._is_enh(st)
        idx = snap.get('idx') or 0
        slot_vals: list[Any] = []
        pad = [''] * N_SLOTS  # saves from before a slot-count change
        for ref, role in zip(
            (list(snap['refs']) + pad)[:N_SLOTS],
            (list(snap['roles']) + pad)[:N_SLOTS],
            strict=True,
        ):
            url = self.resolve_ref(ref)[0] if ref else None
            slot_vals += [self._preview(url), ref, gr.update(value=role, interactive=not enh)]
        raw = json.dumps(st['payload'], indent=2, ensure_ascii=False) if st else ''
        return [
            st,
            idx,
            raw,
            *slot_vals,
            gr.update(value=snap.get('kind') or 'hint', interactive=not enh),
            snap.get('verb') or VERBS[0],
            gr.update(value=snap.get('text') or '', interactive=not enh),
            self._source_md(st, idx),
            self._entry_md(st, idx),
            gr.update(
                choices=st['views'] if enh else [],
                value=st['view'] if enh else None,
                visible=enh,
            ),
        ]

    def _col(self):
        return self._dbc._get_collection(SAVES_COLLECTION)

    def _save_ids(self, cat: str | None = None) -> list[dict]:
        """[{_id, ts, category}] of the saves in category ``cat`` (all when
        unset), oldest first ([] without a DB)."""
        col = self._col()
        if col is None:
            return []
        flt = {'category': c} if (c := norm_cat(cat)) else {}
        proj = {'_id': 1, 'ts': 1, 'category': 1, 'has_clip': 1}
        return list(col.find(flt, proj).sort([('ts', 1), ('_id', 1)]))

    def _categories(self) -> list[str]:
        col = self._col()
        cats = sorted(c for c in col.distinct('category') if c) if col is not None else []
        return [CAT_ALL, *cats]

    @staticmethod
    def _ts_str(ts: datetime | None) -> str:
        if ts is None:
            return '?'
        return ts.replace(tzinfo=timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')

    @classmethod
    def _hist_md(cls, pos: int | None, saves: list[dict]) -> str:
        n = len(saves)
        if pos is None:
            return f'**current** · {n} save{"s" if n != 1 else ""}'
        s = saves[pos]
        cat = f' · `{s["category"]}`' if s.get('category') else ''
        clip = ' · ⎘ enh' if s.get('has_clip') else ''
        return f'**save {pos + 1}/{n}** · {cls._ts_str(s.get("ts"))}{cat}{clip}'

    def _on_save(self, cat, state, idx, verb, kind, text, *refs_roles):
        """Save the shown config under category ``cat`` (a new typed-in one
        joins the dropdown)."""
        cur = {'pos': None, 'draft': None}
        col = self._col()
        if col is None:
            gr.Warning('save: no DB connection', duration=0.5)
            return 'save: no DB connection', cur, gr.update(), gr.update()
        doc = snap_to_doc(self._snap(state, idx, verb, kind, text, *refs_roles))
        doc['category'] = norm_cat(cat)
        last = col.find_one({}, sort=[('ts', -1), ('_id', -1)])
        if last and all(last.get(k) == v for k, v in doc.items()):
            gr.Info('unchanged since the last save', duration=0.5)
            md = self._hist_md(None, self._save_ids(cat))
            return 'save: unchanged since the last save', cur, md, gr.update()
        doc['ts'] = datetime.now(timezone.utc).replace(tzinfo=None)
        col.insert_one(doc)
        saves = self._save_ids(cat)
        where = f' in `{doc["category"]}`' if doc['category'] else ''
        gr.Success(f'saved #{len(saves)}{where}', duration=0.5)
        return (
            f'saved #{len(saves)}{where} ({doc["mode"]}'
            f'{" + clipspace enhancer data" if doc["has_clip"] else ""})'
            f' · {self._ts_str(doc["ts"])}',
            cur,
            self._hist_md(None, saves),
            gr.update(choices=self._categories(), value=cat),
        )

    def _on_cat(self, hist: dict | None, cat):
        """Category filter changed: a shown save's index no longer applies, so
        go back to the current config (the parked draft)."""
        n_out = 3 + 3 * N_SLOTS + 7
        hist = hist or {'pos': None, 'draft': None}
        md = self._hist_md(None, self._save_ids(cat))
        if hist['pos'] is None or not hist['draft']:
            return [*[gr.update()] * n_out, {'pos': None, 'draft': None}, md]
        msg = f'category `{norm_cat(cat) or CAT_ALL}` · back to the current config'
        msg += self._restore_clip(hist['draft'])
        return [*self._load_snap(hist['draft']), msg, {'pos': None, 'draft': None}, md]

    def _on_del(self, hist: dict | None, cat):
        """Delete the shown save — two clicks: the first arms it (any other
        action disarms). Then show the next older save, else the next newer,
        else the current config."""
        n_out = 3 + 3 * N_SLOTS + 7
        hist = hist or {'pos': None, 'draft': None}
        saves, col = self._save_ids(cat), self._col()
        pos = hist['pos']
        keep = [*[gr.update()] * n_out]
        if pos is None or pos >= len(saves) or col is None:
            gr.Info('no save shown (◀ to pick one)', duration=0.5)
            return [*keep, 'delete: no save shown', hist, gr.update(), gr.update()]
        target = saves[pos]['_id']
        if hist.get('arm') != str(target):
            gr.Warning('click 🗑 again to delete this save', duration=1)
            msg = f'delete save {pos + 1}/{len(saves)}? click 🗑 again'
            return [*keep, msg, dict(hist, arm=str(target)), gr.update(), gr.update()]
        col.delete_one({'_id': target})
        saves = self._save_ids(cat)
        new = pos - 1 if pos > 0 else (0 if saves else None)
        msg = f'deleted save {pos + 1}'
        doc = col.find_one({'_id': saves[new]['_id']}) if new is not None else None
        if doc is None:
            new, snap, hist = None, hist['draft'], {'pos': None, 'draft': None}
            msg += ' · back to the current config'
        else:
            snap, hist = doc_to_snap(doc), {'pos': new, 'draft': hist['draft']}
            msg += f' · showing save {new + 1}/{len(saves)}'
        gr.Success(f'deleted save {pos + 1}', duration=0.5)
        msg += self._restore_clip(snap)
        outs = self._load_snap(snap) if snap else keep
        cats = gr.update(choices=self._categories())
        return [*outs, msg, hist, self._hist_md(new, saves), cats]

    def _on_hist(
        self, hist: dict | None, step: int, cat, state, idx, verb, kind, text, *refs_roles
    ):
        """◀ / ▶ through the saves of category ``cat``; leaving the current
        config drafts it so ▶ past the newest save restores it (even when it
        was never saved)."""
        n_out = 3 + 3 * N_SLOTS + 7
        hist = hist or {'pos': None, 'draft': None}
        saves = self._save_ids(cat)
        pos = hist['pos']
        if pos is not None and pos >= len(saves):  # saves vanished meanwhile
            pos = len(saves) - 1 if saves else None
        new = hist_step(pos, len(saves), step)
        if new == pos:
            edge = 'oldest save' if step < 0 else 'current config'
            gr.Info(f'already at the {edge}', duration=0.5)
            return [*[gr.update()] * n_out, hist, self._hist_md(pos, saves)]
        draft = hist['draft']
        if pos is None:
            draft = self._snap(state, idx, verb, kind, text, *refs_roles)
        if new is None:
            snap, hist, msg = draft, {'pos': None, 'draft': None}, 'back to the current config'
        else:
            col = self._col()
            doc = col.find_one({'_id': saves[new]['_id']}) if col is not None else None
            if doc is None:
                gr.Warning('save not found', duration=0.5)
                return [*[gr.update()] * n_out, hist, self._hist_md(pos, saves)]
            snap, hist = doc_to_snap(doc), {'pos': new, 'draft': draft}
            msg = f'loaded save {new + 1}/{len(saves)} · {self._ts_str(doc.get("ts"))}'
        msg += self._restore_clip(snap)
        return [*self._load_snap(snap), msg, hist, self._hist_md(new, saves)]

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
        if miss := missing_roles(slots, verb):
            where = ', '.join(str(n) for n in miss)
            gr.Warning(f'{verb}: slot {where} needs media + a role', duration=1)
            return (
                f'NOT deployed: `{verb}` builds the prompt from roles only — '
                f'slot {where} needs media + a role'
            )
        origin = None
        if state and state['kind'] == 'refdef':
            origin = (state['payload'].get('origin') or {}).get('scene_id')
        if probs := continue_problems(slots, verb):
            gr.Warning(f'{verb}: {"; ".join(probs)}', duration=1)
            return f'NOT deployed: `{verb}` — {"; ".join(probs)}'
        payload = refdef_payload(slots, verb, kind, text, origin)
        clip_copy(json.dumps(payload, ensure_ascii=False))
        n = sum(1 for s in slots if s['url'])
        msg = f'deployed instruction `{verb}` ({n}/{N_SLOTS} slots, kind={kind})'
        note = trigger_enhancer() if auto else 'auto-trigger off'
        print(f'[refdef_tab:info] deploy {verb}: {note}')
        return f'{msg} · {note}'

    def _on_update(self, state: dict | None, verb: str | None, *refs_roles):
        """Rewrite the CURRENT clipspace's reference urls from the slots —
        script only, never triggers the enhancer."""
        slots = self._slots_from_ui(list(refs_roles))
        view = state['view'] if self._is_enh(state) else None  # type: ignore[index]
        res = update_payload(pyperclip.paste(), slots, view, verb)
        if res is None:
            gr.Warning('update: clipspace is no enhancer data / refdef', duration=0.5)
            return 'update: clipspace is no enhancer data / refdef instruction'
        payload, used_view, changed, skipped = res
        where = f' (view `{used_view}`)' if used_view else ''
        note = f' · NOT updated: {", ".join(skipped)}' if skipped else ''
        if not changed and skipped:
            gr.Warning(f'update: nothing updated, {len(skipped)} NOT updated', duration=0.5)
            return f'update{where}: nothing updated, clipspace untouched{note}'
        if not changed:
            gr.Info('update: refs already match', duration=0.5)
            return f'update{where}: refs already match, clipspace untouched'
        clip_copy(json.dumps(payload, ensure_ascii=False))
        print(f'[refdef_tab:info] update{where}: {", ".join(changed)}')
        if skipped:
            gr.Warning(f'updated {len(changed)}, {len(skipped)} NOT updated', duration=0.5)
        else:
            gr.Success(f'updated {len(changed)} ref(s)', duration=0.5)
        return f'updated clipspace{where}: {", ".join(changed)}{note}'

    def _on_join(self, *refs_roles):
        """⛓ join (board task 172): script only, no agent — walk the chain from
        slot 1 (last clip) / slot 2 (first clip, optional), write the joined
        master to CHAIN_OUT_DIR and toast the path + seam summary."""
        slots = self._slots_from_ui(list(refs_roles))
        try:
            last, first = join_args(slots)
            rep = chain_join(last, first)
        except Exception as e:
            gr.Warning(f'join: {e}', duration=3)
            return f'join failed: {e}'
        name = Path(rep['out']).name
        n = len(rep['clips'])
        summary = seam_summary(rep) or 'single clip'
        gr.Success(f'joined {n} clips → {name}', duration=3)
        print(f'[refdef_tab:info] join {rep["out"]}: {summary}')
        return (
            f'joined {n} clips ({rep["seconds"]:.1f} s) → `{rep["out"]}`  \n'
            f'seams (MAD /255, plain→written (motion before/after)): {summary}'
        )

    # -- UI build (call inside the app's gr.Blocks context) ------------- #
    def build(self) -> None:
        with gr.Tab('refdef', elem_id='refdef_tab'):
            state = gr.State(None)  # parse_payload() result of the last enhancer pull
            idx = gr.State(0)  # pointed prompt_data entry (display only)
            # save-history pointer: pos None = current config; draft = the current
            # config parked while a save is shown
            hist = gr.State({'pos': None, 'draft': None})

            with gr.Row():
                pull_btn = gr.Button('⟲ pull', variant='primary', scale=1)
                deploy_btn = gr.Button('⇪ deploy', elem_id='refdef-deploy', scale=1)
                update_btn = gr.Button('⇄ update', scale=1)
                join_btn = gr.Button('⛓ join', scale=1)
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
                    # instruction deploy → TRIGGER_CMD to the herdr agent, only when idle
                    label='auto trigger enhancer',
                    scale=1,
                )
            view = gr.Radio([], label='view (enhancer data section)', visible=False)
            with gr.Row(equal_height=True):
                prev_btn = gr.Button('◀', scale=0, min_width=40)
                with gr.Column(scale=0, min_width=230):
                    hist_md = gr.Markdown(self._hist_md(None, self._save_ids()))
                next_btn = gr.Button('▶', scale=0, min_width=40)
                save_btn = gr.Button('💾', scale=0, min_width=40)
                del_btn = gr.Button('🗑', scale=0, min_width=40)
                # ◀ ▶ filter; 💾 files under it; typing a name starts a new one
                with gr.Column(scale=0, min_width=80):
                    gr.Markdown('category:', elem_id='refdef-cat-label')
                cat = gr.Dropdown(
                    self._categories(),
                    value=CAT_ALL,
                    allow_custom_value=True,
                    show_label=False,
                    container=False,
                    scale=2,
                    min_width=200,
                )
                gr.Column(scale=3)  # spacer

            # input is the clipspace only: images are display-only, the slot
            # ref (img id or url) rides in a per-slot State
            imgs, refs, roles, slot_pulls, clears = [], [], [], [], []
            for row0 in range(0, N_SLOTS, SLOTS_PER_ROW):
                with gr.Row(equal_height=True):
                    for i in range(row0, min(N_SLOTS, row0 + SLOTS_PER_ROW)):
                        with gr.Column():
                            imgs.append(
                                gr.Image(
                                    type='filepath',
                                    label=f'slot {i + 1}',
                                    height=300,
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
            with gr.Accordion('source / concepts / triggers', open=False):
                source_md = gr.Markdown(self._source_md(None, 0))
                entry_md = gr.Markdown()
            with gr.Accordion('raw payload (as pulled / last view switch)', open=False):
                raw = gr.Code(language='json', interactive=False)

            refs_roles = [c for pair in zip(refs, roles, strict=True) for c in pair]
            slot_outs = [c for trip in zip(imgs, refs, roles, strict=True) for c in trip]
            load_outs = [state, idx, raw, *slot_outs, kind, verb, text, source_md, entry_md, view]

            snap_ins = [state, idx, verb, kind, text, *refs_roles]
            cur_hist = {'pos': None, 'draft': None}

            def pull(h, *a):
                out = self._on_pull(*a)
                # a pull that changed something makes the shown config the current one
                return [*out, cur_hist if isinstance(out[-1], str) else h]

            def hist_refresh(h, c):
                return self._hist_md(h['pos'], self._save_ids(c))

            pull_btn.click(pull, [hist, state, *refs], [*load_outs, status, hist]).then(
                hist_refresh, [hist, cat], [hist_md]
            )
            reset_btn.click(
                lambda: [*self._on_reset(), cur_hist], [], [*load_outs, status, hist]
            ).then(hist_refresh, [hist, cat], [hist_md])
            save_btn.click(self._on_save, [cat, *snap_ins], [status, hist, hist_md, cat])
            del_btn.click(self._on_del, [hist, cat], [*load_outs, status, hist, hist_md, cat])
            cat.input(self._on_cat, [hist, cat], [*load_outs, status, hist, hist_md])
            view.input(self._on_view, [state, view, *refs], [*load_outs, status])
            for btn, step in ((prev_btn, -1), (next_btn, 1)):
                btn.click(
                    lambda h, c, *a, step=step: self._on_hist(h, step, c, *a),
                    [hist, cat, *snap_ins],
                    [*load_outs, status, hist, hist_md],
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
            update_btn.click(self._on_update, [state, verb, *refs_roles], [status])
            join_btn.click(self._on_join, refs_roles, [status])


REFDEF_HEAD = r"""
<style>
#refdef-deploy { background: #2e7d32 !important; border-color: #2e7d32 !important;
  color: #fff !important; }
#refdef-cat-label { text-align: right; }
#refdef-deploy:hover { background: #388e3c !important; }
</style>
"""
