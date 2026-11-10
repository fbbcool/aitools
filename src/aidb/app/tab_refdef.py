"""Refdef tab of the AIDB scene app (reference definition).

N_SLOTS (7) fixed reference slots (image + short role text) plus one prompt /
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
    ``img-fsw-novis`` = qwen21 head swap (``SWAP_VERBS``): slot 1 = target, slot 2 =
    reference head, both images; the enhancer writes a ``head_swap:`` prompt into
    ``prompts_inp`` without looking at the images (roles optional — an empty one
    deploys as ``SWAP_DEFAULT_ROLES``: slot 1 head/face replaced by slot 2's; + hint).
    ``inp-qfix`` = qwen21 quickfix (``QFIX_VERBS``, board FEATURE 180) — NO
    instruction, NO enhancer: deploy writes enhancer data itself
    (``qfix_payload``): ``prompts_inp`` with slot 1 = edit target (+ its 🎭 mask
    → mask mode, else nomask), slots 2.. = 0-2 still refs (image 2 / 3 in slot
    order), slot 1's role = the ``prompt_qwen21`` edit instruction verbatim.
    ``ref`` = the slots are MiniMax H3 ref2va picture references
    (``<Picture i>``, board task 159); like ``enh``: slot 1 required, stills. With
    *auto-trigger* on, deploy then prompts the ``enhancer`` agent in herdr
    session ``xlasm`` with ``/refdef`` — only when it is idle.

H3 ref budget (``H3_VERBS`` = ref / ref-novis / pre-vid / post-vid, FEATURE t181):
at most 6 pictures, 2 clips, 2 audio files and 12 refs in total (a clip with
``audio: true`` counts its soundtrack too); more → 2 s toast, nothing deployed.
Under pre-/post-vid the anchor (slot 1) is pinned frames, not a ref; its carried
refs with ``use: true`` count with the new ones, a file both carried and in a slot
once (t191). t190 frame pins (an image slot whose role starts with ``first frame``
/ ``last frame``) are outside the budget; first + post-vid / last + pre-vid → toast.

``pre-vid`` / ``post-vid`` (H3 clip chains, board task 172): slot 1 = the
anchor clip (video), the other slots optional NEW image / audio / clip refs (a
clip = the cut-to shot after the pinned opening, t191); the text is the beat hint. Deploys like ``ref`` (+ a ``continue`` hint ``{dir, url,
pin}``); the enhancer writes ``prompts_ref[].continue``. Slot 1 must carry its
enhancer payload (the refs the enhancer inherits): a merge / re-encode is mapped
to its ``fbbcool_temp_<id>`` master by the 5-char id in its name
(``anchor_master``), else deploy is refused. ``⛓ join`` is
script-only like ⇄ update: slot 1 = the LAST clip of a chain, slot 2 = the
FIRST (a pre, optional) → ``ait.tools.videos.chain_join`` writes the joined
master to ``~/Downloads/000_comfy/`` and toasts path + seam summary.

Slot-1 area (FEATURE t185): slot 1 sits left; when its clip carries refs (the
rendered ``prompts_ref`` entry embedded in it, or in its ``fbbcool_temp`` master
via ``anchor_master`` — ``carry_of``), a panel right of it shows them, one cell
per ref (preview, ``tag · desc``, ``≡ slot N`` when a slot holds the same media)
with a ✅/🚫 use switch, all on after every slot-1 change, not saved. A
pre-/post-vid deploy sends them as refdef.v1 ``inherit: [{n, tag, kind, url,
desc, use}]`` (``inherit_list``); the enhancer inherits only ``use: true``.

``✅`` / ``🚫`` (per slot) enables / disables a slot: a disabled slot keeps its
image + role in the tab (dimmed) but deploys, updates, joins and view-switches as
an empty slot (enhancer mode: its replacement is not patched in). New content in
the slot (pull, slot ⟲, ✕) switches it back on.

``🖼`` / ``👁`` (per slot, FEATURE t189) switches an image / video slot between a
direct pixel ref (🖼, default) and vision (👁, a big eye over the preview): the
deployed ref gets ``use: "vision"``, the enhancer looks at the media (even on
``*-novis`` verbs), writes it into the prompt as text and ships no pixels for it
— so it is outside the H3 ref budget and its 🎭 mask is ignored. Locked (always
🖼): ``img-fsw-novis`` slots 1 + 2, slot 1 of pre-/post-vid, inp-mask,
inp-nomask, pickup; audio has no 👁. Without the enhancer (inp-qfix, enhancer-data deploys) it is ignored with a
status note. 💾 saves it; slot ⟲ / ✕ reset it to 🖼.

A click on a slot's (local) image opens the shared brush editor fullscreen
(task 193; Esc / ✕ closes it): paint the area to mask, ✓ stores it (⎘ = ✓ + the masked image's path on the clipspace, ready for
a ComfyUI quickload), 🗑 removes it. A mask belongs to the source image (fixed
path in ``MASK_DIR``; repainting replaces it), so every slot / pull / save
showing that image shows it (red tint). An instruction deploy adds ``mask`` = a
``1xlasm_enhancer.mask.v1`` raster object ``{schema_id, type, url, w, h, sha}`` to
the image's ref (board task 175). Enhancer data: media ``mask`` objects (main =
``url_mask``; raster or json shapes) are tinted into the slots; patching puts the
tab's mask on its media and drops the mask of a replaced url. Per slot, 🟥/⬜
switches masking on/off (off = no tint, deploy / ⇄ update / patching send the
slot WITHOUT a mask and drop a payload mask from its media; the painted mask
file stays; new slot content switches back on), 🧽 deletes the slot image's
painted mask.

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
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote

import av
import gradio as gr
import pyperclip
from PIL import Image, ImageChops, ImageDraw, ImageOps, PngImagePlugin

from ait.tools.files import (
    is_aud,
    is_img,
    is_img_or_vid,
    is_vid,
    suffix_aud,
    suffix_img,
    suffix_vid,
)
from ait.tools.videos import (
    CHAIN_PIN,
    anchor_master,
    chain_join,
    clip_refs,
    ref_frame,
    seam_summary,
)
from aidb.scene.scene_common import SceneDef
from aidb.scene.scene_image_manager import SceneImageManager
from aidb.scene.scene_manager import SceneManager

N_SLOTS: Final = 10  # H3 max distinct media: 6 pictures + 2 clips + 2 audio files
SLOTS_PER_ROW: Final = 3  # slots 2.. (slot 1 has its own row)
ROLE_LINES: Final = 2  # role box height (slot 1: double)
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
    'img-fsw-novis',
    'inp-qfix',
    'ref-img',
)
# H3 clip-chain continuations (board task 172): slot 1 = the anchor clip
# (FbbcoolSaveVideo master, video only), the other slots optional NEW refs
# (images / audio / clips = cut-to shots, t191); the enhancer writes prompts_ref[].continue = {dir, url, pin}
CONTINUE_VERBS: Final = {'pre-vid': 'pre', 'post-vid': 'post'}
# verbs whose prompt is built from the slot roles alone (enhancer never looks at
# the media): slot 1 needs media + a role; it references the other slots by number
ROLE_ONLY_VERBS: Final = ('ref-novis',)
# MiniMax H3 ref2va budget (FEATURE t181 plan v3): per kind 6 pictures / 2 clips /
# 2 audio files, and at most 12 refs in total where a clip's soundtrack counts as
# one more ref iff the ref carries ``audio: true``. Same rule as the enhancer's
# refusal; checked before deploy (``ref_budget_problems``).
H3_VERBS: Final = ('ref', 'ref-novis', 'pre-vid', 'post-vid')
H3_REF_CAP: Final = {'image': 6, 'video': 2, 'audio': 2}
H3_REF_TOTAL: Final = 12
# t190 frame pins (enhancer refdef.py PIN_RE / PIN_CONFLICT): an image slot whose
# role starts with "first frame" / "last frame" is pinned (AddGuide 0 / -1), no ref
PIN_RE: Final = re.compile(r'^\s*(first|last)[\s_-]*frame\b', re.I)
PIN_CONFLICT: Final = {
    'post-vid': ('first', "post-vid already pins the anchor's tail at frame 0"),
    'pre-vid': ('last', "pre-vid already pins the anchor's head at the end"),
}
# qwen21 head swap (agent-comfy workflows/qwen21-headswap.json, BFS head LoRA): slot 1 =
# target (body / pose / light / bg = <image1>), slot 2 = reference head (<image2>), both
# stills, nothing else. The enhancer writes a ``head_swap:`` prompt_qwen21 into
# prompts_inp without vision — from the roles (optional) + hint alone.
SWAP_VERBS: Final = ('img-fsw-novis',)
# empty swap roles = the default swap semantics (slot 1 head/face replaced by slot 2's),
# written into the instruction so the enhancer never sees a blank role
SWAP_DEFAULT_ROLES: Final = (
    'target: keep body, pose, outfit, light and background; its head/face gets replaced',
    'reference head: the head/face that replaces the head/face of slot 1',
)
# qwen21 reference-to-image (FEATURE t187, agent-comfy workflows/qwen21-ref.json):
# NOVIS — the enhancer never looks at the media, the prompt comes from roles + text.
# Slots 1-5 = equal still refs (5 since t187 comfyos follow-up) (image 1..N compacted in slot order; empty roles
# stay empty, no defaults), at least one; slots 6+ empty. 🎭 masks are IGNORED:
# never emitted for this verb (deploy status names the slots).
IMG_REF_VERBS: Final = ('ref-img',)
IMG_REF_MAX: Final = 5
# qwen21 quickfix (board FEATURE 180, ComfyUI userdata workflows/qwen21-quickfix.json):
# NO enhancer roundtrip — deploy scripts the enhancer data itself (``qfix_payload``):
# slot 1 = edit target (+ its 🎭 mask → mask mode, else nomask), slots 2.. = 0-2
# still refs (= image 2 / image 3, in slot order), slot 1's role = the prompt_qwen21
# edit instruction verbatim. Never triggers the enhancer.
QFIX_VERBS: Final = ('inp-qfix',)
QFIX_MAX_REFS: Final = 2
QFIX_TOAST_OK_S: Final = 0.5  # deploy success toast
QFIX_TOAST_WARN_S: Final = 2  # guard refusal / failure toast
SCHEMA_ITERATION_OUT: Final = '1xlasm_enhancer.iteration.v6.10'  # what qfix writes
QFIX_MADE_BY: Final = 'refdef.inp-qfix'  # its payload marker (pull: instruction → slot 1 role)
# ⇄ update: the enhancer-data view (section) a verb owns (board task 162). A verb
# here patches ONLY its view; the other verbs never touch these views.
VERB_VIEW: Final = {
    'inp-mask': 'inp',
    'inp-nomask': 'inp',
    'img-fsw-novis': 'inp',
    'inp-qfix': 'inp',
    'ref': 'ref',
    'ref-novis': 'ref',
}
REF_LABEL: Final = {'image': 'picture', 'video': 'clip', 'audio': 'audio'}  # ref view
STILL_VIEWS: Final = ('inp',)  # qwen21 still slots: images only
VID_REF_KEYS: Final = ('first', 'last')  # prompts_vid.refs keys for slots 2/3
PREVIEW_SIZE: Final = 768  # slot preview edge (px)
MAX_PULL_LINES: Final = 50  # longer clipspaces are no image lists
# auto-trigger: after an instruction deploy, prompt the enhancer agent in its
# herdr session with TRIGGER_CMD (board task 150) — only when it is idle
HERDR_SESSION: Final = 'xlasm'
HERDR_AGENT: Final = 'xlasmos'  # 1xlasm-enhancer's herdr agent name
TRIGGER_CMD: Final = '/refdef'
HERDR_READY: Final = ('idle', 'done')
HERDR_TIMEOUT_S: Final = 10
SAVES_COLLECTION: Final = 'refdef_saves'  # 💾 save history (see build)
# predefined prompts (FEATURE t188): {name (unique), category, models, prompt, ts};
# the dropdown above the text box fills it, ➕ upserts by name, 🗑 deletes
PROMPTS_COLLECTION: Final = 'refdef_prompts'
PROMPT_MODELS_DEFAULT: Final = ('generic',)
PROMPT_SEED: Final = (
    {
        'name': 'facesheet',
        'category': 'character-gen',
        'models': ['qwen21'],
        'prompt': 'face reference sheet, 3×2 grid on plain grey: front, three-quarter '
        'left/right, profile left/right, neutral close-up; same woman as image 1–3, '
        'landscape, no clothes',
    },
)
CAT_ALL: Final = '(all)'  # category filter = every save; saved as uncategorized
SNAP_KEYS: Final = ('state', 'idx', 'refs', 'roles', 'verb', 'kind', 'text', 'vision')
# 🎭 hand-drawn masks: one per source image (repainting replaces it), at a fixed
# path derived from the image path. ``*__mask.png`` = L (white = masked);
# ``*__masked.png`` = the image as RGBA with alpha 0 where masked — what ComfyUI
# loaders (FbbcoolImgQuickload, LoadImage) read as their mask (mask = 1 - alpha).
MASK_DIR: Final = Path.home() / 'Downloads' / '000_comfy' / 'refdef_masks'
MASK_EDIT_SIZE: Final = 1536  # editor canvas edge (px); the mask is scaled back up
MASK_TINT: Final = (255, 0, 0)  # slot-preview overlay of the masked area
SCHEMA_MASK: Final = '1xlasm_enhancer.mask.v1'  # board task 175, comment 628
SCHEMA_MASK_PREFIX: Final = '1xlasm_enhancer.mask.'
MASK_KEY_MAIN: Final = 'url_mask'  # the top-level scene image's mask (sibling of url)
MASK_ICON_ON: Final = '🟥'  # per-slot masking switch: on (mask deployed / tinted)
MASK_ICON_OFF: Final = '⬜'  # off: slot deployed without any mask


# t193: the fullscreen editor overlay stays mounted (a canvas mounted while hidden
# never loads its image) and is shown / hidden by a CSS class
def mask_overlay(show: bool) -> dict:
    """Update showing / hiding the fullscreen mask editor overlay."""
    return gr.update(elem_classes=['refdef-mask-on' if show else 'refdef-mask-off'])


SLOT_ICON_ON: Final = '✅'  # per-slot enable switch: on (slot deployed)
SLOT_ICON_OFF: Final = '🚫'  # off: slot kept in the tab but deployed as empty
# per-slot pixel / vision switch (FEATURE t189): 🖼 = direct pixel ref (default),
# 👁 = the enhancer looks at the media and writes it into the prompt as text
VIS_ICON_PIXEL: Final = '🖼\ufe0f'
VIS_ICON_VISION: Final = '👁\ufe0f'  # emoji presentation (bare U+1F441 = text glyph)
VIS_USE: Final = 'vision'  # refdef.v1 ref ``use`` value (absent = pixel)
VIS_MEDIA: Final = ('image', 'video')  # audio has no pixels
VISION_LOCK_SLOT1: Final = ('inp-mask', 'inp-nomask', 'pickup')  # + swap / continue verbs
# load outputs + status: state, idx, raw, 3×slot, kind, verb, text, source, entry,
# view, vision, status
N_LOAD_OUT: Final = 3 + 3 * N_SLOTS + 8
# slot 1 carried refs: the refs a clip in slot 1 was rendered with (its payload)
CARRY_CELLS: Final = H3_REF_TOTAL  # max refs an H3 render can carry
CARRY_PER_ROW: Final = 4  # big cells: the carried refs get room (t185 v3)
CARRY_TAG_KEYS: Final = (('pic', 'image'), ('vid', 'video'), ('aud', 'audio'))


# ---------------------------------------------------------------------- #
# pure payload logic
# ---------------------------------------------------------------------- #
def disable_slots(refs_roles: list[str], slot_on: list[bool] | None) -> list[str]:
    """The flat ``[ref, role, ...]`` UI values with every disabled slot (✅ off)
    blanked: deploy / update / join / view switch treat it as empty, the tab keeps
    its content."""
    out = list(refs_roles)
    for i, on in enumerate(slot_on or []):
        if not on and 2 * i + 1 < len(out):
            out[2 * i] = out[2 * i + 1] = ''
    return out


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
    'ref': tuple(f'picture {i}' for i in range(1, N_SLOTS + 1)),  # see REF_LABEL
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
    order; since v6.8 each ref carries ``slot`` (1..N_SLOTS), older refs go by
    list position. A ref whose ``slot`` is out of range is skipped (never moved
    to another slot)."""
    out: list[dict | None] = [None] * N_SLOTS
    for i, r in enumerate(entry.get('refs') or []):
        if not isinstance(r, dict):
            continue
        n = r.get('slot')
        if n is None:
            k = i
        elif isinstance(n, int) and 1 <= n <= N_SLOTS:
            k = n - 1
        else:
            continue
        if k < N_SLOTS and out[k] is None:
            out[k] = r
    return out


