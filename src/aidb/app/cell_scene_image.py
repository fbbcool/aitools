import html as html_lib
import json
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage

from aidb.app.html import AppHtml, HtmlHelper
from aidb.scene import Scene, SceneDef
from aidb.scene.scene_image import SceneImage

from ait.caption.joy import LABEL_PROMPT
from ait.caption.skin import Skin, SkinRegistry
from ait.tools.images import image_from_url, _image_extract_prompt_from_info_ext


_DEFAULT_SKIN_NAME = '1xlasm'
_SKIN_CACHE: dict[str, Skin] = {}


def _skin(name: str = _DEFAULT_SKIN_NAME) -> Optional[Skin]:
    """Lazily load a Skin from the registry. Returns None if loading fails
    (e.g. CONF_AIT not set, file missing) so the editor degrades gracefully."""
    if name in _SKIN_CACHE:
        return _SKIN_CACHE[name]
    try:
        s = SkinRegistry().get(name)
    except Exception as e:
        print(f'[cell_scene_image] failed to load skin {name!r}: {e}')
        return None
    _SKIN_CACHE[name] = s
    return s


def editor_labels() -> list[str]:
    """
    Returns the canonical list of labels available in the editor UI:
    the keys of `LABEL_PROMPT` from the captioner, with 'none' removed.
    Dict insertion order is preserved.
    """
    return [k for k in LABEL_PROMPT.keys() if k != 'none']


