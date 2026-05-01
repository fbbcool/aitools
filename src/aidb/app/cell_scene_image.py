import html as html_lib
import json
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage

from aidb.app.html import AppHtml, HtmlHelper
from aidb.scene import Scene, SceneDef
from aidb.scene.scene_image import SceneImage

from ait.caption.joy import LABEL_PROMPT
from ait.tools.images import image_from_url, _image_extract_prompt_from_info_ext


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
    def html(obj: SceneImage) -> str:
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

        caption_btn_1xlasm = AppSceneImageCell._html_caption_button(
            target_type='registered',
            target=obj.id,
            trigger='1xlasm',
            label='caption 1xlasm',
        )
        caption_btn_gts = AppSceneImageCell._html_caption_button(
            target_type='registered',
            target=obj.id,
            trigger='gts_prompter',
            label='caption gts_prompter',
        )

        save_image_btn = AppSceneImageCell._html_save_image_button(obj)

        thumb_onclick = AppSceneImageCell._html_lightbox_onclick(
            target_type='registered', target=obj.id
        )

        return f"""
        <div class="image-item simg-edit-cell" id="cell-simg-{obj.id}">
            <img src="data:image/png;base64,{img_b64}" onclick="{thumb_onclick}">
            <div class="image-controls">
                {caption_field}
                <div class="simg-edit-id-row">
                    <div class="simg-edit-id">id: {obj.id}</div>
                    {url_copy_btn}
                </div>
                <div class="operation-radio-group">
                    {rating_html}
                </div>
                <div class="simg-edit-field">
                    <label class="simg-edit-label">labels</label>
                    <div class="operation-radio-group">
                        {labels_html}
                    </div>
                </div>
                {hints_field}
                {caption_joy_field}
                {prompt_field}
                <div class="simg-cell-actions">
                    {caption_btn_1xlasm}
                    {caption_btn_gts}
                </div>
                <div class="simg-cell-save">
                    {save_image_btn}
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

        if multiline:
            input_html = (
                f'<textarea id="{elem_id}" class="simg-edit-textarea" rows="{rows}">'
                f'{safe_value}</textarea>'
            )
        else:
            input_html = (
                f'<input type="text" id="{elem_id}" class="simg-edit-input" '
                f'value="{safe_value}">'
            )

        copy_btn_html = AppSceneImageCell._html_copy_button(elem_id)
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
        </div>
        """

    LIGHTBOX_OVERLAY_ID: str = 'simg-lightbox-overlay'
    LIGHTBOX_IMG_ID: str = 'simg-lightbox-img'
    LIGHTBOX_CAPTION_ID: str = 'simg-lightbox-caption'
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
        content_cls = AppSceneImageCell.LIGHTBOX_CONTENT_CLASS

        cmd_btn_id = AppHtml.elem_id_cmd_button()
        cmd_bus_id = AppHtml.elem_id_cmd_databus()

        # ---- close-only: X button ----------------------------------------
        # Just hide and clear all state, no DB write.
        close_js = (
            f"event.stopPropagation();"
            f"const o = document.getElementById('{overlay_id}');"
            f"const i = document.getElementById('{img_id}');"
            f"const c = document.getElementById('{caption_id}');"
            f"if (o) {{ o.style.display = 'none'; "
            f"o.dataset.targetType = ''; o.dataset.imageId = ''; }}"
            f"if (i) {{ i.src = ''; }}"
            f"if (c) {{ c.value = ''; }}"
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
            f"o.dataset.targetType = ''; o.dataset.imageId = ''; }}"
            f"if (i) {{ i.src = ''; }}"
            f"if (c) {{ c.value = ''; }}"
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
            .simg-edit-cell img,
            .simg-unreg-cell img {{
                cursor: zoom-in;
            }}
        </style>
        <div id="{overlay_id}" onclick="{save_close_js}">
            <span id="simg-lightbox-close" onclick="{close_js}">&times;</span>
            <div class="{content_cls}">
                <img id="{img_id}" src="" alt="Full Size Image">
                <textarea id="{caption_id}" placeholder="caption"
                          onclick="event.stopPropagation();"
                          onkeydown="{textarea_keydown_js}"></textarea>
            </div>
        </div>
        """

    @staticmethod
    def _html_lightbox_onclick(target_type: str, target: str) -> str:
        """
        Returns a JS snippet (suitable for embedding in an HTML attribute)
        that pushes a JSON `{type, target}` payload into the lightbox in-bus
        and clicks the hidden lightbox trigger button. The Python handler +
        JS .then() callback will populate and show the lightbox modal.
        """
        elem_id_btn = AppHtml.elem_id_simg_editor_lightbox_button()
        elem_id_bus = AppHtml.elem_id_simg_editor_lightbox_databus()

        payload = json.dumps({'type': target_type, 'target': target})
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
    def _html_save_image_button(obj: SceneImage) -> str:
        """
        Major 'save image' button. Reads the current values of all editable
        text fields on this cell (hints, caption, caption_joy) and persists
        them in a single DB update via the cmd-bus 'db_query_multi' cmd.
        """
        elem_id_btn = AppHtml.elem_id_cmd_button()
        elem_id_bus = AppHtml.elem_id_cmd_databus()

        h_id = f'simg-set_hints-{obj.id}'
        c_id = f'simg-set_caption-{obj.id}'
        cj_id = f'simg-set_caption_joy-{obj.id}'

        cmd_skeleton = {
            'type': 'image',
            'id': obj.id,
            'cmd': 'db_query_multi',
            'payload': {
                'set_hints': '__H__',
                'set_caption': '__C__',
                'set_caption_joy': '__CJ__',
            },
            'label': 'save',
        }
        skeleton_json = json.dumps(cmd_skeleton)

        js = f"""
        event.stopPropagation();
        const eh = document.getElementById('{h_id}');
        const ec = document.getElementById('{c_id}');
        const ecj = document.getElementById('{cj_id}');
        const skel = JSON.parse('{skeleton_json}');
        skel.payload['set_hints'] = eh ? eh.value : '';
        skel.payload['set_caption'] = ec ? ec.value : '';
        skel.payload['set_caption_joy'] = ecj ? ecj.value : '';
        const bus = document.querySelector('#{elem_id_bus} textarea');
        if (bus) {{
            bus.value = JSON.stringify(skel);
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
        const trig = document.getElementById('{elem_id_btn}');
        if (trig) {{ trig.click(); }}
        const btn = event.currentTarget;
        const orig = btn.textContent;
        btn.textContent = 'saved';
        btn.classList.add('simg-copy-btn-ok');
        setTimeout(function() {{
            btn.textContent = orig;
            btn.classList.remove('simg-copy-btn-ok');
        }}, 1000);
        """.replace('\n', ' ').replace('"', '&quot;')
        return f'<button type="button" class="simg-save-image-btn" onclick="{js}">save image</button>'

    @staticmethod
    def _html_caption_button(
        target_type: str,
        target: str,
        trigger: str,
        label: Optional[str] = None,
    ) -> str:
        """
        Renders a button which, when clicked, asks the backend to caption the
        given target (registered SceneImage id or unregistered file url) using
        the given trigger.

        The JS pushes a JSON payload `{type, target, trigger}` into the caption
        databus and triggers the hidden caption button. The backend handler
        runs the captioning, optionally stores results, and refreshes the
        editor.
        """
        if not label:
            label = f'caption {trigger}'

        elem_id_btn = AppHtml.elem_id_simg_editor_caption_button()
        elem_id_bus = AppHtml.elem_id_simg_editor_caption_databus()
        skeleton_json = json.dumps(
            {'type': target_type, 'target': target, 'trigger': trigger}
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

        # JS uses single quotes only so it survives embedding inside onclick="..."
        url_str = str(url)
        # url_str is a filesystem path; escape any single quotes for JS literal
        url_js = url_str.replace('\\', '\\\\').replace("'", "\\'")
        onclick_js = (
            f"event.stopPropagation();"
            f"const bus = document.querySelector('#{elem_id_bus} textarea');"
            f"if (bus) {{ bus.value = '{url_js}';"
            f"bus.dispatchEvent(new Event('input', {{ bubbles: true }})); }}"
            f"const btn = document.getElementById('{elem_id_btn}');"
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
            .simg-cell-save {
                display: flex;
                justify-content: center;
                margin-top: 10px;
            }
            .simg-save-image-btn {
                padding: 8px 16px;
                border: 1px solid #4CAF50;
                border-radius: 5px;
                cursor: pointer;
                font-size: 0.95em;
                font-weight: 600;
                background-color: #4CAF50;
                color: #ffffff;
                font-family: inherit;
                width: 100%;
                line-height: 1.2;
                transition: all 0.2s ease;
            }
            .simg-save-image-btn:hover {
                background-color: #5fbd62;
            }
            .simg-save-image-btn.simg-copy-btn-ok {
                background-color: #2e7d32 !important;
                border-color: #2e7d32 !important;
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
        </style>
        """