def _view_media(payload: dict, view: str) -> list[dict | None]:
    """Live media objects ({url[, desc, w, h]}) of a view, slot order.
    ``main`` is the top-level url — returned as a detached dict."""
    if view == 'main':
        return [
            {
                'url': payload.get('url'),
                'desc': payload.get('url_desc'),
                'mask': payload.get(MASK_KEY_MAIN),
            }
        ]
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
    seen: dict[str, int] = {}  # ref view: fallback label numbered per kind
    for i, m in enumerate(_view_media(payload, view)[:N_SLOTS]):
        if m and m.get('url'):
            roles = VIEW_ROLES[view]
            if view == 'ref':
                kind = str(m.get('kind') or 'image')
                seen[kind] = seen.get(kind, 0) + 1
                label = f'{REF_LABEL.get(kind, kind)} {seen[kind]}'
            else:
                label = roles[i] if i < len(roles) else ''
            role = m.get('desc') or label
            slots[i] = {'url': m['url'], 'id': None, 'role': role}
            if isinstance(m.get('mask'), dict):
                slots[i]['mask'] = m['mask']
    # an inp-qfix payload pulls its edit instruction back into slot 1's role
    if view == 'inp' and payload.get('made_by') == QFIX_MADE_BY and slots[0]['url']:
        slots[0]['role'] = view_text(payload, view) or slots[0]['role']
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
                    **({'vision': True} if ref.get('use') == VIS_USE else {}),
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


def same_mask(a: dict | None, b: dict | None) -> bool:
    """Whether two mask objects describe the same mask: raster by file + media
    sha, json by content (post-ops on a payload mask are the enhancer's)."""
    if not isinstance(a, dict) or not isinstance(b, dict) or a.get('type') != b.get('type'):
        return False
    if a.get('type') == 'raster':
        return (a.get('url'), a.get('sha')) == (b.get('url'), b.get('sha'))
    return a == b


def _set_mask(obj: dict, mask: dict | bool | None) -> bool:
    """Put the tab's mask on a media object (False = masking off: drop its
    mask) → whether it changed."""
    if mask is False:
        return obj.pop('mask', None) is not None
    if not isinstance(mask, dict) or same_mask(obj.get('mask'), mask):
        return False
    obj['mask'] = mask
    return True


def _replace_media(obj: dict, url: str) -> None:
    obj['url'] = url
    obj.pop('frame', None)  # src-clip frame provenance no longer applies
    obj.pop('mask', None)  # a mask is bound to its media (task 175)
    if 'w' in obj or 'h' in obj:
        dims = _img_dims(url)
        if dims:
            obj['w'], obj['h'] = dims