class AppSceneImageCell:
    """
    HTML generation for a single SceneImage cell in the editor view.

    The cell contains:
      - image preview
      - rating radio buttons
      - editable caption textarea
      - editable prompt textarea
    """

    THUMB_MAX_SIDE: int = 256

    @staticmethod
    def html_info(
        obj: SceneImage,
        set_id: Optional[str] = None,
        excluded: bool = False,
    ) -> str:
        """
        Compact read-only image cell for informational sections (e.g., the
        Set Editor's Prototype / Excluded sections).

        Shows only: thumbnail (clickable into the lightbox), id row with the
        url copy buttons, and — when a `set_id` is provided — the per-image
        exclude toggle. No caption / hints / labels editors.
        """
        pil = AppSceneImageCell._load_thumb(obj)
        img_b64: Optional[str] = HtmlHelper.pil_to_base64(pil)
        if img_b64 is None:
            img_b64 = ''

        thumb_onclick = AppSceneImageCell._html_lightbox_onclick(
            target_type='registered', target=obj.id, set_id=set_id
        )

        url = obj.url_from_data
        url_str = str(url) if url is not None else ''
        url_copy_btn = AppSceneImageCell._html_copy_static_button(url_str, label='url')

        scene_url = obj.data.get(SceneDef.FIELD_URL_PARENT)
        scene_url_str = str(scene_url) if scene_url else ''
        url_scene_copy_btn = AppSceneImageCell._html_copy_static_button(
            scene_url_str, label='url scene'
        )

        exclude_html = ''
        if set_id:
            exclude_html = AppSceneImageCell._html_exclude_checkbox(
                set_id=set_id, img_id=obj.id, checked=excluded
            )
        toggles_row = (
            f'<div class="simg-edit-toggles">{exclude_html}</div>'
            if exclude_html else ''
        )

        return f"""
        <div class="image-item simg-info-cell" id="cell-simg-info-{obj.id}">
            <img src="data:image/png;base64,{img_b64}" onclick="{thumb_onclick}">
            {toggles_row}
            <div class="image-controls">
                <div class="simg-edit-id-row">
                    <div class="simg-edit-id">id: {obj.id}</div>
                    {url_copy_btn}
                    {url_scene_copy_btn}
                </div>
            </div>
        </div>
        """

    @staticmethod
    def html(
        obj: SceneImage,
        set_id: Optional[str] = None,
        excluded: bool = False,
    ) -> str:
        pil = AppSceneImageCell._load_thumb(obj)
        img_b64: Optional[str] = HtmlHelper.pil_to_base64(pil)
        if img_b64 is None:
            img_b64 = ''
            print(f'Warning: No image available for SceneImage ID: {obj.id}.')

        rating_html = AppSceneImageCell._html_rating(obj)
        labels_html = AppSceneImageCell._html_labels(obj)
        # The caption field gets a 'set' button (in addition to copy + save)
        # which copies caption_joy into the caption textarea (DOM-only).
        # If caption_joy is empty the backend generates a caption that is
        # then written into both fields.
        caption_field = AppSceneImageCell._html_text_field(
            obj,
            attr_setter='set_caption',
            label='caption',
            value=obj.caption,
            multiline=True,
            extra_header_buttons=[AppSceneImageCell._html_set_button(obj.id)],
            rows=9,
        )
        hints_field = AppSceneImageCell._html_text_field(
            obj,
            attr_setter='set_hints',
            label='hints',
            value=obj.hints,
            multiline=True,
        )
        caption_joy_field = AppSceneImageCell._html_text_field(
            obj,
            attr_setter='set_caption_joy',
            label='caption_joy',
            value=obj.caption_joy,
            multiline=True,
        )
        prompt_field = AppSceneImageCell._html_text_field(
            obj,
            attr_setter='set_prompt',
            label='prompt',
            value=obj.prompt,
            multiline=True,
            with_save=False,
        )

        url = obj.url_from_data
        url_str = str(url) if url is not None else ''
        url_copy_btn = AppSceneImageCell._html_copy_static_button(url_str, label='url')

        scene_url = obj.data.get(SceneDef.FIELD_URL_PARENT)
        scene_url_str = str(scene_url) if scene_url else ''
        url_scene_copy_btn = AppSceneImageCell._html_copy_static_button(
            scene_url_str, label='url scene'
        )
        goto_scene_btn = AppSceneImageCell._html_goto_scene_button(obj.scene_id)

        caption_btn_1xlasm = AppSceneImageCell._html_caption_button(
            target_type='registered',
            target=obj.id,
            trigger='1xlasm',
            label='caption 1xlasm',
        )
        caption_btn_1xlasm_clip = AppSceneImageCell._html_caption_button(
            target_type='registered',
            target=obj.id,
            trigger='1xlasm',
            label='caption 1xlasm clip',
            clip_only=True,
        )
        caption_btn_gts = AppSceneImageCell._html_caption_button(
            target_type='registered',
            target=obj.id,
            trigger='gts_prompter',
            label='caption gts_prompter',
        )

        thumb_onclick = AppSceneImageCell._html_lightbox_onclick(
            target_type='registered', target=obj.id, set_id=set_id
        )

        exclude_html = ''
        if set_id:
            exclude_html = AppSceneImageCell._html_exclude_checkbox(
                set_id=set_id, img_id=obj.id, checked=excluded
            )
        prototype_html = AppSceneImageCell._html_prototype_checkbox(
            img_id=obj.id, checked=obj.prototype
        )
        toggles_row = (
            f'<div class="simg-edit-toggles">{prototype_html}{exclude_html}</div>'
        )

        labels_ng_html = AppSceneImageCell._html_labels_ng(obj)

        id_copy_btn = AppSceneImageCell._html_copy_static_button(obj.id, label='id')

        return f"""
        <div class="image-item simg-edit-cell" id="cell-simg-{obj.id}">
            <div class="simg-edit-image-row">
                <div class="simg-edit-image-col">
                    <img src="data:image/png;base64,{img_b64}" onclick="{thumb_onclick}">
                    {toggles_row}
                    {hints_field}
                    <div class="simg-edit-field simg-edit-rating">
                        <label class="simg-edit-label">rating</label>
                        <div class="operation-radio-group">
                            {rating_html}
                        </div>
                    </div>
                    <div class="simg-edit-image-col-links">
                        {id_copy_btn}
                        {url_copy_btn}
                        {url_scene_copy_btn}
                        {goto_scene_btn}
                    </div>
                </div>
                {labels_ng_html}
            </div>
            <div class="image-controls">
                {caption_field}
                <div class="simg-edit-id-row">
                    <div class="simg-edit-id">id: {obj.id}</div>
                </div>
                <div class="simg-edit-field">
                    <label class="simg-edit-label">labels</label>
                    <div class="operation-radio-group">
                        {labels_html}
                    </div>
                </div>
                {caption_joy_field}
                {prompt_field}
                <div class="simg-cell-actions">
                    {caption_btn_1xlasm}
                    {caption_btn_1xlasm_clip}
                    {caption_btn_gts}
                </div>
            </div>
        </div>
        """

    @staticmethod
    def _load_thumb(obj: SceneImage) -> Optional[PILImage.Image]:
        url = obj.url_from_data
        if url is None:
            return None
        pil = image_from_url(url)
        if pil is None:
            return None
        try:
            pil.thumbnail((AppSceneImageCell.THUMB_MAX_SIDE, AppSceneImageCell.THUMB_MAX_SIDE))
        except Exception:
            pass
        return pil

    @staticmethod
    def _html_rating(obj: SceneImage) -> str:
        current_rating = obj.rating

        html = ''
        for r in range(SceneDef.RATING_MIN, SceneDef.RATING_MAX + 1):
            checked = current_rating == r
            html += AppHtml.html_make_cmd_button(
                AppHtml.make_cmd_data(
                    'image',
                    obj.id,
                    'db_query',
                    payload={'set_rating': r},
                    label=str(r),
                ),
                checked=checked,
            )
        return html

    @staticmethod
    def _html_labels_ng(obj: SceneImage) -> str:
        """
        Structured `labels_ng` editor: three top-level boxes (primary entity,
        secondary entity, interaction) each containing a sub-box per
        label-group. Each label is a toggleable button — clicking flips the
        full path (e.g. `primary.attribute.busty`) on the SceneImage's
        `labels_ng` field via the `switch_label_ng` cmd.
        """
        skin = _skin()
        if skin is None:
            return (
                '<div class="simg-edit-labels-ng simg-labels-ng-error">'
                '<div class="simg-edit-label">labels_ng</div>'
                '<div class="simg-labels-ng-empty">(skin unavailable)</div>'
                '</div>'
            )

        applied = set(obj.labels_ng)
        blocks: list[tuple[str, str, dict]] = []  # (entity_tag, title, label_groups)
        primary = skin.entities_primary
        blocks.append(('primary', primary.phrase or 'primary', primary.label_groups))
        if skin.entities_secondary is not None:
            secondary = skin.entities_secondary
            blocks.append(('secondary', secondary.phrase or 'secondary', secondary.label_groups))
        if skin.interaction is not None:
            blocks.append(('interaction', 'interaction', skin.interaction.label_groups))

        out: list[str] = []
        for entity_tag, title, groups in blocks:
            group_html: list[str] = []
            for group_name, group in groups.items():
                btn_html = ''
                # Display labels alphabetically by name within each group;
                # the source declaration order is preserved in `_built` for
                # render_label_prompts but is not the right order for the UI.
                for lab in sorted(group.labels, key=lambda l: l.name):
                    path = f'{entity_tag}.{group_name}.{lab.name}'
                    btn_html += AppHtml.html_make_cmd_button(
                        AppHtml.make_cmd_data(
                            'image',
                            obj.id,
                            'db_query',
                            payload={'switch_label_ng': path},
                            label=lab.name,
                        ),
                        checked=path in applied,
                    )
                group_html.append(
                    f'<div class="simg-labels-ng-group">'
                    f'  <div class="simg-labels-ng-group-title">{html_lib.escape(group_name, quote=True)}</div>'
                    f'  <div class="operation-radio-group">{btn_html}</div>'
                    f'</div>'
                )
            out.append(
                f'<div class="simg-labels-ng-block">'
                f'  <div class="simg-labels-ng-title">{html_lib.escape(title, quote=True)}</div>'
                f'  {"".join(group_html)}'
                f'</div>'
            )

        return (
            '<div class="simg-edit-labels-ng">'
            '<div class="simg-edit-label">labels_ng</div>'
            f'{"".join(out)}'
            '</div>'
        )

    @staticmethod
    def _html_labels(obj: SceneImage) -> str:
        """
        Toggleable label buttons (mirrors the Scene 'label' operation).
        Clicking a label sends a `switch_label` cmd which flips its membership.
        """
        current_labels = obj.labels
        html = ''
        for label in editor_labels():
            checked = label in current_labels
            html += AppHtml.html_make_cmd_button(
                AppHtml.make_cmd_data(
                    'image',
                    obj.id,
                    'db_query',
                    payload={'switch_label': label},
                    label=label,
                ),
                checked=checked,
            )
        return html

    @staticmethod
    def _html_text_field(
        obj: SceneImage,
        attr_setter: str,
        label: str,
        value: Optional[str],
        multiline: bool = True,
        with_save: bool = True,
        extra_header_buttons: Optional[list[str]] = None,
        rows: int = 3,
    ) -> str:
        """
        Renders a full editable text-field block:

            <div class="simg-edit-field">
                <div class="simg-edit-field-header">
                    <label>{label}</label>
                    <button class="simg-copy-btn">copy</button>
                    <button class="simg-save-btn">save</button>
                </div>
                <textarea/input>
            </div>

        - copy: copies the input's current visible value to clipboard
        - save: explicitly stores the input's current value to the DB via
                the cmd-bus (overwriting whatever was there before)
        """
        if value is None:
            value = ''

        safe_value = html_lib.escape(value, quote=True)
        elem_id = f'simg-{attr_setter}-{obj.id}'

        # `oninput` flags the wrapping field as stale on user edit; the
        # save-button JS clears the flag after firing the save cmd.
        stale_oninput = (
            "this.closest('.simg-edit-field').classList.add('simg-stale')"
        )
        if multiline:
            input_html = (
                f'<textarea id="{elem_id}" class="simg-edit-textarea" rows="{rows}" '
                f'oninput="{stale_oninput}">'
                f'{safe_value}</textarea>'
            )
        else:
            input_html = (
                f'<input type="text" id="{elem_id}" class="simg-edit-input" '
                f'value="{safe_value}" oninput="{stale_oninput}">'
            )

        copy_btn_html = AppSceneImageCell._html_copy_button(elem_id)
        clear_btn_html = AppSceneImageCell._html_clear_button(elem_id)
        save_btn_html = ''
        if with_save:
            save_btn_html = AppSceneImageCell._html_save_button(
                target_elem_id=elem_id,
                obj_id=obj.id,
                attr_setter=attr_setter,
                label=label,
            )
        extras = ''.join(extra_header_buttons or [])

        return f"""
        <div class="simg-edit-field">
            <div class="simg-edit-field-header">
                <label class="simg-edit-label" for="{elem_id}">{label}</label>
                <div class="simg-edit-field-actions">
                    {extras}
                    {copy_btn_html}
                    {clear_btn_html}
                    {save_btn_html}
                </div>
            </div>
            {input_html}
        </div>
        """

    @staticmethod
    def _html_save_button(
        target_elem_id: str,
        obj_id: str,
        attr_setter: str,
        label: str,
    ) -> str:
        """
        Save button for an editable text field. When clicked it reads the
        current value of the linked input/textarea, packages a cmd-bus
        `db_query` cmd with `{attr_setter: value}` payload, and triggers the
        existing hidden cmd-button so the server stores the value
        (overwriting any previous value).
        """
        elem_id_btn = AppHtml.elem_id_cmd_button()
        elem_id_bus = AppHtml.elem_id_cmd_databus()

        cmd_skeleton = {
            'type': 'image',
            'id': obj_id,
            'cmd': 'db_query',
            'payload': {attr_setter: '__VALUE__'},
            'label': label,
        }
        skeleton_json = json.dumps(cmd_skeleton)

        js = f"""
        event.stopPropagation();
        const el = document.getElementById('{target_elem_id}');
        if (!el) {{ return; }}
        const v = el.value;
        const skel = JSON.parse('{skeleton_json}');
        skel.payload['{attr_setter}'] = v;
        const bus = document.querySelector('#{elem_id_bus} textarea');
        if (bus) {{
            bus.value = JSON.stringify(skel);
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
        const trig = document.getElementById('{elem_id_btn}');
        if (trig) {{ trig.click(); }}
        const btn = event.currentTarget;
        const field = btn.closest('.simg-edit-field');
        if (field) {{ field.classList.remove('simg-stale'); }}
        const orig = btn.textContent;
        btn.textContent = 'saved';
        btn.classList.add('simg-copy-btn-ok');
        setTimeout(function() {{
            btn.textContent = orig;
            btn.classList.remove('simg-copy-btn-ok');
        }}, 800);
        """.replace('\n', ' ').replace('"', '&quot;')
        return f'<button type="button" class="simg-save-btn" onclick="{js}">save</button>'

    @staticmethod
    def _html_copy_button(target_elem_id: str, label: str = 'copy') -> str:
        """
        Small copy-to-clipboard button. Reads the value of the element with id
        `target_elem_id` (an <input> or <textarea>) and writes it to the user's
        clipboard via navigator.clipboard.writeText (with execCommand fallback).
        """
        js = f"""
        event.stopPropagation();
        const el = document.getElementById('{target_elem_id}');
        if (!el) {{ return; }}
        const v = el.value;
        const ok = function() {{
            const btn = event.currentTarget;
            const orig = btn.textContent;
            btn.textContent = 'copied';
            btn.classList.add('simg-copy-btn-ok');
            setTimeout(function() {{
                btn.textContent = orig;
                btn.classList.remove('simg-copy-btn-ok');
            }}, 800);
        }};
        if (navigator.clipboard) {{
            navigator.clipboard.writeText(v).then(ok).catch(function(err) {{
                console.warn('clipboard.writeText failed', err);
                el.select();
                document.execCommand('copy');
                ok();
            }});
        }} else {{
            el.select();
            document.execCommand('copy');
            ok();
        }}
        """.replace('\n', ' ').replace('"', '&quot;')
        safe_label = html_lib.escape(label, quote=True)
        return (
            f'<button type="button" class="simg-copy-btn" onclick="{js}">{safe_label}</button>'
        )

    @staticmethod
    def _html_clear_button(target_elem_id: str, label: str = 'clear') -> str:
        """
        Clears the value of the element with id `target_elem_id` (an <input>
        or <textarea>) in the DOM only — does NOT save. Marks the wrapping
        `.simg-edit-field` as stale so the user knows the field diverges
        from the persisted value.
        """
        js = f"""
        event.stopPropagation();
        const el = document.getElementById('{target_elem_id}');
        if (!el) {{ return; }}
        el.value = '';
        const field = el.closest('.simg-edit-field');
        if (field) {{ field.classList.add('simg-stale'); }}
        const btn = event.currentTarget;
        const orig = btn.textContent;
        btn.textContent = 'cleared';
        btn.classList.add('simg-copy-btn-ok');
        setTimeout(function() {{
            btn.textContent = orig;
            btn.classList.remove('simg-copy-btn-ok');
        }}, 600);
        """.replace('\n', ' ').replace('"', '&quot;')
        safe_label = html_lib.escape(label, quote=True)
        return (
            f'<button type="button" class="simg-copy-btn" onclick="{js}">{safe_label}</button>'
        )

    @staticmethod
    def _html_copy_static_button(value: Optional[str], label: str = 'copy') -> str:
        """
        Small copy-to-clipboard button that copies a fixed string value (no
        dependency on a DOM input element).
        """
        if value is None:
            value = ''
        # Escape value for embedding in a JS single-quoted string literal.
        value_js = (
            value.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n').replace('\r', '')
        )
        js = f"""
        event.stopPropagation();
        const v = '{value_js}';
        const ok = function() {{
            const btn = event.currentTarget;
            const orig = btn.textContent;
            btn.textContent = 'copied';
            btn.classList.add('simg-copy-btn-ok');
            setTimeout(function() {{
                btn.textContent = orig;
                btn.classList.remove('simg-copy-btn-ok');
            }}, 800);
        }};
        if (navigator.clipboard) {{
            navigator.clipboard.writeText(v).then(ok).catch(function(err) {{
                console.warn('clipboard.writeText failed', err);
                const ta = document.createElement('textarea');
                ta.value = v; document.body.appendChild(ta);
                ta.select(); document.execCommand('copy');
                document.body.removeChild(ta); ok();
            }});
        }} else {{
            const ta = document.createElement('textarea');
            ta.value = v; document.body.appendChild(ta);
            ta.select(); document.execCommand('copy');
            document.body.removeChild(ta); ok();
        }}
        """.replace('\n', ' ').replace('"', '&quot;')
        safe_label = html_lib.escape(label, quote=True)
        return (
            f'<button type="button" class="simg-copy-btn" onclick="{js}">{safe_label}</button>'
        )

    @staticmethod
    def _html_prototype_checkbox(img_id: str, checked: bool) -> str:
        """
        Per-image 'prototype' toggle.

        Toggling on  -> dispatches `set_prototype(True)` to the image.
        Toggling off -> dispatches `set_prototype(False)` to the image.
        """
        elem_id_btn = AppHtml.elem_id_cmd_button()
        elem_id_bus = AppHtml.elem_id_cmd_databus()

        skel_on = json.dumps({
            'type': 'image', 'id': img_id, 'cmd': 'db_query',
            'payload': {'set_prototype': True},
            'label': 'prototype',
        })
        skel_off = json.dumps({
            'type': 'image', 'id': img_id, 'cmd': 'db_query',
            'payload': {'set_prototype': False},
            'label': 'prototype',
        })

        js = f"""
        event.stopPropagation();
        const isOn = event.currentTarget.checked;
        const skel = JSON.parse(isOn ? '{skel_on}' : '{skel_off}');
        const bus = document.querySelector('#{elem_id_bus} textarea');
        if (bus) {{
            bus.value = JSON.stringify(skel);
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
        const trig = document.getElementById('{elem_id_btn}');
        if (trig) {{ trig.click(); }}
        """.replace('\n', ' ').replace('"', '&quot;')

        cb_id = f'simg-prototype-{img_id}'
        checked_attr = ' checked' if checked else ''
        return (
            f'<label class="simg-prototype-toggle" for="{cb_id}">'
            f'<input type="checkbox" id="{cb_id}"{checked_attr} onchange="{js}">'
            f'prototype</label>'
        )

    @staticmethod
    def _html_goto_scene_button(scene_id: Optional[str]) -> str:
        """
        Small button: navigates to the Scene Editor with the given scene
        loaded. Mirrors `AppSceneCell._html_thumb_onclick_js` (writes
        scene_id to the simg-editor databus, clicks the hidden trigger,
        and switches the outer tab). Renders a disabled button when
        `scene_id` is falsy.
        """
        elem_id_btn = AppHtml.elem_id_simg_editor_open_button()
        elem_id_bus = AppHtml.elem_id_simg_editor_databus()

        if not scene_id:
            return (
                '<button type="button" class="simg-copy-btn" disabled '
                'title="no parent scene found">goto scene</button>'
            )

        sid_js = str(scene_id).replace('\\', '\\\\').replace("'", "\\'")
        js = (
            "event.stopPropagation();"
            f"const bus = document.querySelector('#{elem_id_bus} textarea');"
            f"if (bus) {{ bus.value = '{sid_js}';"
            f"bus.dispatchEvent(new Event('input', {{ bubbles: true }})); }}"
            f"const btn = document.getElementById('{elem_id_btn}');"
            "if (btn) { btn.click(); }"
            "const tabBtns = document.querySelectorAll('button[role=&quot;tab&quot;]');"
            "for (let i = 0; i < tabBtns.length; i++) {"
            "  const t = tabBtns[i];"
            "  if (t.textContent && t.textContent.trim() === 'Scene Editor') {"
            "    t.click(); break;"
            "  }"
            "}"
        ).replace('"', '&quot;')
        return (
            f'<button type="button" class="simg-copy-btn" onclick="{js}">'
            f'goto scene</button>'
        )

    @staticmethod
    def _html_exclude_checkbox(set_id: str, img_id: str, checked: bool) -> str:
        """
        Per-image 'exclude' toggle for the Set Editor.

        Toggling on  -> dispatches `imgs_exclude_add([img_id])` to the set.
        Toggling off -> dispatches `imgs_exclude_del([img_id])` to the set.
        Both go through the cmd-bus `db_query` path.
        """
        elem_id_btn = AppHtml.elem_id_cmd_button()
        elem_id_bus = AppHtml.elem_id_cmd_databus()

        skel_add = json.dumps({
            'type': 'set', 'id': set_id, 'cmd': 'db_query',
            'payload': {'imgs_exclude_add': [img_id]},
            'label': 'exclude',
        })
        skel_del = json.dumps({
            'type': 'set', 'id': set_id, 'cmd': 'db_query',
            'payload': {'imgs_exclude_del': [img_id]},
            'label': 'exclude',
        })

        js = f"""
        event.stopPropagation();
        const isOn = event.currentTarget.checked;
        const skel = JSON.parse(isOn ? '{skel_add}' : '{skel_del}');
        const bus = document.querySelector('#{elem_id_bus} textarea');
        if (bus) {{
            bus.value = JSON.stringify(skel);
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
        const trig = document.getElementById('{elem_id_btn}');
        if (trig) {{ trig.click(); }}
        """.replace('\n', ' ').replace('"', '&quot;')

        cb_id = f'simg-exclude-{img_id}'
        checked_attr = ' checked' if checked else ''
        return (
            f'<label class="simg-exclude-toggle" for="{cb_id}">'
            f'<input type="checkbox" id="{cb_id}"{checked_attr} onchange="{js}">'
            f'exclude</label>'
        )

    @staticmethod
    def html_scene_exclude_checkbox(set_id: str, scene_id: str, checked: bool) -> str:
        """
        Per-scene 'exclude' toggle for the Set Editor's Scenes tab.

        Mirrors the per-image exclude toggle: same `simg-exclude-toggle`
        styling, label `exclude`. Stores/removes the scene id from the set's
        `scenes_exclude` list (no scene-label mutation).
        """
        elem_id_btn = AppHtml.elem_id_cmd_button()
        elem_id_bus = AppHtml.elem_id_cmd_databus()

        skel_add = json.dumps({
            'type': 'set', 'id': set_id, 'cmd': 'db_query',
            'payload': {'scenes_exclude_add': [scene_id]},
            'label': 'exclude',
        })
        skel_del = json.dumps({
            'type': 'set', 'id': set_id, 'cmd': 'db_query',
            'payload': {'scenes_exclude_del': [scene_id]},
            'label': 'exclude',
        })

        js = f"""
        event.stopPropagation();
        const isOn = event.currentTarget.checked;
        const skel = JSON.parse(isOn ? '{skel_add}' : '{skel_del}');
        const bus = document.querySelector('#{elem_id_bus} textarea');
        if (bus) {{
            bus.value = JSON.stringify(skel);
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
        const trig = document.getElementById('{elem_id_btn}');
        if (trig) {{ trig.click(); }}
        """.replace('\n', ' ').replace('"', '&quot;')

        cb_id = f'simg-scene-exclude-{scene_id}'
        checked_attr = ' checked' if checked else ''
        return (
            f'<label class="simg-exclude-toggle" for="{cb_id}">'
            f'<input type="checkbox" id="{cb_id}"{checked_attr} onchange="{js}">'
            f'exclude</label>'
        )

    @staticmethod
    def html_scene_info(scene: Scene) -> str:
        """
        Renders a small panel with scene-level rating + labels controls,
        wired through the existing cmd-bus (type='scene', cmd='db_query').
        """
        rating_html = ''
        for r in range(SceneDef.RATING_MIN, SceneDef.RATING_MAX + 1):
            checked = scene.rating == r
            rating_html += AppHtml.html_make_cmd_button(
                AppHtml.make_cmd_data(
                    'scene',
                    scene.id,
                    'db_query',
                    payload={'set_rating': r},
                    label=str(r),
                ),
                checked=checked,
            )

        labels_html = ''
        current_labels = scene.labels
        for label in editor_labels():
            checked = label in current_labels
            labels_html += AppHtml.html_make_cmd_button(
                AppHtml.make_cmd_data(
                    'scene',
                    scene.id,
                    'db_query',
                    payload={'switch_label': label},
                    label=label,
                ),
                checked=checked,
            )

        sets_html = ''
        for label in SceneDef.label_sets():
            checked = label in current_labels
            sets_html += AppHtml.html_make_cmd_button(
                AppHtml.make_cmd_data(
                    'scene',
                    scene.id,
                    'db_query',
                    payload={'switch_label': label},
                    label=label,
                ),
                checked=checked,
            )

        return f"""
        <div class="simg-scene-info">
            <div class="simg-edit-field">
                <label class="simg-edit-label">scene rating</label>
                <div class="operation-radio-group">
                    {rating_html}
                </div>
            </div>
            <div class="simg-edit-field">
                <label class="simg-edit-label">scene labels</label>
                <div class="operation-radio-group">
                    {labels_html}
                </div>
            </div>
            <div class="simg-edit-field">
                <label class="simg-edit-label">scene sets</label>
                <div class="operation-radio-group">
                    {sets_html}
                </div>
            </div>
        </div>
        """

    LIGHTBOX_OVERLAY_ID: str = 'simg-lightbox-overlay'
    LIGHTBOX_IMG_ID: str = 'simg-lightbox-img'
    LIGHTBOX_CAPTION_ID: str = 'simg-lightbox-caption'
    LIGHTBOX_PROTOTYPE_ID: str = 'simg-lightbox-prototype'
    LIGHTBOX_EXCLUDE_ID: str = 'simg-lightbox-exclude'
    LIGHTBOX_CONTENT_CLASS: str = 'simg-lightbox-content'

    @staticmethod
    def html_lightbox_modal() -> str:
        """
        Returns the HTML for the single shared full-size image lightbox.
        Embed once per editor view.

        Behaviour:
          - Hidden by default; shown by JS callback after the server returns
            the image base64 (and, for registered targets, the current
            caption + image id stored on the overlay's dataset).
          - Click on the overlay BACKGROUND -> if the overlay holds a
            registered image and the caption was edited, the value is
            persisted via the cmd-bus (`db_query` / set_caption) and then
            the modal closes.
          - Click on the 'X' close button -> closes WITHOUT saving.
          - Clicks on the image / textarea do NOT propagate so the modal
            stays open while the user views/edits.
        """
        overlay_id = AppSceneImageCell.LIGHTBOX_OVERLAY_ID
        img_id = AppSceneImageCell.LIGHTBOX_IMG_ID
        caption_id = AppSceneImageCell.LIGHTBOX_CAPTION_ID
        prototype_id = AppSceneImageCell.LIGHTBOX_PROTOTYPE_ID
        exclude_id = AppSceneImageCell.LIGHTBOX_EXCLUDE_ID
        content_cls = AppSceneImageCell.LIGHTBOX_CONTENT_CLASS

        cmd_btn_id = AppHtml.elem_id_cmd_button()
        cmd_bus_id = AppHtml.elem_id_cmd_databus()

        # ---- prototype toggle: persists immediately on change ------------
        prototype_change_js = (
            f"event.stopPropagation();"
            f"const o = document.getElementById('{overlay_id}');"
            f"if (!o || !o.dataset.imageId) {{ return; }}"
            f"const v = event.currentTarget.checked;"
            f"const data = {{ type: 'image', id: o.dataset.imageId,"
            f"  cmd: 'db_query', payload: {{ set_prototype: v }},"
            f"  label: 'prototype' }};"
            f"const cbus = document.querySelector('#{cmd_bus_id} textarea');"
            f"if (cbus) {{ cbus.value = JSON.stringify(data);"
            f"  cbus.dispatchEvent(new Event('input', {{ bubbles: true }})); }}"
            f"const cbtn = document.getElementById('{cmd_btn_id}');"
            f"if (cbtn) {{ cbtn.click(); }}"
        )

        # ---- exclude toggle (only active when modal carries a setId) -----
        exclude_change_js = (
            f"event.stopPropagation();"
            f"const o = document.getElementById('{overlay_id}');"
            f"if (!o || !o.dataset.imageId || !o.dataset.setId) {{ return; }}"
            f"const v = event.currentTarget.checked;"
            f"const setter = v ? 'imgs_exclude_add' : 'imgs_exclude_del';"
            f"const data = {{ type: 'set', id: o.dataset.setId,"
            f"  cmd: 'db_query', payload: {{}}, label: 'exclude' }};"
            f"data.payload[setter] = [o.dataset.imageId];"
            f"const cbus = document.querySelector('#{cmd_bus_id} textarea');"
            f"if (cbus) {{ cbus.value = JSON.stringify(data);"
            f"  cbus.dispatchEvent(new Event('input', {{ bubbles: true }})); }}"
            f"const cbtn = document.getElementById('{cmd_btn_id}');"
            f"if (cbtn) {{ cbtn.click(); }}"
        )

        # ---- close-only: X button ----------------------------------------
        # Just hide and clear all state, no DB write.
        close_js = (
            f"event.stopPropagation();"
            f"const o = document.getElementById('{overlay_id}');"
            f"const i = document.getElementById('{img_id}');"
            f"const c = document.getElementById('{caption_id}');"
            f"const p = document.getElementById('{prototype_id}');"
            f"const x = document.getElementById('{exclude_id}');"
            f"if (o) {{ o.style.display = 'none'; "
            f"o.dataset.targetType = ''; o.dataset.imageId = '';"
            f"o.dataset.setId = ''; }}"
            f"if (i) {{ i.src = ''; }}"
            f"if (c) {{ c.value = ''; }}"
            f"if (p) {{ p.checked = false; }}"
            f"if (x) {{ x.checked = false; }}"
        )

        # ---- save-and-close: clicking the overlay background -------------
        # When the modal currently shows a registered image, push a
        # cmd-bus payload to persist caption (set_caption + db_store) before
        # hiding. For unregistered images we just close.
        save_close_js = (
            f"event.stopPropagation();"
            f"const o = document.getElementById('{overlay_id}');"
            f"const i = document.getElementById('{img_id}');"
            f"const c = document.getElementById('{caption_id}');"
            f"if (o && o.dataset.targetType === 'registered' && o.dataset.imageId) {{"
            f"  const v = c ? c.value : '';"
            f"  const data = {{ type: 'image', id: o.dataset.imageId,"
            f"    cmd: 'db_query', payload: {{ set_caption: v }}, label: 'caption' }};"
            f"  const cbus = document.querySelector('#{cmd_bus_id} textarea');"
            f"  if (cbus) {{ cbus.value = JSON.stringify(data);"
            f"    cbus.dispatchEvent(new Event('input', {{ bubbles: true }})); }}"
            f"  const cbtn = document.getElementById('{cmd_btn_id}');"
            f"  if (cbtn) {{ cbtn.click(); }}"
            f"}}"
            f"if (o) {{ o.style.display = 'none'; "
            f"o.dataset.targetType = ''; o.dataset.imageId = '';"
            f"o.dataset.setId = ''; }}"
            f"if (i) {{ i.src = ''; }}"
            f"if (c) {{ c.value = ''; }}"
            f"const p2 = document.getElementById('{prototype_id}');"
            f"if (p2) {{ p2.checked = false; }}"
            f"const x2 = document.getElementById('{exclude_id}');"
            f"if (x2) {{ x2.checked = false; }}"
        )

        # The textarea also gets stopPropagation on keystrokes so e.g. Esc
        # / arrow keys typed during editing don't bubble up unexpectedly.
        textarea_keydown_js = "event.stopPropagation();"

        return f"""
        <style>
            #{overlay_id} {{
                display: none;
                position: fixed;
                z-index: 10000;
                left: 0;
                top: 0;
                width: 100vw;
                height: 100vh;
                background-color: rgba(0,0,0,0.92);
                justify-content: center;
                align-items: center;
            }}
            .{content_cls} {{
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: 16px;
                max-width: 100vw;
                max-height: 100vh;
            }}
            #{img_id} {{
                max-width: 100vw;
                max-height: 100vh;
                object-fit: contain;
                cursor: zoom-out;
            }}
            .{content_cls}.simg-lightbox-with-caption #{img_id} {{
                /* leave room to the right for the caption textarea */
                max-width: calc(100vw - 540px);
                max-height: 100vh;
            }}
            #{caption_id} {{
                display: none;
                width: 500px;
                height: min(80vh, 700px);
                padding: 8px 12px;
                background-color: #1f1f1f;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                font-family: inherit;
                font-size: 0.95em;
                resize: none;
            }}
            #{caption_id}:focus {{
                outline: none;
                border-color: #4CAF50;
                box-shadow: 0 0 0 1px #4CAF50;
            }}
            .{content_cls}.simg-lightbox-with-caption #{caption_id} {{
                display: block;
            }}
            #simg-lightbox-close {{
                position: absolute;
                top: 12px;
                right: 24px;
                color: #f1f1f1;
                font-size: 36px;
                font-weight: bold;
                cursor: pointer;
                user-select: none;
                z-index: 10001;
                line-height: 1;
            }}
            #simg-lightbox-close:hover {{
                color: #bbb;
            }}
            #{overlay_id} .simg-lightbox-toggles {{
                position: absolute;
                top: 16px;
                left: 24px;
                z-index: 10001;
                display: flex;
                gap: 8px;
            }}
            #{overlay_id} .simg-lightbox-prototype-toggle,
            #{overlay_id} .simg-lightbox-exclude-toggle {{
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 5px 10px;
                border: 1px solid #777;
                border-radius: 5px;
                font-size: 0.9em;
                color: #ffffff;
                background-color: rgba(40,40,40,0.85);
                cursor: pointer;
                user-select: none;
                line-height: 1;
            }}
            #{overlay_id} .simg-lightbox-prototype-toggle:hover,
            #{overlay_id} .simg-lightbox-exclude-toggle:hover {{
                background-color: rgba(70,70,70,0.95);
            }}
            #{overlay_id} .simg-lightbox-prototype-toggle input[type="checkbox"],
            #{overlay_id} .simg-lightbox-exclude-toggle input[type="checkbox"] {{
                margin: 0;
                cursor: pointer;
            }}
            .simg-edit-cell img,
            .simg-unreg-cell img {{
                cursor: zoom-in;
            }}
        </style>
        <div id="{overlay_id}" onclick="{save_close_js}">
            <span id="simg-lightbox-close" onclick="{close_js}">&times;</span>
            <div class="simg-lightbox-toggles" onclick="event.stopPropagation();">
                <label class="simg-lightbox-prototype-toggle"
                       for="{prototype_id}"
                       onclick="event.stopPropagation();">
                    <input type="checkbox" id="{prototype_id}"
                           onclick="event.stopPropagation();"
                           onchange="{prototype_change_js}">
                    prototype
                </label>
                <label class="simg-lightbox-exclude-toggle"
                       for="{exclude_id}"
                       onclick="event.stopPropagation();"
                       style="display:none;">
                    <input type="checkbox" id="{exclude_id}"
                           onclick="event.stopPropagation();"
                           onchange="{exclude_change_js}">
                    exclude
                </label>
            </div>
            <div class="{content_cls}">
                <img id="{img_id}" src="" alt="Full Size Image">
                <textarea id="{caption_id}" placeholder="caption"
                          onclick="event.stopPropagation();"
                          onkeydown="{textarea_keydown_js}"></textarea>
            </div>
        </div>
        """

    @staticmethod
    def _html_lightbox_onclick(
        target_type: str,
        target: str,
        set_id: Optional[str] = None,
    ) -> str:
        """
        Returns a JS snippet (suitable for embedding in an HTML attribute)
        that pushes a JSON `{type, target, set_id?}` payload into the
        lightbox in-bus and clicks the hidden lightbox trigger button. The
        Python handler + JS .then() callback will populate and show the
        lightbox modal.
        """
        elem_id_btn = AppHtml.elem_id_simg_editor_lightbox_button()
        elem_id_bus = AppHtml.elem_id_simg_editor_lightbox_databus()

        payload_obj: dict = {'type': target_type, 'target': target}
        if set_id:
            payload_obj['set_id'] = set_id
        payload = json.dumps(payload_obj)
        # Escape for embedding in a single-quoted JS string literal
        # (\ -> \\ , ' -> \').
        payload_js = payload.replace('\\', '\\\\').replace("'", "\\'")

        js = (
            f"event.stopPropagation();"
            f"const bus = document.querySelector('#{elem_id_bus} textarea');"
            f"if (bus) {{ bus.value = '{payload_js}';"
            f"bus.dispatchEvent(new Event('input', {{ bubbles: true }})); }}"
            f"const btn = document.getElementById('{elem_id_btn}');"
            f"if (btn) {{ btn.click(); }}"
        ).replace('"', '&quot;')
        return js

    @staticmethod
    def _html_set_button(obj_id: str) -> str:
        """
        'set' button (lives in the caption field's header).

        Behaviour:
          - If the caption_joy textarea has non-empty content, copy it into
            the caption textarea (DOM-only, not persisted).
          - Otherwise, ask the backend to generate a caption via JoySceneDB
            (default trigger). The result is then written into BOTH the
            caption_joy and caption textareas. The user can save explicitly.
        """
        elem_id_btn = AppHtml.elem_id_simg_editor_set_button()
        elem_id_bus_in = AppHtml.elem_id_simg_editor_set_databus()
        cj_id = f'simg-set_caption_joy-{obj_id}'
        c_id = f'simg-set_caption-{obj_id}'

        js = f"""
        event.stopPropagation();
        const cj = document.getElementById('{cj_id}');
        const c = document.getElementById('{c_id}');
        if (!c) {{ return; }}
        const cjVal = cj ? cj.value : '';
        if (cjVal && cjVal.trim().length > 0) {{
            c.value = cjVal;
            const btn = event.currentTarget;
            const orig = btn.textContent;
            btn.textContent = 'set';
            btn.classList.add('simg-copy-btn-ok');
            setTimeout(function() {{
                btn.textContent = orig;
                btn.classList.remove('simg-copy-btn-ok');
            }}, 800);
            return;
        }}
        const bus = document.querySelector('#{elem_id_bus_in} textarea');
        if (bus) {{
            bus.value = '{obj_id}';
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
        const trig = document.getElementById('{elem_id_btn}');
        if (trig) {{ trig.click(); }}
        """.replace('\n', ' ').replace('"', '&quot;')
        return f'<button type="button" class="simg-set-btn" onclick="{js}">set</button>'

    @staticmethod
    def _html_caption_button(
        target_type: str,
        target: str,
        trigger: str,
        label: Optional[str] = None,
        clip_only: bool = False,
    ) -> str:
        """
        Renders a button which, when clicked, asks the backend to caption the
        given target (registered SceneImage id or unregistered file url) using
        the given trigger.

        When `clip_only=True`, the backend skips persistence (no caption_joy
        write, no non-empty-caption_joy guard) and only copies the result to
        the clipboard.
        """
        if not label:
            label = f'caption {trigger}'

        elem_id_btn = AppHtml.elem_id_simg_editor_caption_button()
        elem_id_bus = AppHtml.elem_id_simg_editor_caption_databus()
        skeleton_json = json.dumps(
            {
                'type': target_type,
                'target': target,
                'trigger': trigger,
                'clip_only': bool(clip_only),
            }
        )

        js = f"""
        event.stopPropagation();
        const skel = JSON.parse('{skeleton_json}');
        const bus = document.querySelector('#{elem_id_bus} textarea');
        if (bus) {{
            bus.value = JSON.stringify(skel);
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
        const trig = document.getElementById('{elem_id_btn}');
        if (trig) {{ trig.click(); }}
        """.replace('\n', ' ').replace('"', '&quot;')

        safe_label = html_lib.escape(label, quote=True)
        return f'<button type="button" class="simg-caption-btn" onclick="{js}">{safe_label}</button>'

    @staticmethod
    def html_unregistered_cell(url: Path) -> str:
        """
        Renders a single 'unregistered image' cell with a Register button.

        The Register button puts the file path into the register databus and
        triggers the hidden register-button click; the backend then registers
        the file via the SceneImageManager and refreshes the editor.
        """
        pil = AppSceneImageCell._load_thumb_from_url(url)
        img_b64 = HtmlHelper.pil_to_base64(pil) or ''

        elem_id_btn = AppHtml.elem_id_simg_editor_register_button()
        elem_id_bus = AppHtml.elem_id_simg_editor_register_databus()
        elem_id_btn_p = AppHtml.elem_id_simg_editor_register_prototype_button()
        elem_id_bus_p = AppHtml.elem_id_simg_editor_register_prototype_databus()

        # JS uses single quotes only so it survives embedding inside onclick="..."
        url_str = str(url)
        # url_str is a filesystem path; escape any single quotes for JS literal
        url_js = url_str.replace('\\', '\\\\').replace("'", "\\'")
        onclick_js = (
            f"event.stopPropagation();"
            f"const cell = event.currentTarget.closest('.image-item');"
            f"if (cell) {{ cell.classList.add('simg-stale'); }}"
            f"const bus = document.querySelector('#{elem_id_bus} textarea');"
            f"if (bus) {{ bus.value = '{url_js}';"
            f"bus.dispatchEvent(new Event('input', {{ bubbles: true }})); }}"
            f"const btn = document.getElementById('{elem_id_btn}');"
            f"if (btn) {{ btn.click(); }}"
        ).replace('"', '&quot;')
        onclick_js_p = (
            f"event.stopPropagation();"
            f"const cell = event.currentTarget.closest('.image-item');"
            f"if (cell) {{ cell.classList.add('simg-stale'); }}"
            f"const bus = document.querySelector('#{elem_id_bus_p} textarea');"
            f"if (bus) {{ bus.value = '{url_js}';"
            f"bus.dispatchEvent(new Event('input', {{ bubbles: true }})); }}"
            f"const btn = document.getElementById('{elem_id_btn_p}');"
            f"if (btn) {{ btn.click(); }}"
        ).replace('"', '&quot;')

        safe_name = html_lib.escape(url.name, quote=True)
        safe_path = html_lib.escape(url_str, quote=True)
        url_copy_btn = AppSceneImageCell._html_copy_static_button(url_str, label='url')

        # Extract the embedded prompt from the image (if any). When no prompt
        # can be extracted, fall back to the file url as the value to copy.
        prompt = AppSceneImageCell._extract_prompt_from_url(url)
        prompt_value = prompt if prompt else url_str
        prompt_copy_btn = AppSceneImageCell._html_copy_static_button(
            prompt_value, label='prompt'
        )

        caption_btn = AppSceneImageCell._html_caption_button(
            target_type='unregistered',
            target=url_str,
            trigger='gts_prompter',
            label='caption gts_prompter',
        )
        thumb_onclick = AppSceneImageCell._html_lightbox_onclick(
            target_type='unregistered', target=url_str
        )
        return f"""
        <div class="image-item simg-unreg-cell">
            <img src="data:image/png;base64,{img_b64}" onclick="{thumb_onclick}">
            <div class="image-controls">
                <div class="simg-edit-id-row">
                    <div class="simg-edit-id" title="{safe_path}">{safe_name}</div>
                    {url_copy_btn}
                </div>
                <div class="simg-unreg-actions">
                    {prompt_copy_btn}
                    {caption_btn}
                    <button type="button" class="simg-register-btn" onclick="{onclick_js}">
                        register
                    </button>
                    <button type="button" class="simg-register-btn simg-register-prototype-btn"
                            onclick="{onclick_js_p}">
                        register prototype
                    </button>
                </div>
            </div>
        </div>
        """

    @staticmethod
    def _extract_prompt_from_url(url: Path) -> Optional[str]:
        """
        Tries to extract the generation prompt embedded in the image's PNG
        metadata. Returns None when no prompt could be recovered.
        """
        try:
            pil = image_from_url(url)
            if pil is None:
                return None
            pil.load()
            info_ext = getattr(pil, 'info', {}) or {}
            return _image_extract_prompt_from_info_ext(info_ext, verbose=False)
        except Exception as e:
            print(f'WARN: prompt extract from {url} failed: {e}')
            return None

    @staticmethod
    def _load_thumb_from_url(url: Path) -> Optional[PILImage.Image]:
        try:
            pil = image_from_url(url)
        except Exception:
            return None
        if pil is None:
            return None
        try:
            pil.thumbnail((AppSceneImageCell.THUMB_MAX_SIDE, AppSceneImageCell.THUMB_MAX_SIDE))
        except Exception:
            pass
        return pil

    @staticmethod
    def html_styles() -> str:
        """
        Optional extra styles for the SceneImage editor cells. Inserted once
        in the editor section. The base `image-grid` / `image-item` styles
        come from AppHtml.html_styled_cells_grid.
        """
        return """
        <style>
            .simg-edit-id {
                font-size: 0.75em;
                color: #aaaaaa;
                word-break: break-all;
                flex: 1 1 auto;
                text-align: left;
            }
            .simg-edit-id-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 6px;
                margin-bottom: 4px;
            }
            .simg-unreg-actions {
                display: flex;
                gap: 6px;
                flex-wrap: wrap;
                justify-content: center;
                margin-top: 4px;
            }
            .simg-edit-field {
                margin-top: 8px;
                text-align: left;
                padding: 0 4px;
            }
            .simg-edit-label {
                display: block;
                font-size: 0.75em;
                color: #cccccc;
                margin-bottom: 2px;
            }
            .simg-edit-textarea,
            .simg-edit-input {
                width: 100%;
                box-sizing: border-box;
                background-color: #222222;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 0.8em;
                font-family: inherit;
                resize: vertical;
            }
            .simg-edit-textarea:focus,
            .simg-edit-input:focus {
                outline: none;
                border-color: #4CAF50;
                box-shadow: 0 0 0 1px #4CAF50;
            }
            .simg-scene-info {
                background-color: #2a2a2a;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 8px 10px;
                margin: 8px 0;
                color: #ffffff;
            }
            /* Copy / save / register / caption / set buttons share the
               look-and-feel of selectable labels in
               `.operation-radio-group label`. */
            .simg-copy-btn,
            .simg-save-btn,
            .simg-register-btn,
            .simg-caption-btn,
            .simg-set-btn {
                padding: 5px 8px;
                border: 1px solid #ccc;
                border-radius: 5px;
                cursor: pointer;
                font-size: 0.8em;
                transition: all 0.2s ease;
                background-color: #555555;
                color: #ffffff;
                font-family: inherit;
                line-height: 1;
            }
            .simg-copy-btn:hover,
            .simg-save-btn:hover,
            .simg-register-btn:hover,
            .simg-caption-btn:hover,
            .simg-set-btn:hover {
                background-color: #777777;
            }
            /* Cells whose backend state has likely diverged from what is
               rendered (e.g. register was clicked but the editor has not
               been reloaded yet). Cleared on the next full editor render. */
            .image-item.simg-stale {
                outline: 3px solid #2563eb;
                outline-offset: -3px;
            }
            /* Editable text fields whose textarea/input value has been
               edited but not yet saved. Cleared by the save button JS. */
            .simg-edit-field.simg-stale {
                outline: 2px solid #2563eb;
                outline-offset: 2px;
                border-radius: 4px;
            }
            .simg-cell-actions {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                justify-content: center;
                margin-top: 8px;
            }
            .simg-copy-btn-ok,
            .simg-copy-btn-ok:hover {
                background-color: #4CAF50;
                color: #ffffff;
                border-color: #4CAF50;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            }
            .simg-edit-field-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 6px;
                margin-bottom: 2px;
            }
            .simg-edit-field-header .simg-edit-label {
                margin-bottom: 0;
            }
            .simg-edit-field-actions {
                display: flex;
                gap: 4px;
                align-items: center;
            }
            .simg-edit-toggles {
                display: flex;
                justify-content: center;
                gap: 6px;
                padding: 6px 4px 4px 4px;
            }
            .simg-exclude-toggle,
            .simg-prototype-toggle {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 3px 6px;
                border: 1px solid #ccc;
                border-radius: 5px;
                font-size: 0.75em;
                color: #ffffff;
                background-color: #555555;
                cursor: pointer;
                user-select: none;
                line-height: 1;
            }
            .simg-exclude-toggle:hover,
            .simg-prototype-toggle:hover {
                background-color: #777777;
            }
            .simg-exclude-toggle input[type="checkbox"],
            .simg-prototype-toggle input[type="checkbox"] {
                margin: 0;
                cursor: pointer;
            }
            /* ---- left-aligned thumbnail + labels_ng panel ---- */
            /* Higher specificity (.image-item.simg-edit-cell) so these
               override `.image-item { text-align: center }` and
               `.image-item img { margin: 0 auto }` regardless of the
               order in which the two style blocks are emitted. */
            .image-item.simg-edit-cell {
                text-align: left;
            }
            .image-item.simg-edit-cell .simg-edit-image-row {
                display: flex;
                align-items: flex-start;
                gap: 10px;
                padding: 5px;
            }
            .image-item.simg-edit-cell .simg-edit-image-row img {
                margin: 0;
                padding: 0;
                flex: 0 0 auto;
                border-bottom: none;
            }
            /* Image column: thumbnail stacked vertically with the hints
               field directly below it. The column is fixed-width
               (matches the thumbnail) so the labels_ng panel beside it
               keeps a sensible flex share. */
            .image-item.simg-edit-cell .simg-edit-image-col {
                flex: 0 0 auto;
                display: flex;
                flex-direction: column;
                gap: 4px;
                width: auto;
            }
            .image-item.simg-edit-cell .simg-edit-image-col .simg-edit-field {
                margin-top: 0;
                padding: 0;
            }
            /* Inside the image column the prototype/exclude toggles should
               left-align with the image, not center under it. */
            .image-item.simg-edit-cell .simg-edit-image-col .simg-edit-toggles {
                justify-content: flex-start;
                padding: 4px 0 2px 0;
            }
            /* Rating row sits in the image column under the hints; the
               buttons should left-align like the other controls there. */
            .image-item.simg-edit-cell .simg-edit-image-col .simg-edit-rating .operation-radio-group {
                justify-content: flex-start;
            }
            /* url / url scene / goto scene buttons sit under the rating. */
            .image-item.simg-edit-cell .simg-edit-image-col-links {
                display: flex;
                flex-wrap: wrap;
                gap: 4px;
                padding: 4px 0 2px 0;
            }
            .simg-edit-labels-ng {
                flex: 1 1 auto;
                font-size: 0.75em;
                color: #cccccc;
                min-width: 0;          /* allow flex item to shrink */
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .simg-labels-ng-block {
                border: 1px solid #555555;
                border-radius: 6px;
                background-color: #2a2a2a;
                padding: 4px 6px 6px 6px;
                display: flex;
                flex-direction: column;
                gap: 4px;
            }
            .simg-labels-ng-title {
                font-size: 0.85em;
                font-weight: 600;
                color: #ffffff;
                padding: 1px 0 2px 2px;
            }
            .simg-labels-ng-group {
                border: 1px solid #444444;
                border-radius: 4px;
                background-color: #1f1f1f;
                padding: 4px 6px;
                display: flex;
                flex-direction: column;
                gap: 4px;
            }
            .simg-labels-ng-group-title {
                font-size: 0.7em;
                color: #aaaaaa;
                text-align: left;
                text-transform: lowercase;
                letter-spacing: 0.02em;
            }
            /* Inside an ng-group the buttons should pack tight from the left
               (the global `.operation-radio-group` rule centers them). */
            .simg-labels-ng-group .operation-radio-group {
                justify-content: flex-start;
            }
            .simg-labels-ng-empty {
                color: #888888;
                font-style: italic;
            }
            .simg-labels-ng-error {
                color: #cc6666;
            }
        </style>
        """
