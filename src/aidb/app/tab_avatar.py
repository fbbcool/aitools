"""avatar tab of the AIDB scene app (board FEATURE t218).

Create / shape / edit avatars of the ``avatars`` collection (``aidb.avatar``):
picker + ➕ new / ✎ rename / 🗑 delete (name box = slug, slugified), metadata
editors (display name, description, triggers + tags as comma lists, loras /
prompt guides / extra as JSON) saved by 💾, and a media grid with an editable
role per item (saved on blur: DB + embedded ait_role where supported).

``⟲ pull`` adds media from the clipspace (img url / url list / img id / scene
id, same resolution as the refdef pull; the source's embedded role becomes the
item role, a source already in the avatar is skipped). ``⇪ deploy`` writes the
selected media (☑ per item, avatar order) as a plain url list — what the refdef
pull fills its slots from. Roles do not go to refdef in v1 (t218 deferred).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import gradio as gr
import pyperclip
from PIL import Image

from aidb.app.tab_refdef import RefdefTab, clip_copy
from aidb.avatar import AvatarError, AvatarManager, refdef_urls, slugify
from ait.tools.role import descr as role_descr, role as file_role

THUMB_SIZE: Final = 320
PER_ROW: Final = 4
KIND_ICON: Final = {'image': '🖼', 'video': '🎞', 'audio': '♪'}

# hover tooltips (t218 follow-up): gr.Button has no title param → each button carries
# the class ``av-tip-<key>`` and AVATAR_HEAD's observer sets ``title`` from this map
# (also on buttons the media grid re-renders).
TIPS: Final = {
    'new': 'create a new avatar from the name box (slugified = its name + media dir)',
    'rename': 'rename the selected avatar to the name box — moves its media dir',
    'delete': 'delete the selected avatar + its media dir (copies only, originals kept)'
    ' — asks for confirmation',
    'save': 'save display name, triggers, tags, description, loras, prompt guides + extra',
    'pull': 'add media from the clipspace (img url / url list / img id / scene id) — '
    'copied into the avatar dir; sources already in the avatar are skipped',
    'deploy': 'write the selected media as a url list to the clipspace for refdef pull '
    '(roles not included)',
    'all': 'select all media / clear the selection',
    'left': 'move this media item one place left (earlier in deploy order)',
    'right': 'move this media item one place right (later in deploy order)',
    'remove': 'remove this media item and delete its copy — no confirmation, original kept',
}


# gradio's own buttons inside a component (no gr.Button, no class of their own): the
# component carries ``av-tipin-<key>``; its buttons WITHOUT a gradio title get these
# tips in DOM order (the last one repeats).
INNER_TIPS: Final = {
    'code': ('download this JSON as a file', 'copy this JSON to the clipboard'),
    'thumb': ('media preview (video = first frame, audio = waveform)',),
}
CODE_BUTTONS: Final = ['download', 'copy']  # explicit = fixed order for INNER_TIPS['code']


def tip_inner(key: str) -> list[str]:
    """elem_classes of a component whose built-in buttons get INNER_TIPS[`key`]."""
    if key not in INNER_TIPS:
        raise KeyError(f'no inner tooltip {key!r}')
    return [f'av-tipin-{key}']


def tip(key: str) -> list[str]:
    """elem_classes of a button with tooltip `key` (see TIPS / AVATAR_HEAD)."""
    if key not in TIPS:
        raise KeyError(f'no tooltip {key!r}')
    return ['av-tip', f'av-tip-{key}']


# ---------------------------------------------------------------------- #
# pure helpers (unit-tested)
# ---------------------------------------------------------------------- #
def parse_list(text: str | None) -> list[str]:
    """Comma / newline separated → stripped list (blanks dropped, order kept)."""
    out: list[str] = []
    for part in (text or '').replace('\n', ',').split(','):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


def parse_json(text: str | None, field: str, want: type) -> Any:
    """JSON editor value → `want` (list / dict); blank = empty. Raises AvatarError."""
    if not (text or '').strip():
        return want()
    try:
        v = json.loads(text)  # type: ignore[arg-type]
    except ValueError as e:
        raise AvatarError(f'{field}: invalid JSON ({e})') from e
    if not isinstance(v, want):
        raise AvatarError(f'{field}: JSON {want.__name__} expected')
    return v


def dump_json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, indent=2)


def ui_fields(av: dict | None) -> list[Any]:
    """Avatar → editor values (display, description, triggers, tags, loras, guides, extra)."""
    av = av or {}
    return [
        av.get('display_name', ''),
        av.get('description', ''),
        ', '.join(av.get('triggers') or []),
        ', '.join(av.get('tags') or []),
        dump_json(av.get('loras') or []),
        dump_json(av.get('prompt_guides') or []),
        dump_json(av.get('extra') or {}),
    ]


def fields_from_ui(display, description, triggers, tags, loras, guides, extra) -> dict:
    return {
        'display_name': display or '',
        'description': description or '',
        'triggers': parse_list(triggers),
        'tags': parse_list(tags),
        'loras': parse_json(loras, 'loras', list),
        'prompt_guides': parse_json(guides, 'prompt guides', list),
        'extra': parse_json(extra, 'extra', dict),
    }


def selected_in_order(av: dict, sel: list[str] | None) -> list[str]:
    """Selected mids that still exist, in avatar media order."""
    chosen = set(sel or [])
    return [m['mid'] for m in av.get('media') or [] if m['mid'] in chosen]


def deploy_text(av: dict, sel: list[str] | None) -> str:
    return '\n'.join(refdef_urls(av, selected_in_order(av, sel)))


def moved(mids: list[str], mid: str, step: int) -> list[str]:
    """`mids` with `mid` moved one place left (-1) / right (+1), clamped."""
    if mid not in mids:
        return list(mids)
    out = list(mids)
    i = out.index(mid)
    j = max(0, min(len(out) - 1, i + step))
    out.insert(j, out.pop(i))
    return out


# ---------------------------------------------------------------------- #
# tab
# ---------------------------------------------------------------------- #
class AvatarTab:
    def __init__(self, dbc, verbose: int = 0) -> None:
        self._am = AvatarManager(dbc=dbc, verbose=verbose)
        self._refdef = RefdefTab(dbc)  # clipspace resolution + previews, shared with refdef
        self._verbose = verbose
        self._thumbs: dict[tuple[str, float], Image.Image | str | None] = {}

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[avatar_tab:{level}] {msg}')

    def _thumb(self, url: str) -> Image.Image | str | None:
        try:
            key = (url, Path(url).stat().st_mtime)
        except OSError:
            return None
        if key not in self._thumbs:
            im = RefdefTab._preview(url)
            if isinstance(im, Image.Image):
                im = im.copy()
                im.thumbnail((THUMB_SIZE, THUMB_SIZE))
            self._thumbs[key] = im
        return self._thumbs[key]

    def _choices(self) -> list[tuple[str, str]]:
        out = []
        for d in self._am.list():
            dn = d.get('display_name') or d['name']
            out.append((dn if dn == d['name'] else f'{dn} ({d["name"]})', d['name']))
        return out

    # -- handlers ------------------------------------------------------- #
    def _on_refresh(self, name: str | None):
        names = self._am.names()
        return gr.update(choices=self._choices(), value=name if name in names else None)

    def _on_pick(self, name: str | None, rev: int):
        av = self._am.get(name) if name else None
        return [*ui_fields(av), [], rev + 1, '']

    def _on_new(self, text: str | None, rev: int):
        name = slugify(text or '')
        try:
            self._am.create(name, (text or '').strip() or None)
        except AvatarError as e:
            return [gr.update(), gr.update(), rev, f'❌ {e}']
        return [gr.update(choices=self._choices(), value=name), '', rev, f'created `{name}`']

    def _on_rename(self, name: str | None, text: str | None, rev: int):
        if not name:
            return [gr.update(), gr.update(), rev, '❌ no avatar selected']
        new = slugify(text or '')
        try:
            self._am.rename(name, new)
        except AvatarError as e:
            return [gr.update(), gr.update(), rev, f'❌ {e}']
        return [gr.update(choices=self._choices(), value=new), '', rev + 1, f'`{name}` → `{new}`']

    def _on_delete(self, name: str | None, rev: int):
        if not name:  # also: confirm cancelled
            return [gr.update(), rev, '']
        ok = self._am.delete(name)
        return [gr.update(choices=self._choices(), value=None), rev + 1, f'deleted `{name}`: {ok}']

    def _on_save(self, name: str | None, *ui):
        if not name:
            return '❌ no avatar selected'
        try:
            self._am.update(name, **fields_from_ui(*ui))
        except AvatarError as e:
            return f'❌ {e}'
        return f'saved `{name}`'

    def _on_pull(self, name: str | None, rev: int):
        if not name:
            return [rev, '❌ no avatar selected']
        items = self._refdef.images_from_clipspace(pyperclip.paste())
        if not items:
            gr.Info('nothing usable to pull', duration=0.5)
            return [rev, gr.update()]
        av = self._am.get(name) or {}
        have = {m.get('src') for m in av.get('media') or []}
        n_add, n_skip, errs = 0, 0, []
        for url, _id in items:
            if url in have:
                n_skip += 1
                continue
            try:
                self._am.add_media(name, url, role=role_descr(file_role(url)))
                have.add(url)
                n_add += 1
            except AvatarError as e:
                errs.append(str(e))
        msg = f'pulled {n_add} item(s)' + (f', {n_skip} already in' if n_skip else '')
        msg += f' · ❌ {"; ".join(errs)}' if errs else ''
        return [rev + 1 if n_add else rev, msg]

    def _on_deploy(self, name: str | None, sel: list[str]):
        av = self._am.get(name) if name else None
        text = deploy_text(av, sel) if av else ''
        if not text:
            gr.Info('nothing selected', duration=0.5)
            return gr.update()
        clip_copy(text)
        return f'deployed {len(text.splitlines())} url(s)'

    def _on_select_all(self, name: str | None, sel: list[str], rev: int):
        av = self._am.get(name) if name else None
        mids = [m['mid'] for m in (av or {}).get('media') or []]
        return [[] if mids and set(mids) <= set(sel or []) else mids, rev + 1]

    # -- UI ------------------------------------------------------------- #
    def build(self) -> None:
        with gr.Tab('avatar', elem_id='av_tab') as tab:
            rev = gr.State(0)  # bumped by every structural change → grid re-render
            sel = gr.State([])  # selected mids
            with gr.Row():
                pick = gr.Dropdown(choices=self._choices(), value=None, label='avatar', scale=3)
                name_box = gr.Textbox(placeholder='name', show_label=False, scale=2)
                new_btn = gr.Button('➕', scale=0, min_width=48, elem_classes=tip('new'))
                ren_btn = gr.Button('✎', scale=0, min_width=48, elem_classes=tip('rename'))
                del_btn = gr.Button(
                    '🗑', variant='stop', scale=0, min_width=48, elem_classes=tip('delete')
                )
            with gr.Row():
                display = gr.Textbox(label='display name', scale=2)
                triggers = gr.Textbox(label='triggers', scale=2)
                tags = gr.Textbox(label='tags', scale=2)
                save_btn = gr.Button(
                    '💾', variant='primary', scale=0, min_width=48, elem_classes=tip('save')
                )
            description = gr.Textbox(label='description', lines=3)
            with gr.Row():
                loras = gr.Code(
                    language='json',
                    label='loras',
                    lines=8,
                    buttons=CODE_BUTTONS,
                    elem_classes=tip_inner('code'),
                )
                guides = gr.Code(
                    language='json',
                    label='prompt guides',
                    lines=8,
                    buttons=CODE_BUTTONS,
                    elem_classes=tip_inner('code'),
                )
                extra = gr.Code(
                    language='json',
                    label='extra',
                    lines=8,
                    buttons=CODE_BUTTONS,
                    elem_classes=tip_inner('code'),
                )
            with gr.Row():
                pull_btn = gr.Button(
                    '⟲ pull', variant='primary', scale=0, min_width=100, elem_classes=tip('pull')
                )
                deploy_btn = gr.Button(
                    '⇪ deploy',
                    variant='primary',
                    scale=0,
                    min_width=100,
                    elem_classes=tip('deploy'),
                )
                all_btn = gr.Button('☑', scale=0, min_width=48, elem_classes=tip('all'))
                status = gr.Markdown()
            meta = [display, description, triggers, tags, loras, guides, extra]

            @gr.render(inputs=[pick, sel], triggers=[rev.change])
            def grid(name, selected):
                av = self._am.get(name) if name else None
                media = (av or {}).get('media') or []
                selected = list(selected or [])
                mids = [m['mid'] for m in media]
                for r in range(0, len(media), PER_ROW):
                    with gr.Row():
                        for m in media[r : r + PER_ROW]:
                            self._cell(name, m, mids, selected, sel, rev, status)
                        for _ in range(PER_ROW - len(media[r : r + PER_ROW])):
                            gr.Column(min_width=THUMB_SIZE // 2)  # keep cell widths

            tab.select(self._on_refresh, [pick], [pick])
            pick.change(self._on_pick, [pick, rev], [*meta, sel, rev, status])
            new_btn.click(self._on_new, [name_box, rev], [pick, name_box, rev, status])
            name_box.submit(self._on_new, [name_box, rev], [pick, name_box, rev, status])
            ren_btn.click(self._on_rename, [pick, name_box, rev], [pick, name_box, rev, status])
            del_btn.click(
                self._on_delete,
                [pick, rev],
                [pick, rev, status],
                js='(n, r) => [(n && confirm("Delete avatar " + n + " and its media copies?")) ? n : null, r]',
            )
            save_btn.click(self._on_save, [pick, *meta], [status])
            pull_btn.click(self._on_pull, [pick, rev], [rev, status])
            deploy_btn.click(self._on_deploy, [pick, sel], [status])
            all_btn.click(self._on_select_all, [pick, sel, rev], [sel, rev])

    def _cell(self, name, m, mids, selected, sel, rev, status) -> None:
        mid = m['mid']
        with gr.Column(min_width=THUMB_SIZE // 2):
            gr.Image(
                value=self._thumb(m['url']),
                show_label=False,
                interactive=False,
                height=THUMB_SIZE,
                elem_classes=tip_inner('thumb'),
                key=f'av-img-{mid}',
            )
            role = gr.Textbox(
                value=m.get('role') or '',
                show_label=False,
                placeholder='role',
                lines=2,
                interactive=True,
                key=f'av-role-{mid}',
            )
            with gr.Row():
                chk = gr.Checkbox(
                    value=mid in selected,
                    label=f'{KIND_ICON.get(m["kind"], "?")} {Path(m["url"]).name}',
                    scale=3,
                    interactive=True,
                    key=f'av-sel-{mid}',
                )
                left = gr.Button('◀', scale=0, min_width=36, size='sm', elem_classes=tip('left'))
                right = gr.Button('▶', scale=0, min_width=36, size='sm', elem_classes=tip('right'))
                rm = gr.Button(
                    '🗑',
                    scale=0,
                    min_width=36,
                    size='sm',
                    variant='stop',
                    elem_classes=tip('remove'),
                )

        def on_role(text):
            cur = self._am.media(name, mid)
            if cur is not None and (cur.get('role') or '') == (text or '').strip():
                return gr.update()  # plain blur: no rewrite (video role = ffmpeg remux)
            try:
                self._am.set_role(name, mid, text or '')
            except AvatarError as e:
                return f'❌ {e}'
            return f'role saved · {Path(m["url"]).name}'

        def on_chk(on, cur):
            cur = [x for x in (cur or []) if x != mid]
            return cur + [mid] if on else cur

        def on_move(step):
            def fn(r):
                self._am.reorder(name, moved(mids, mid, step))
                return r + 1

            return fn

        def on_rm(r, cur):
            self._am.remove_media(name, mid)
            return r + 1, [x for x in (cur or []) if x != mid], f'removed {Path(m["url"]).name}'

        role.blur(on_role, [role], [status])
        role.submit(on_role, [role], [status])
        chk.input(on_chk, [chk, sel], [sel])
        left.click(on_move(-1), [rev], [rev])
        right.click(on_move(1), [rev], [rev])
        rm.click(on_rm, [rev, sel], [rev, sel, status])


AVATAR_HEAD: Final = (
    """