def patch_iteration(
    payload: dict,
    view: str,
    urls: list[str | None],
    masks: list[dict | bool | None] | None = None,
) -> tuple[dict, list[str], list[str]]:
    """Copy of an iteration payload with only the image urls of ``view``
    patched (slot order as in ``view_slots``). Everything else is deployed
    verbatim.

    Replacing an image is always allowed (``w``/``h`` follow the new file).
    Structural changes are reported, not deployed, where the prompt names
    images by number: adding/removing an inp/ref ref, clearing an inp/next src
    or the next ref. Returns the patched payload, the changed field names
    and the skipped edits; ``edited_by`` is set only when something changed.

    ``masks`` = the tab's own (🎭) mask object per slot (None = none): it is
    set on the slot's media object unless that already carries the same mask
    (``same_mask``). A replaced url drops the old media's mask (task 175).
    False = masking switched off for the slot: its media's mask is dropped.
    """
    out = copy.deepcopy(payload)
    changed: list[str] = []
    skipped: list[str] = []
    urls = ([u or None for u in urls] + [None] * N_SLOTS)[:N_SLOTS]
    masks = (list(masks or []) + [None] * N_SLOTS)[:N_SLOTS]

    if view == 'main':
        if urls[0] != (out.get('url') or None):
            out['url'] = urls[0]
            out.pop(MASK_KEY_MAIN, None)
            changed.append('url')
        if masks[0] is False:
            if out.pop(MASK_KEY_MAIN, None) is not None:
                changed.append(MASK_KEY_MAIN)
        elif (
            urls[0]
            and isinstance(masks[0], dict)
            and not same_mask(out.get(MASK_KEY_MAIN), masks[0])
        ):
            out[MASK_KEY_MAIN] = masks[0]
            changed.append(MASK_KEY_MAIN)
        skipped += [f'slot {i + 1} (main has one image)' for i in range(1, N_SLOTS) if urls[i]]

    elif view == 'vid':
        refs = _vid_refs(out)
        for i, key in enumerate(VID_REF_KEYS):
            new = urls[i]
            ref = refs.get(key)
            old = ref.get('url') if isinstance(ref, dict) else None
            if new == (old or None):
                if isinstance(ref, dict) and _set_mask(ref, masks[i]):
                    changed.append(f'prompts_vid.refs.{key}.mask')
                continue
            if new is None:
                refs[key] = None
            elif isinstance(ref, dict):
                _replace_media(ref, new)
                _set_mask(ref, masks[i])
            else:
                refs[key] = {'url': new}
                _set_mask(refs[key], masks[i])
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
                if obj is not None and _set_mask(obj, masks[i]):
                    changed.append(f'{sec}.{names[i]}.mask')
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
                _set_mask(obj, masks[i])
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
    anchor clip (video). The other slots take any media — a clip there is the
    cut-to shot source (FEATURE t191); the H3 budget is ``ref_budget_problems``."""
    if verb not in CONTINUE_VERBS or not slots:
        return []
    if media_kind(slots[0].get('url')) != 'video':
        return ['slot 1 needs the anchor clip (video)']
    return []


def pin_of(slot: dict, verb: str) -> str | None:
    """t190 frame pin: ``'first'`` / ``'last'`` when an H3 verb's filled image
    slot's role starts with the keyword (the enhancer's ``PIN_RE``). A pinned ref
    is no ``<Picture N>`` and sits outside the H3 budget."""
    if verb not in H3_VERBS or media_kind(slot.get('url')) != 'image':
        return None
    m = PIN_RE.match(slot.get('role') or '')
    return m.group(1).lower() if m else None


def pin_problems(slots: list[dict], verb: str) -> list[str]:
    """t190 pin conflicts the enhancer refuses: a first-frame pin under post-vid
    (the anchor's tail already sits at frame 0), a last-frame pin under pre-vid."""
    bad = PIN_CONFLICT.get(verb)
    return [
        f'slot {i + 1} pins the {bad[0]} frame — {bad[1]}'
        for i, s in enumerate(slots[:N_SLOTS])
        if bad and pin_of(s, verb) == bad[0]
    ]


def _ref_key(url: str) -> str:
    """URL identity for the budget's de-dupe (t191 D): the normalised path."""
    return os.path.normpath(unquote(str(url)))


def ref_budget_problems(
    slots: list[dict], verb: str, inherit: list[dict] | None = None
) -> list[str]:
    """Why an H3 ref2va instruction breaks the ref budget (FEATURE t181): per kind
    ``H3_REF_CAP``, in total ``H3_REF_TOTAL`` with a clip's soundtrack counted iff
    its ref carries ``audio: true``. Outside the budget: 👁 vision slots (t189),
    t190 frame pins, and the pre-/post-vid anchor in slot 1 (pinned frames, not a
    ref). ``inherit`` (pre-/post-vid, t191): the anchor's carried refs, those with
    ``use: true`` count too; a file both carried and in a slot counts once."""
    if verb not in H3_VERBS:
        return []
    skip = 1 if verb in CONTINUE_VERBS else 0
    refs = [
        {'kind': media_kind(s['url']), 'url': s['url'], 'audio': s.get('audio') is True}
        for i, s in enumerate(slots)
        if i >= skip and s.get('url') and not is_vision(s, i, verb) and not pin_of(s, verb)
    ]
    if verb in CONTINUE_VERBS:
        seen = {_ref_key(r['url']) for r in refs}
        for r in inherit or []:
            if not r.get('use', True) or not r.get('url') or _ref_key(r['url']) in seen:
                continue
            seen.add(_ref_key(r['url']))
            refs.append({'kind': r.get('kind'), 'url': r['url'], 'audio': r.get('audio') is True})
    n = {k: 0 for k in H3_REF_CAP}
    for r in refs:
        if r['kind'] in n:
            n[r['kind']] += 1
    probs = [
        f'max {cap} {REF_LABEL[k]}s, got {n[k]}' for k, cap in H3_REF_CAP.items() if n[k] > cap
    ]
    tracks = sum(1 for r in refs if r['kind'] == 'video' and r['audio'])
    if (total := sum(n.values()) + tracks) > H3_REF_TOTAL:
        probs.append(f'max {H3_REF_TOTAL} refs in total (soundtracks counted), got {total}')
    return probs


def swap_problems(slots: list[dict], verb: str) -> list[str]:
    """Why a head-swap instruction can't deploy: slot 1 = target image, slot 2 =
    reference head image, slots 3+ empty (the workflow takes exactly 2 images)."""
    if verb not in SWAP_VERBS:
        return []
    slots = (list(slots) + empty_slots())[:N_SLOTS]
    probs = [
        f'slot {i + 1} needs the {what} (image)'
        for i, what in enumerate(('target', 'reference head'))
        if media_kind(slots[i].get('url')) != 'image'
    ]
    if extra := [str(i + 1) for i, s in enumerate(slots[2:], 2) if s.get('url')]:
        probs.append(f'slot {", ".join(extra)} must be empty (2 images only)')
    return probs


def img_ref_problems(slots: list[dict], verb: str) -> list[str]:
    """Why a ref-img instruction can't deploy: 1-5 still images in slots 1-5,
    slots 6+ empty."""
    if verb not in IMG_REF_VERBS:
        return []
    slots = (list(slots) + empty_slots())[:N_SLOTS]
    head = slots[:IMG_REF_MAX]
    probs = [
        f'slot {i + 1} is {kind} (images only)'
        for i, s in enumerate(head)
        if (kind := media_kind(s.get('url'))) not in (None, 'image')
    ]
    if not any(s.get('url') for s in head):
        probs.append(f'needs 1-{IMG_REF_MAX} images in slots 1-{IMG_REF_MAX}')
    elif all(is_vision(s, i, verb) for i, s in enumerate(head) if s.get('url')):
        probs.append('needs at least one 🖼 pixel image (all filled slots are 👁)')
    if extra := [
        str(i + 1) for i, s in enumerate(slots[IMG_REF_MAX:], IMG_REF_MAX) if s.get('url')
    ]:
        probs.append(f'slot {", ".join(extra)} must be empty (max {IMG_REF_MAX} images)')
    return probs


def vision_locked(i: int, verb: str) -> bool:
    """Slot ``i`` (0-based) is one the verb needs as pixels (t189 D2): the swap's
    target + new face, the pre-/post-vid anchor, the inpaint edit image, the
    pickup render (the last two per xlasmos' contract reply)."""
    if verb in SWAP_VERBS:
        return i < 2
    return i == 0 and verb in (*CONTINUE_VERBS, *VISION_LOCK_SLOT1)


def is_vision(slot: dict, i: int, verb: str) -> bool:
    """Slot ``i`` deploys as ``use: vision``: 👁 set, image / video media, not
    locked, and a verb the enhancer handles (inp-qfix is scripted)."""
    return bool(
        slot.get('vision')
        and media_kind(slot.get('url')) in VIS_MEDIA
        and not vision_locked(i, verb)
        and verb not in QFIX_VERBS
    )


def vision_slots(slots: list[dict], verb: str) -> list[int]:
    """1-based slots deployed as ``use: vision``."""
    return [i + 1 for i, s in enumerate(slots[:N_SLOTS]) if is_vision(s, i, verb)]


def vision_ignored(slots: list[dict], verb: str) -> list[int]:
    """1-based filled slots with 👁 set that deploy as pixel refs anyway
    (locked slot, audio, inp-qfix)."""
    return [
        i + 1
        for i, s in enumerate(slots[:N_SLOTS])
        if s.get('vision') and s.get('url') and not is_vision(s, i, verb)
    ]


def ignored_masks(slots: list[dict], verb: str) -> list[int]:
    """1-based slots whose 🎭 mask the deploy ignores: ref-img emits no masks, a
    👁 vision slot ships no pixels (t189 D3)."""
    return [
        i + 1
        for i, s in enumerate(slots[:N_SLOTS])
        if s.get('url') and s.get('mask') and (verb in IMG_REF_VERBS or is_vision(s, i, verb))
    ]


def qfix_problems(slots: list[dict], verb: str) -> list[str]:
    """Why an inp-qfix deploy can't happen: slot 1 = the edit target (image),
    the other filled slots 0-2 still refs, slot 1's role = the edit instruction."""
    if verb not in QFIX_VERBS:
        return []
    probs = []
    if not slots or media_kind(slots[0].get('url')) != 'image':
        probs.append('slot 1 needs the edit target (image)')
    refs = [(i + 1, s) for i, s in enumerate(slots[1:], 1) if s.get('url')]
    probs += [f'slot {n} must be a still image' for n, s in refs if media_kind(s['url']) != 'image']
    if len(refs) > QFIX_MAX_REFS:
        probs.append(f'max {QFIX_MAX_REFS} refs (image 2 / image 3), got {len(refs)}')
    if slots and not (slots[0].get('role') or '').strip():
        probs.append('slot 1 role (the qwen21 edit instruction) is empty')
    return probs


def _qfix_media(slot: dict, desc: str) -> dict:
    """{url, w, h, desc[, mask]} media object of a qfix slot."""
    url = str(slot['url'])
    obj: dict[str, Any] = {'url': url}
    if dims := _img_dims(url):
        obj['w'], obj['h'] = dims
    obj['desc'] = (slot.get('role') or '').strip() or desc
    if isinstance(slot.get('mask'), dict) and not slot.get('mask_off'):
        obj['mask'] = slot['mask']
    return obj


def qfix_payload(slots: list[dict], text: str = '', origin_scene_id: str | None = None) -> dict:
    """The enhancer data an ``inp-qfix`` deploy writes — built here, no enhancer
    (board FEATURE 180): a ``prompts_inp`` entry exactly as the enhancer's
    ``/inpaint`` commits it (engine qwen21, ``src.mask`` = the slot 1 🎭 mask →
    mode mask, else nomask; refs = the filled slots 2.. in order; ``prompt_qwen21``
    = slot 1's role verbatim, the tab text only rides as ``hints``) on a payload
    whose top-level url is the edit target. ``rev`` = ``from_rev`` = 0, so a
    pull opens it on the ``inp`` view; ``edited_by`` keeps the enhancer away.
    Call ``qfix_problems`` first."""
    src = _qfix_media(dict(slots[0], role=''), 'edit target')  # its role = the prompt
    refs = [
        _qfix_media(s, f'image {n + 2}') for n, s in enumerate(s for s in slots[1:] if s.get('url'))
    ]
    entry: dict[str, Any] = {
        'prompt_qwen21': (slots[0].get('role') or '').strip(),
        'engine': 'qwen21',
        'concepts': [],
        'src': src,
        'mask': None,  # legacy mirror; null for a raster src.mask
        'mode': 'mask' if src.get('mask') else 'nomask',
        **({'refs': refs} if refs else {}),
        'hints': (text or '').strip() or None,
        'from_rev': 0,
        'ts': SceneDef.now_ts(),
    }
    payload: dict[str, Any] = {
        'schema_id': SCHEMA_ITERATION_OUT,
        'scene_id': origin_scene_id,
        'url': src['url'],
        'url_desc': src['desc'],
        'prompts': {'type': 'single', 'current': 0, 'prompt_data': []},
        'rev': 0,
        'prompts_inp': {'type': 'single', 'current': 0, 'prompt_data': [entry]},
        'edited_by': EDITED_BY,
        'made_by': QFIX_MADE_BY,
    }
    if src.get('mask'):
        payload[MASK_KEY_MAIN] = src['mask']
    return payload


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


def mask_paths(url: str) -> tuple[Path, Path]:
    """(mask, masked) file paths of a source image (exist or not)."""
    src = Path(url).expanduser().resolve()
    key = hashlib.sha1(str(src).encode()).hexdigest()[:10]
    base = f'{src.stem}__{key}'
    return MASK_DIR / f'{base}__mask.png', MASK_DIR / f'{base}__masked.png'


def mask_of(url: str | None) -> tuple[str, str] | None:
    """(mask, masked) paths of a local image's painted mask, None when none."""
    if not url or url.startswith(('http://', 'https://')) or media_kind(url) != 'image':
        return None
    mask, masked = mask_paths(url)
    return (str(mask), str(masked)) if mask.is_file() and masked.is_file() else None


def file_sha(url: str) -> str:
    """sha1 of a file's bytes, first 12 hex (mask.v1 ``sha`` binding)."""
    h = hashlib.sha1()
    with open(url, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:12]


def mask_object(url: str | None) -> dict | None:
    """The tab's painted mask of a local image as a ``1xlasm_enhancer.mask.v1``
    raster object ({schema_id, type, url, w, h, sha}), None when it has none."""
    hit = mask_of(url)
    if hit is None or url is None:
        return None
    with Image.open(hit[0]) as m:
        w, h = m.size  # = the EXIF-upright media size
    return {
        'schema_id': SCHEMA_MASK,
        'type': 'raster',
        'url': hit[0],
        'w': w,
        'h': h,
        'sha': file_sha(url),
    }


def slot_mask(slot: dict) -> dict | bool | None:
    """``patch_iteration`` mask of a ``{url, mask_off}`` slot: False when its
    masking is switched off, else the painted mask object (None = none)."""
    return False if slot.get('mask_off') else mask_object(slot.get('url'))


def rasterize_mask(mask: dict | None, size: tuple[int, int]) -> Image.Image | None:
    """L preview (255 = masked) of a mask.v1 object at ``size`` — spatial part
    only (``ranges`` / dilate / feather are ignored, ``invert`` applies). None
    for no / unknown / unreadable / time-only masks."""
    if not isinstance(mask, dict) or not str(mask.get('schema_id', SCHEMA_MASK)).startswith(
        SCHEMA_MASK_PREFIX
    ):
        return None
    w, h = size
    if mask.get('type') == 'raster':
        try:
            with Image.open(mask['url']) as m:
                out = m.convert('L').resize(size, Image.Resampling.NEAREST)
        except Exception:  # noqa: BLE001 - unreadable raster -> no tint
            return None
    elif mask.get('type') == 'json' and mask.get('shapes'):
        out = Image.new('L', size, 0)
        draw = ImageDraw.Draw(out)
        for sh in mask['shapes']:
            if not isinstance(sh, dict):
                continue
            fill = 0 if sh.get('op') == 'sub' else 255
            c = sh.get('coords') or []
            try:
                if sh.get('kind') == 'rect':
                    x, y, rw, rh = c
                    draw.rectangle([x * w, y * h, (x + rw) * w, (y + rh) * h], fill=fill)
                elif sh.get('kind') == 'ellipse':
                    cx, cy, rx, ry = c
                    box = [(cx - rx) * w, (cy - ry) * h, (cx + rx) * w, (cy + ry) * h]
                    draw.ellipse(box, fill=fill)
                elif sh.get('kind') == 'circle':
                    cx, cy, r = c
                    rp = r * min(w, h)
                    draw.ellipse([cx * w - rp, cy * h - rp, cx * w + rp, cy * h + rp], fill=fill)
                elif sh.get('kind') == 'polygon' and len(c) >= 3:
                    draw.polygon([(x * w, y * h) for x, y in c], fill=fill)
            except (TypeError, ValueError):
                continue
    else:
        return None
    return ImageOps.invert(out) if mask.get('invert') else out


def drop_mask(url: str) -> bool:
    """Delete a source image's mask files → whether there were any."""
    hit = False
    for f in mask_paths(url):
        if f.is_file():
            f.unlink()
            hit = True
    return hit


def write_mask(url: str, painted: Image.Image) -> tuple[str, str] | None:
    """Store ``painted`` (L / any mode; > 0 = masked, any size) as the mask of
    the source image ``url``: scaled to the (EXIF-upright) image size, then the
    L mask + the RGBA ``masked`` image (alpha 0 where masked; the source's PNG
    text chunks kept, so ComfyUI metadata survives). An empty mask deletes the
    mask files → None."""
    with Image.open(url) as src:
        info = {k: v for k, v in src.info.items() if isinstance(k, str) and isinstance(v, str)}
        im = ImageOps.exif_transpose(src).convert('RGB')
    m = painted.convert('L').point(lambda v: 255 if v > 0 else 0)
    if m.size != im.size:
        m = m.resize(im.size, Image.Resampling.BILINEAR).point(lambda v: 255 if v > 127 else 0)
    if m.getbbox() is None:
        drop_mask(url)
        return None
    mask_p, masked_p = mask_paths(url)
    MASK_DIR.mkdir(parents=True, exist_ok=True)
    m.save(mask_p)
    rgba = im.convert('RGBA')
    rgba.putalpha(m.point(lambda v: 255 - v))
    png = PngImagePlugin.PngInfo()
    for k, v in info.items():
        png.add_text(k, v)
    rgba.save(masked_p, pnginfo=png)
    return str(mask_p), str(masked_p)


def tint_mask(im: Image.Image, url: str | None, mask: dict | None = None) -> Image.Image:
    """Slot preview with its mask tinted in: the tab's painted mask of ``url``
    (newest, deployed next), else the payload's mask object ``mask``."""
    m = rasterize_mask(mask_object(url) if mask_of(url) else mask, im.size)
    if m is None:
        return im
    over = Image.new('RGB', im.size, MASK_TINT)
    return Image.composite(over, im, m.point(lambda v: v * 45 // 100))


def _instruction_role(slot: dict, i: int, verb: str) -> str:
    """A slot's role as deployed: stripped; an empty swap-verb role (slot 1 / 2)
    falls back to ``SWAP_DEFAULT_ROLES``."""
    role = (slot.get('role') or '').strip()
    if not role and verb in SWAP_VERBS and i < len(SWAP_DEFAULT_ROLES) and slot.get('url'):
        return SWAP_DEFAULT_ROLES[i]
    return role


def carry_tag(ref: dict) -> str:
    """Short H3 tag of a carried ref: ``pic 2`` / ``vid 1`` / ``aud 1`` (else its kind)."""
    for key, kind in CARRY_TAG_KEYS:
        if isinstance(ref.get(key), int):
            return f'{key} {ref[key]}'
        if ref.get('kind') == kind:
            return key
    return str(ref.get('kind') or '?')


def carry_of(url: str | None) -> dict:
    """Slot 1's carried refs: ``{anchor, refs, on, error}`` — ``anchor`` = the clip
    whose payload the refs come from (the slot clip, or its FbbcoolSaveVideo master
    via ``anchor_master``), ``refs`` = its rendered prompts_ref entry's refs,
    ``on`` = per-ref use switch (all on)."""
    out: dict[str, Any] = {'anchor': None, 'refs': [], 'on': [], 'error': None}
    if not url or media_kind(url) != 'video':
        return out
    try:
        master = anchor_master(url)
    except ValueError as e:
        out['error'] = str(e)
        return out
    if master is None:
        return out
    refs = clip_refs(master)
    out.update(anchor=str(master), refs=refs, on=[True] * len(refs))
    return out


def inherit_list(carry: dict | None, anchor: str | None) -> list[dict] | None:
    """The refdef.v1 ``inherit`` list: every ref the anchor carries, in payload
    order, with ``use`` = its ✅/🚫 switch. None when ``carry`` belongs to another
    clip than the deployed anchor (stale) or carries nothing."""
    if not carry or not carry.get('refs') or carry.get('anchor') != anchor:
        return None
    on = list(carry.get('on') or [])
    return [
        {
            'n': i + 1,
            'tag': carry_tag(r),
            'kind': r.get('kind'),
            'url': r.get('url'),
            'desc': r.get('desc') or '',
            'use': on[i] if i < len(on) else True,
            # a carried clip's soundtrack counts in the H3 budget (t181)
            **({'audio': True} if r.get('audio') is True else {}),
        }
        for i, r in enumerate(carry['refs'])
    ]


def refdef_payload(
    slots: list[dict],
    verb: str,
    prompt_kind: str,
    text: str,
    origin_scene_id: str | None = None,
    inherit: list[dict] | None = None,
) -> dict:
    """The instruction payload the enhancer builds its enhancer data from. A
    slot's ``mask`` (a mask.v1 object, see ``mask_object``) becomes the ref's
    ``mask``. ``inherit`` (pre-/post-vid only): the anchor's carried refs with
    their ``use`` switch — the enhancer inherits only ``use: true`` ones."""
    payload: dict[str, Any] = {
        'schema_id': SCHEMA_REFDEF,
        'verb': verb if verb in VERBS else VERBS[0],
        'refs': [
            {
                'slot': i + 1,
                'url': s.get('url') or None,
                'id': s.get('id') or None,
                'role': _instruction_role(s, i, verb),
                'media': media_kind(s.get('url')),
                # 🎭 painted mask (only when one exists): mask.v1 object (task 175)
                **(
                    {'mask': s['mask']}
                    if s.get('mask') and verb not in IMG_REF_VERBS and not is_vision(s, i, verb)
                    else {}
                ),
                # 👁 (t189): the enhancer describes the media into the prompt, no pixels
                **({'use': VIS_USE} if is_vision(s, i, verb) else {}),
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
        if inherit:
            payload['inherit'] = inherit
    return payload


def update_payload(
    text: str | None,
    slots: list[dict],
    view: str | None = None,
    verb: str | None = None,
) -> tuple[dict, str, list[str], list[str]] | None:
    """Clipspace text with its reference urls replaced by the filled
    ``slots`` (``{url, id}``; empty slot = keep the clipspace's ref;
    ``mask_off`` = masking switched off: the ref's mask is dropped).

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
            off = bool(s.get('mask_off'))
            mask = None if off else mask_object(s.get('url'))
            ref = by_slot.get(i + 1)
            if ref is None:
                ref = {'slot': i + 1, **new, 'role': '', 'media': new_media}
                refs.append(ref)
            elif (ref.get('url'), ref.get('id') or None) != (new['url'], new['id']):
                ref.update(new, media=new_media)
                ref.pop('mask', None)  # bound to the old media
            elif off:
                if ref.pop('mask', None) is None:
                    continue
            elif not mask or same_mask(ref.get('mask'), mask):
                continue
            ref.pop('masked', None)  # pre-v1 provisional field
            if mask:
                ref['mask'] = mask
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
        masks = [slot_mask(s) for s in slots]
        out, changed, skipped = patch_iteration(p, v, urls, masks)
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


def parse_models(models: str | list | None) -> list[str]:
    """'a, b' / ['a', 'b'] → ['a', 'b']; empty → ['generic']."""
    if isinstance(models, str):
        models = models.split(',')
    out = [m.strip() for m in models or [] if m and m.strip()]
    return list(dict.fromkeys(out)) or list(PROMPT_MODELS_DEFAULT)


def prompt_label(doc: dict) -> str:
    """Dropdown label ``category / name [models]``."""
    models = ', '.join(parse_models(doc.get('models')))
    return f'{doc.get("category") or "-"} / {doc["name"]} [{models}]'


def list_prompts(col) -> list[dict]:
    """Every predefined prompt, by category then name ([] without a DB)."""
    if col is None:
        return []
    docs = list(col.find({}, {'_id': 0}))
    return sorted(docs, key=lambda d: ((d.get('category') or '').lower(), d['name'].lower()))


def save_prompt(col, name: str, category: str | None, models, prompt: str) -> dict:
    """Upsert the prompt ``name`` (an existing name is overwritten)."""
    name, prompt = (name or '').strip(), (prompt or '').strip()
    if not name:
        raise ValueError('needs a name')
    if not prompt:
        raise ValueError('prompt text is empty')
    doc = {
        'name': name,
        'category': (category or '').strip() or None,
        'models': parse_models(models),
        'prompt': prompt,
        'ts': datetime.now(timezone.utc).replace(tzinfo=None),
    }
    col.replace_one({'name': name}, doc, upsert=True)
    return doc


def delete_prompt(col, name: str) -> bool:
    return bool(name) and col.delete_one({'name': name}).deleted_count > 0


def seed_prompts(col) -> int:
    """Insert the PROMPT_SEED entries whose name is missing; returns how many."""
    if col is None:
        return 0
    n = 0
    for doc in PROMPT_SEED:
        if col.find_one({'name': doc['name']}) is None:
            save_prompt(col, doc['name'], doc['category'], doc['models'], doc['prompt'])
            n += 1
    return n


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
    def _preview(
        url: str | None, mask: dict | None = None, mask_on: bool = True
    ) -> Image.Image | str | None:
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
            return tint_mask(im, url, mask) if mask_on else im
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
        view, vision."""
        enh = self._is_enh(st)
        slots = st['slots'] if st else empty_slots()
        slot_vals: list[Any] = []
        for s in slots:
            ref = s.get('id') or s.get('url') or ''
            role = gr.update(value=s.get('role') or '', interactive=not enh)
            slot_vals += [self._preview(s.get('url'), s.get('mask')), ref, role]
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
            [bool(s.get('vision')) for s in slots],
        ]

    def _commit(
        self, state: dict, refs: list[str], mask_on: list[bool] | None = None
    ) -> tuple[dict, list[str], list[str]]:
        """Patch the current view's slot images into the working payload
        (``state['payload']``), so every view's replacements reach deploy."""
        urls = [self.resolve_ref(r)[0] for r in refs]
        on = mask_on or [True] * N_SLOTS
        masks = [slot_mask({'url': u, 'mask_off': not on[i]}) for i, u in enumerate(urls)]
        work, changed, skipped = patch_iteration(state['payload'], state['view'], urls, masks)
        before = state.get('changed', [])
        merged = before + [c for c in changed if c not in before]
        return dict(state, payload=work, changed=merged), changed, skipped

    def _on_view(self, state: dict | None, view: str | None, mask_on: list[bool], *refs: str):
        """Switch the enhancer-data view; the old view's slot replacements
        are committed to the working payload first."""
        if not self._is_enh(state) or not view or view == state['view']:  # type: ignore[index]
            return [gr.update()] * (N_LOAD_OUT)
        st, changed, skipped = self._commit(state, list(refs), mask_on)  # type: ignore[arg-type]
        note = f' · kept: {", ".join(changed)}' if changed else ''
        note += f' · NOT kept: {", ".join(skipped)}' if skipped else ''
        return [*self._load(with_view(st, view)), f'view `{view}`{note}']

    def _on_pull(self, state: dict | None, *refs: str):
        n_out = N_LOAD_OUT
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
        return [*[gr.update()] * 3, *upd, *[gr.update()] * 7, status + dropped]

    def _on_reset(self):
        return [*self._load(None), 'reset']

    # -- save history ------------------------------------------------- #
    @staticmethod
    def _snap(state, idx, verb, kind, text, vision, *refs_roles) -> dict:
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
            'vision': [bool(v) for v in (vision or [False] * N_SLOTS)],  # t189 D4
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
            [bool(v) for v in (list(snap.get('vision') or []) + [False] * N_SLOTS)[:N_SLOTS]],
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

    def _pcol(self):
        return self._dbc._get_collection(PROMPTS_COLLECTION)

    def _prompt_choices(self) -> list[tuple[str, str]]:
        return [(prompt_label(d), d['name']) for d in list_prompts(self._pcol())]

    def _on_prompt_pick(self, name):
        """Dropdown pick → the text box (replaced) + the ➕ fields (edit = ➕ again)."""
        col = self._pcol()
        doc = col.find_one({'name': name}) if col is not None and name else None
        if doc is None:
            return gr.update(), gr.update(), gr.update(), gr.update()
        return (
            doc['prompt'],
            doc['name'],
            doc.get('category') or '',
            ', '.join(parse_models(doc.get('models'))),
        )

    def _on_prompt_add(self, name, category, models, text):
        col = self._pcol()
        if col is None:
            gr.Warning('prompt: no DB connection', duration=0.5)
            return gr.update()
        try:
            doc = save_prompt(col, name, category, models, text)
        except ValueError as e:
            gr.Warning(f'prompt: {e}', duration=1)
            return gr.update()
        gr.Info(f'prompt `{doc["name"]}` saved', duration=0.5)
        return gr.update(choices=self._prompt_choices(), value=doc['name'])

    def _on_prompt_del(self, name):
        col = self._pcol()
        if col is None or not name:
            gr.Info('no prompt selected', duration=0.5)
            return gr.update()
        if delete_prompt(col, name):
            gr.Info(f'prompt `{name}` deleted', duration=0.5)
        return gr.update(choices=self._prompt_choices(), value=None)

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

    def _on_save(self, cat, state, idx, verb, kind, text, vision, *refs_roles):
        """Save the shown config under category ``cat`` (a new typed-in one
        joins the dropdown)."""
        cur = {'pos': None, 'draft': None}
        col = self._col()
        if col is None:
            gr.Warning('save: no DB connection', duration=0.5)
            return 'save: no DB connection', cur, gr.update(), gr.update()
        doc = snap_to_doc(self._snap(state, idx, verb, kind, text, vision, *refs_roles))
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
        n_out = N_LOAD_OUT
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
        n_out = N_LOAD_OUT
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
        self,
        hist: dict | None,
        step: int,
        cat,
        state,
        idx,
        verb,
        kind,
        text,
        vision,
        *refs_roles,
    ):
        """◀ / ▶ through the saves of category ``cat``; leaving the current
        config drafts it so ▶ past the newest save restores it (even when it
        was never saved)."""
        n_out = N_LOAD_OUT
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
            draft = self._snap(state, idx, verb, kind, text, vision, *refs_roles)
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

    def _slots_from_ui(
        self,
        refs_roles: list[str],
        mask_on: list[bool] | None = None,
        vision: list[bool] | None = None,
    ) -> list[dict]:
        on = mask_on or [True] * N_SLOTS
        vis = vision or [False] * N_SLOTS
        slots = []
        for i in range(N_SLOTS):
            url, id_img = self.resolve_ref(refs_roles[2 * i])
            slot: dict[str, Any] = {'url': url, 'id': id_img, 'role': refs_roles[2 * i + 1]}
            if vis[i]:
                slot['vision'] = True
            if not on[i]:
                slot['mask_off'] = True
            elif hit := mask_object(url):
                slot['mask'] = hit
            slots.append(slot)
        return slots

    def _on_deploy(
        self,
        state: dict | None,
        verb: str,
        kind: str,
        auto: bool,
        text: str,
        mask_on: list[bool],
        vision: list[bool],
        carry: dict | None,
        *refs_roles,
    ):
        slots = self._slots_from_ui(list(refs_roles), mask_on, vision)
        if self._is_enh(state):
            refs = [refs_roles[2 * i] for i in range(N_SLOTS)]
            st, _, skipped = self._commit(state, refs, mask_on)  # type: ignore[arg-type]
            # the full payload (all sections) goes back; never triggers the enhancer
            clip_copy(json.dumps(st['payload'], ensure_ascii=False))
            note = f' · NOT deployed: {", ".join(skipped)}' if skipped else ''
            if vis := [i + 1 for i, s in enumerate(slots) if s.get('vision') and s['url']]:
                note += f' · vision ignored: slot {", ".join(map(str, vis))} (no enhancer)'
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

        def refused(probs: list[str]) -> str:
            # qfix: 2 s app toast (FEATURE 180); the other verbs keep 1 s
            gr.Warning(
                f'{verb}: {"; ".join(probs)}',
                duration=QFIX_TOAST_WARN_S
                if verb in QFIX_VERBS + SWAP_VERBS + H3_VERBS + IMG_REF_VERBS
                else 1,
            )
            return f'NOT deployed: `{verb}` — {"; ".join(probs)}'

        if probs := continue_problems(slots, verb):
            return refused(probs)
        anchor_note = ''
        inherit = None
        master = None
        # the enhancer inherits the anchor's refs from its payload; built ahead of the
        # budget check, which counts the carried refs too (t191)
        if verb in CONTINUE_VERBS:
            url = slots[0]['url']
            try:
                master = anchor_master(url)
            except ValueError as e:
                return refused([str(e)])
            if master is None:
                return refused(
                    [
                        f'slot 1 {Path(url).name} has no enhancer payload (merge / re-encode?) '
                        'and no fbbcool_temp master found — use the FbbcoolSaveVideo master'
                    ]
                )
            if str(master) != url:
                slots[0] = {**slots[0], 'url': str(master), 'id': None}
                anchor_note = f' · anchor → {master.name}'
            if inherit := inherit_list(carry, str(master)):
                off = [r['tag'] for r in inherit if not r['use']]
                anchor_note += f' · inherit {len(inherit) - len(off)}/{len(inherit)}'
                anchor_note += f' (off: {", ".join(off)})' if off else ''
        if probs := (
            pin_problems(slots, verb)
            or ref_budget_problems(slots, verb, inherit)
            or swap_problems(slots, verb)
            or img_ref_problems(slots, verb)
            or qfix_problems(slots, verb)
        ):
            return refused(probs)
        if verb in QFIX_VERBS:  # scripted enhancer data, no enhancer (FEATURE 180)
            res = self._deploy_qfix(slots, text, origin)
            if vis_off := vision_ignored(slots, verb):  # scripted: nobody looks (t189)
                res += f' · vision ignored: slot {", ".join(map(str, vis_off))}'
            return res
        if master is not None and anchor_note.startswith(' · anchor →'):
            gr.Info(f'{verb}: anchor → {master.name}', duration=QFIX_TOAST_WARN_S)
        payload = refdef_payload(slots, verb, kind, text, origin, inherit)
        clip_copy(json.dumps(payload, ensure_ascii=False))
        n = sum(1 for s in slots if s['url'])
        msg = f'deployed instruction `{verb}` ({n}/{N_SLOTS} slots, kind={kind}){anchor_note}'
        if vis := vision_slots(slots, verb):
            msg += f' · 👁 vision: slot {", ".join(map(str, vis))}'
        if vis_off := vision_ignored(slots, verb):
            msg += f' · vision ignored: slot {", ".join(map(str, vis_off))}'
        if masked := ignored_masks(slots, verb):
            msg += f' · masks ignored: slot {", ".join(map(str, masked))}'
        note = trigger_enhancer() if auto else 'auto-trigger off'
        if verb in SWAP_VERBS:  # deploy toast like inp-qfix
            dflt = [r['slot'] for r in payload['refs'][:2] if r['role'] in SWAP_DEFAULT_ROLES]
            roles = f'default roles: slot {", ".join(map(str, dflt))}' if dflt else 'own roles'
            gr.Success(f'{verb} deployed: {roles} · {note}', duration=QFIX_TOAST_OK_S)
        print(f'[refdef_tab:info] deploy {verb}: {note}')
        return f'{msg} · {note}'

    @staticmethod
    def _deploy_qfix(slots: list[dict], text: str, origin: str | None) -> str:
        """inp-qfix deploy: script the enhancer data onto the clipspace and read it
        back; success toast 0.5 s, any failure an error toast 2 s (FEATURE 180)."""
        try:
            qp = qfix_payload(slots, text, origin)
            out = json.dumps(qp, ensure_ascii=False)
            clip_copy(out)
            if pyperclip.paste() != out:
                raise RuntimeError('clipspace write failed (read-back differs)')
        except Exception as exc:  # noqa: BLE001 - every failure → toast + status
            gr.Error(f'inp-qfix: {exc}', duration=QFIX_TOAST_WARN_S)
            print(f'[refdef_tab:error] deploy inp-qfix: {exc}')
            return f'NOT deployed: `inp-qfix` — {exc}'
        e = qp['prompts_inp']['prompt_data'][0]
        msg = f'inp-qfix deployed: {e["mode"]}, {len(e.get("refs") or [])} refs'
        gr.Success(msg, duration=QFIX_TOAST_OK_S)
        print(f'[refdef_tab:info] deploy {msg}')
        return f'{msg} · no enhancer trigger'

    def _on_carry(self, url: str | None, *others: str | None):
        """Slot 1 changed → its carried refs panel: header, one cell per ref
        (preview labelled ``tag · desc``, ``≡ slot N`` when a slot already holds the
        same media), all switched on; hidden when the clip carries no refs."""
        url = self.resolve_ref(url)[0] if url else None
        c = carry_of(url)
        cells = [gr.update(visible=False, value=None)] * CARRY_CELLS
        btns = [gr.update(visible=False, value=SLOT_ICON_ON)] * CARRY_CELLS
        if c['error']:
            return c, gr.update(visible=True), f'⚠ {c["error"]}', *cells, *btns
        if not c['refs']:
            return c, gr.update(visible=False), '', *cells, *btns
        slot_urls = {self.resolve_ref(o)[0]: n for n, o in enumerate(others, 2) if o}
        for j, r in enumerate(c['refs'][:CARRY_CELLS]):
            dup = slot_urls.get(r.get('url'))
            label = carry_tag(r) + (f' ≡ slot {dup}' if dup else '')
            desc = (r.get('desc') or '').strip()
            label += f' · {desc[:90]}' if desc else ''
            cells[j] = gr.update(
                visible=True, value=self._preview(r.get('url')), label=label, elem_classes=[]
            )
            btns[j] = gr.update(visible=True, value=SLOT_ICON_ON)
        anchor = Path(c['anchor']).name
        head = f'⤷ `{anchor}`' if url and Path(url).name != anchor else ''
        more = (
            f' · {len(c["refs"]) - CARRY_CELLS} more not shown'
            if len(c['refs']) > CARRY_CELLS
            else ''
        )
        return c, gr.update(visible=True), head + more, *cells, *btns

    @staticmethod
    def _on_carry_toggle(carry: dict | None, j: int):
        """✅/🚫 of carried ref ``j``: flip its use switch, dim its preview."""
        c = copy.deepcopy(carry) if carry else carry_of(None)
        if j >= len(c['on']):
            return c, gr.update(), gr.update()
        c['on'][j] = not c['on'][j]
        on = c['on'][j]
        return (
            c,
            gr.update(value=SLOT_ICON_ON if on else SLOT_ICON_OFF),
            gr.update(elem_classes=[] if on else ['refdef-slot-off']),
        )

    def _on_update(self, state: dict | None, verb: str | None, mask_on: list[bool], *refs_roles):
        """Rewrite the CURRENT clipspace's reference urls from the slots —
        script only, never triggers the enhancer."""
        slots = self._slots_from_ui(list(refs_roles), mask_on)
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
    # -- 🎭 hand-drawn masks ------------------------------------------- #
    def _mask_src(self, ref: str | None) -> str | None:
        """Local image file behind a slot ref, None when it can't be masked."""
        url = self.resolve_ref(ref)[0] if ref else None
        if not url or media_kind(url) != 'image' or not Path(url).is_file():
            return None
        return url

    def _on_mask_open(self, i: int, ref: str | None):
        """Open the editor on slot ``i``'s image (existing mask as the layer)."""
        url = self._mask_src(ref)
        if url is None:  # empty / clip / audio / remote slot: the click does nothing
            return gr.update(), gr.update(), gr.update(), gr.update()
        with Image.open(url) as src:
            src.draft('RGB', (MASK_EDIT_SIZE, MASK_EDIT_SIZE))
            bg = ImageOps.exif_transpose(src).convert('RGB')
        bg.thumbnail((MASK_EDIT_SIZE, MASK_EDIT_SIZE))
        layer = Image.new('RGBA', bg.size, (0, 0, 0, 0))
        if hit := mask_of(url):
            with Image.open(hit[0]) as src_m:
                m = src_m.convert('L').resize(bg.size, Image.Resampling.NEAREST)
            layer.paste((*MASK_TINT, 128), mask=m)
        value = {'background': bg, 'layers': [layer], 'composite': None}
        return mask_overlay(True), value, i, f'🎭 slot {i + 1} · `{Path(url).name}`'

    @staticmethod
    def _painted(value: dict | None) -> Image.Image | None:
        """Editor value → L mask (> 0 = painted), None when there is no canvas."""
        if not value or value.get('background') is None:
            return None
        layers = [la for la in value.get('layers') or [] if la is not None]
        if not layers:
            return Image.new('L', value['background'].size, 0)
        m = Image.new('L', layers[0].size, 0)
        for la in layers:
            a = la.convert('RGBA').getchannel('A').point(lambda v: 255 if v > 0 else 0)
            m = ImageChops.lighter(m, a.resize(m.size, Image.Resampling.NEAREST))
        return m

    def _on_mask_apply(self, i: int | None, value: dict | None, copy_masked: bool, *refs):
        """Store the painted mask for slot ``i``'s image (empty = delete it);
        ``copy_masked`` also puts the RGBA masked image's path on the clipspace."""
        keep = [gr.update()] * N_SLOTS
        url = self._mask_src(refs[i]) if i is not None else None
        m = self._painted(value)
        if i is None or url is None or m is None:
            gr.Warning('mask: no slot image in the editor', duration=0.5)
            return [*keep, gr.update(), 'mask: no slot image in the editor']
        hit = write_mask(url, m)
        imgs: list[Any] = list(keep)
        imgs[i] = self._preview(url)
        if hit is None:
            return [*imgs, mask_overlay(False), f'slot {i + 1}: empty mask · mask removed']
        msg = f'slot {i + 1}: mask saved → `{hit[1]}`'
        if copy_masked:
            clip_copy(hit[1])
            msg += ' · clipspace ← masked image'
        gr.Success(f'slot {i + 1}: mask saved', duration=0.5)
        return [*imgs, mask_overlay(False), msg]

    def _on_mask_drop(self, i: int | None, *refs):
        keep = [gr.update()] * N_SLOTS
        url = self._mask_src(refs[i]) if i is not None else None
        if i is None or url is None or not drop_mask(url):
            return [*keep, mask_overlay(False), 'mask: nothing to remove']
        imgs: list[Any] = list(keep)
        imgs[i] = self._preview(url)
        return [*imgs, mask_overlay(False), f'slot {i + 1}: mask removed']

    @staticmethod
    def _payload_mask(state: dict | None, i: int, url: str | None) -> dict | None:
        """The pulled payload's mask of slot ``i`` while it still shows that media."""
        s = (state or {}).get('slots') or []
        if i < len(s) and url and s[i].get('url') == url:
            return s[i].get('mask')
        return None

    def _on_mask_toggle(self, i: int, mask_on: list[bool], state: dict | None, ref: str | None):
        """🟥/⬜ switch slot ``i``'s masking → (mask_on, button, preview)."""
        on = list(mask_on)
        on[i] = not on[i]
        url = self.resolve_ref(ref)[0] if ref else None
        img = self._preview(url, self._payload_mask(state, i, url), on[i]) if url else gr.update()
        return on, gr.update(value=MASK_ICON_ON if on[i] else MASK_ICON_OFF), img

    def _on_mask_clear(self, i: int, mask_on: list[bool], state: dict | None, ref: str | None):
        """🧽 delete slot ``i``'s painted mask → (preview, status)."""
        url = self._mask_src(ref)
        if url is None or not drop_mask(url):
            gr.Info(f'slot {i + 1}: no painted mask', duration=0.5)
            return gr.update(), f'slot {i + 1}: no painted mask'
        img = self._preview(url, self._payload_mask(state, i, url), mask_on[i])
        return img, f'slot {i + 1}: mask removed'

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
            mask_tgls, mask_clrs = [], []
            mask_on = gr.State([True] * N_SLOTS)  # per-slot masking switch (🟥/⬜)
            slot_on = gr.State([True] * N_SLOTS)  # per-slot enable switch (✅/🚫)
            slot_tgls = []
            vision = gr.State([False] * N_SLOTS)  # per-slot pixel / vision switch (🖼/👁)
            vis_tgls = []
            # slot 1 (the main ref) gets its own row, the rest SLOTS_PER_ROW per row;
            # per slot: image, button row, role row
            rows = [[0]] + [
                list(range(r, min(N_SLOTS, r + SLOTS_PER_ROW)))
                for r in range(1, N_SLOTS, SLOTS_PER_ROW)
            ]

            def make_slot(i: int) -> None:
                imgs.append(
                    gr.Image(
                        type='filepath',
                        label=f'slot {i + 1}',
                        height=300,
                        interactive=False,
                        buttons=[],  # a click opens the fullscreen mask editor (t193)
                        elem_id=f'refdef-img-{i + 1}',
                        elem_classes=['refdef-img'],
                    )
                )
                refs.append(gr.State(''))
                with gr.Row():
                    slot_tgls.append(gr.Button(SLOT_ICON_ON, scale=0, min_width=40))
                    vis_tgls.append(
                        gr.Button(
                            VIS_ICON_PIXEL, scale=0, min_width=40, elem_classes=['refdef-vis']
                        )
                    )
                    slot_pulls.append(gr.Button('⟲', scale=0, min_width=40))
                    clears.append(gr.Button('✕', scale=0, min_width=40))
                    mask_tgls.append(gr.Button(MASK_ICON_ON, scale=0, min_width=40))
                    mask_clrs.append(gr.Button('🧽', scale=0, min_width=40))
                # slot 1: double height, fixed (scrollbar on overflow)
                n_lines = ROLE_LINES * 2 if i == 0 else ROLE_LINES
                roles.append(
                    gr.Textbox(
                        placeholder='role: what this ref is for',
                        show_label=False,
                        lines=n_lines,
                        max_lines=n_lines if i == 0 else None,
                        elem_classes=['refdef-role-main'] if i == 0 else None,
                    )
                )

            # slot 1 carried refs: the refs a slot-1 clip was rendered with, each
            # with a use switch (deployed as refdef.v1 `inherit` on pre-/post-vid)
            carry = gr.State(carry_of(None))
            carry_imgs, carry_tgls = [], []
            for row in rows:
                with gr.Row(equal_height=True):
                    if row == [0]:
                        with gr.Column(scale=1, elem_classes=['refdef-slot']):
                            make_slot(0)
                        with gr.Column(scale=2, visible=False, elem_id='refdef-carry') as carry_box:
                            carry_md = gr.Markdown()
                            for r0 in range(0, CARRY_CELLS, CARRY_PER_ROW):
                                with gr.Row():
                                    for _ in range(r0, min(CARRY_CELLS, r0 + CARRY_PER_ROW)):
                                        with gr.Column(min_width=180):
                                            carry_imgs.append(
                                                gr.Image(
                                                    type='pil',
                                                    height=240,
                                                    interactive=False,
                                                    show_label=True,
                                                    visible=False,
                                                )
                                            )
                                            carry_tgls.append(
                                                gr.Button(
                                                    SLOT_ICON_ON,
                                                    size='sm',
                                                    min_width=40,
                                                    visible=False,
                                                )
                                            )
                        continue
                    for i in row:
                        with gr.Column(elem_classes=['refdef-slot']):
                            make_slot(i)

            # 🎭 mask editor (shared by the slots, fullscreen overlay — t193): a click
            # on a slot image opens it; paint over the area to mask
            mask_slot = gr.State(None)
            with gr.Column(
                elem_id='refdef-mask-full', elem_classes=['refdef-mask-off']
            ) as mask_box:
                with gr.Group():
                    with gr.Row(equal_height=True):
                        mask_md = gr.Markdown()
                        mask_ok = gr.Button('✓', variant='primary', scale=0, min_width=40)
                        mask_copy = gr.Button('⎘', scale=0, min_width=40)
                        mask_del = gr.Button('🗑', scale=0, min_width=40)
                        mask_close = gr.Button(
                            '✕', scale=0, min_width=40, elem_id='refdef-mask-close'
                        )
                    mask_ed = gr.ImageEditor(
                        type='pil',
                        sources=(),
                        transforms=(),
                        layers=False,
                        brush=gr.Brush(
                            default_size=40, colors=[(f'rgb{MASK_TINT}', 0.5)], color_mode='fixed'
                        ),
                        eraser=gr.Eraser(default_size=40),
                        height='calc(100vh - 80px)',
                        show_label=False,
                    )

            status = gr.Markdown()
            # predefined prompts (t188): pick → text box; ➕ upserts by name; 🗑 deletes
            seed_prompts(self._pcol())
            with gr.Row(equal_height=True):
                prompt_dd = gr.Dropdown(
                    self._prompt_choices(),
                    value=None,
                    show_label=False,
                    container=False,
                    scale=4,
                    min_width=300,
                )
                p_name = gr.Textbox(placeholder='name', show_label=False, container=False, scale=1)
                p_cat = gr.Textbox(
                    placeholder='category', show_label=False, container=False, scale=1
                )
                p_models = gr.Textbox(
                    placeholder='models (generic)', show_label=False, container=False, scale=1
                )
                p_add = gr.Button('➕', scale=0, min_width=40)
                p_del = gr.Button('🗑', scale=0, min_width=40)
            text = gr.Textbox(label='prompt / prompt hint', lines=8, max_lines=30)
            with gr.Accordion('source / concepts / triggers', open=False):
                source_md = gr.Markdown(self._source_md(None, 0))
                entry_md = gr.Markdown()
            with gr.Accordion('raw payload (as pulled / last view switch)', open=False):
                raw = gr.Code(language='json', interactive=False)

            refs_roles = [c for pair in zip(refs, roles, strict=True) for c in pair]
            slot_outs = [c for trip in zip(imgs, refs, roles, strict=True) for c in trip]
            load_outs = [
                state, idx, raw, *slot_outs, kind, verb, text, source_md, entry_md, view, vision
            ]  # fmt: skip

            snap_ins = [state, idx, verb, kind, text, vision, *refs_roles]
            cur_hist = {'pos': None, 'draft': None}

            def pull(h, *a):
                out = self._on_pull(*a)
                # a pull that changed something makes the shown config the current one
                return [*out, cur_hist if isinstance(out[-1], str) else h]

            def hist_refresh(h, c):
                return self._hist_md(h['pos'], self._save_ids(c))

            # new slot content switches masking back on (all slots / one slot)
            # … and refreshes the 🖼/👁 buttons from the (loaded) vision switches
            on_outs = [mask_on, *mask_tgls, slot_on, *slot_tgls, *imgs, *vis_tgls]

            def vis_btn(i, on, vb):  # 🖼/👁 button of slot i; locked slots stay 🖼 (t189 D2)
                locked = vision_locked(i, vb)
                eye = bool(on) and not locked
                return gr.update(
                    value=VIS_ICON_VISION if eye else VIS_ICON_PIXEL,
                    interactive=not locked,
                    elem_classes=['refdef-vis', 'refdef-vis-on'] if eye else ['refdef-vis'],
                )

            def vis_btns(vis, vb):
                return [vis_btn(i, v, vb) for i, v in enumerate(vis or [False] * N_SLOTS)]

            def vis_toggle(i, vis, ref, vb):
                vis = list(vis)
                if not vis[i] and media_kind(self.resolve_ref(ref)[0] if ref else None) == 'audio':
                    gr.Info('👁 vision: images / videos only', duration=0.5)
                else:
                    vis[i] = not vis[i]
                return vis, vis_btn(i, vis[i], vb)

            def vis_reset(i, vis, vb):  # new slot content → 🖼
                vis = list(vis)
                vis[i] = False
                return vis, vis_btn(i, False, vb)

            def slot_vis(on):  # (button, preview dimming) of one slot
                return (
                    gr.update(value=SLOT_ICON_ON if on else SLOT_ICON_OFF),
                    gr.update(elem_classes=[] if on else ['refdef-slot-off']),
                )

            def all_on(vision_on, vb):
                vis = [slot_vis(True)] * N_SLOTS
                return [
                    [True] * N_SLOTS,
                    *[gr.update(value=MASK_ICON_ON)] * N_SLOTS,
                    [True] * N_SLOTS,
                    *[b for b, _ in vis],
                    *[im for _, im in vis],
                    *vis_btns(vision_on, vb),
                ]

            def slot_toggle(i, on):
                on = list(on)
                on[i] = not on[i]
                return on, *slot_vis(on[i])

            def slot_enable(i, on):
                on = list(on)
                on[i] = True
                return on, *slot_vis(True)

            def mask_btn_vals(on):
                return [gr.update(value=MASK_ICON_ON if o else MASK_ICON_OFF) for o in on]

            def painted_on(i, on):
                on = list(on)
                if i is not None:
                    on[i] = True
                return [on, *mask_btn_vals(on)]

            def one_on(i, on):
                on = list(on)
                on[i] = True
                return on, gr.update(value=MASK_ICON_ON)

            pull_btn.click(pull, [hist, state, *refs], [*load_outs, status, hist]).then(
                hist_refresh, [hist, cat], [hist_md]
            ).then(all_on, [vision, verb], on_outs)
            reset_btn.click(
                lambda: [*self._on_reset(), cur_hist], [], [*load_outs, status, hist]
            ).then(hist_refresh, [hist, cat], [hist_md]).then(all_on, [vision, verb], on_outs)
            prompt_dd.input(self._on_prompt_pick, [prompt_dd], [text, p_name, p_cat, p_models])
            p_add.click(self._on_prompt_add, [p_name, p_cat, p_models, text], [prompt_dd])
            p_del.click(self._on_prompt_del, [prompt_dd], [prompt_dd])
            save_btn.click(self._on_save, [cat, *snap_ins], [status, hist, hist_md, cat])
            del_btn.click(self._on_del, [hist, cat], [*load_outs, status, hist, hist_md, cat]).then(
                all_on, [vision, verb], on_outs
            )
            cat.input(self._on_cat, [hist, cat], [*load_outs, status, hist, hist_md]).then(
                all_on, [vision, verb], on_outs
            )
            view.input(
                lambda st, v, m, so, *rr: self._on_view(
                    st, v, m, *disable_slots(list(rr), so)[::2]
                ),
                [state, view, mask_on, slot_on, *refs_roles],
                [*load_outs, status],
            ).then(all_on, [vision, verb], on_outs)
            for btn, step in ((prev_btn, -1), (next_btn, 1)):
                btn.click(
                    lambda h, c, *a, step=step: self._on_hist(h, step, c, *a),
                    [hist, cat, *snap_ins],
                    [*load_outs, status, hist, hist_md],
                ).then(all_on, [vision, verb], on_outs)
            for i, (img, ref, clear) in enumerate(zip(imgs, refs, clears, strict=True)):
                # role stays: in enhancer mode it is payload-owned
                clear.click(lambda: (None, ''), [], [img, ref]).then(
                    lambda on, i=i: one_on(i, on), [mask_on], [mask_on, mask_tgls[i]]
                ).then(
                    lambda on, i=i: slot_enable(i, on), [slot_on], [slot_on, slot_tgls[i], img]
                ).then(
                    lambda v, vb, i=i: vis_reset(i, v, vb), [vision, verb], [vision, vis_tgls[i]]
                )
            for i, (img, ref, slot_pull) in enumerate(zip(imgs, refs, slot_pulls, strict=True)):
                slot_pull.click(self._on_slot_pull, [], [img, ref]).then(
                    lambda on, i=i: one_on(i, on), [mask_on], [mask_on, mask_tgls[i]]
                ).then(
                    lambda on, i=i: slot_enable(i, on), [slot_on], [slot_on, slot_tgls[i], img]
                ).then(
                    lambda v, vb, i=i: vis_reset(i, v, vb), [vision, verb], [vision, vis_tgls[i]]
                )
            for i, stgl in enumerate(slot_tgls):
                stgl.click(lambda on, i=i: slot_toggle(i, on), [slot_on], [slot_on, stgl, imgs[i]])
            for i, vtgl in enumerate(vis_tgls):
                vtgl.click(
                    lambda v, r, vb, i=i: vis_toggle(i, v, r, vb),
                    [vision, refs[i], verb],
                    [vision, vtgl],
                )
            verb.change(vis_btns, [vision, verb], vis_tgls, show_progress='hidden')
            for i, (tgl, clr) in enumerate(zip(mask_tgls, mask_clrs, strict=True)):
                tgl.click(
                    lambda on, st, r, i=i: self._on_mask_toggle(i, on, st, r),
                    [mask_on, state, refs[i]],
                    [mask_on, tgl, imgs[i]],
                )
                clr.click(
                    lambda on, st, r, i=i: self._on_mask_clear(i, on, st, r),
                    [mask_on, state, refs[i]],
                    [imgs[i], status],
                )
            for i, img in enumerate(imgs):
                img.select(
                    lambda r, i=i: self._on_mask_open(i, r),
                    [refs[i]],
                    [mask_box, mask_ed, mask_slot, mask_md],
                )
            for btn, copy_masked in ((mask_ok, False), (mask_copy, True)):
                btn.click(
                    lambda i, v, *r, c=copy_masked: self._on_mask_apply(i, v, c, *r),
                    [mask_slot, mask_ed, *refs],
                    [*imgs, mask_box, status],
                ).then(  # a freshly painted mask switches its slot back on
                    painted_on,
                    [mask_slot, mask_on],
                    [mask_on, *mask_tgls],
                )
            mask_del.click(self._on_mask_drop, [mask_slot, *refs], [*imgs, mask_box, status])
            mask_close.click(lambda: mask_overlay(False), [], [mask_box])
            carry_outs = [carry, carry_box, carry_md, *carry_imgs, *carry_tgls]
            refs[0].change(
                lambda *r: self._on_carry(*r), list(refs), carry_outs, show_progress='hidden'
            )
            for j, ctgl in enumerate(carry_tgls):
                ctgl.click(
                    lambda c, j=j: self._on_carry_toggle(c, j),
                    [carry],
                    [carry, ctgl, carry_imgs[j]],
                )
            deploy_btn.click(
                lambda st, v, k, a, t, m, so, vi, c, *rr: self._on_deploy(
                    st, v, k, a, t, m, vi, c, *disable_slots(list(rr), so)
                ),
                [state, verb, kind, auto, text, mask_on, slot_on, vision, carry, *refs_roles],
                [status],
            )
            update_btn.click(
                lambda st, v, m, so, *rr: self._on_update(st, v, m, *disable_slots(list(rr), so)),
                [state, verb, mask_on, slot_on, *refs_roles],
                [status],
            )
            join_btn.click(
                lambda so, *rr: self._on_join(*disable_slots(list(rr), so)),
                [slot_on, *refs_roles],
                [status],
            )


REFDEF_HEAD = r"""
<style>
#refdef-deploy { background: #2e7d32 !important; border-color: #2e7d32 !important;
  color: #fff !important; }
#refdef-cat-label { text-align: right; }
.refdef-role-main textarea { overflow-y: auto !important; }
.refdef-slot-off { opacity: 0.3; }
/* 👁 vision slot (t189): a big eye over the preview, set by the 🖼/👁 button */
.refdef-slot:has(.refdef-vis-on) [id^="refdef-img-"] { position: relative; }
.refdef-slot:has(.refdef-vis-on) [id^="refdef-img-"]::after {
  content: '\1F441\FE0F'; position: absolute; inset: 0; display: flex; align-items: center;
  justify-content: center; font-size: 110px; opacity: 0.6; pointer-events: none;
  z-index: 20; text-shadow: 0 0 12px #000; }
#refdef-deploy:hover { background: #388e3c !important; }
/* t193: a click on a slot image opens the mask editor as a fullscreen overlay */
.refdef-img img { cursor: crosshair; }
#refdef-mask-full { position: fixed !important; inset: 0; z-index: 1000; margin: 0 !important;
  padding: 8px; border-radius: 0; background: var(--body-background-fill); overflow: auto; }
#refdef-mask-full.refdef-mask-off { visibility: hidden; pointer-events: none; }
</style>
<script>
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  const box = document.getElementById('refdef-mask-full');
  if (box && box.classList.contains('refdef-mask-on')) document.getElementById('refdef-mask-close')?.click();
});
</script>
"""