<script>
(() => {
  const TIPS = """
    + json.dumps(TIPS, ensure_ascii=False)
    + """;
  const INNER = """
    + json.dumps(INNER_TIPS, ensure_ascii=False)
    + """;
  // title on the classed element and any inner <button>; re-applied on every DOM
  // change, so buttons of a re-rendered media grid get their tip again
  function apply(){
    for (const [k, t] of Object.entries(TIPS)) {
      document.querySelectorAll('.av-tip-' + k).forEach(el => {
        if (el.title !== t) el.title = t;
        el.querySelectorAll('button').forEach(b => { if (b.title !== t) b.title = t; });
      });
    }
    for (const [k, ts] of Object.entries(INNER)) {
      document.querySelectorAll('.av-tipin-' + k).forEach(el => {
        let i = 0;
        el.querySelectorAll('button').forEach(b => {
          if (b.title && !b.dataset.avTip) return;  // gradio's own title wins
          const t = ts[Math.min(i++, ts.length - 1)];
          if (b.title !== t) b.title = t;
          b.dataset.avTip = '1';
        });
      });
    }
  }
  let pending = false;
  new MutationObserver(() => {
    if (pending) return; pending = true;
    requestAnimationFrame(() => { pending = false; apply(); });
  }).observe(document.documentElement, {childList: true, subtree: true});
  document.addEventListener('DOMContentLoaded', () => apply());
})();
</script>
"""
)
