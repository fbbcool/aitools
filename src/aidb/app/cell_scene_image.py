import html as html_lib
import json
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage

from aidb.app.html import AppHtml, HtmlHelper
from aidb.scene import Scene, SceneDef
from aidb.scene.scene_image import SceneImage
from aidb.tagger_defines import TaggerDef

from ait.tools.images import image_from_url


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
        caption_field = AppSceneImageCell._html_text_field(
            obj,
            attr_setter='set_caption',
            label='caption',
            value=obj.caption,
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
        )

        url = obj.url_from_data
        url_str = str(url) if url is not None else ''
        url_copy_btn = AppSceneImageCell._html_copy_static_button(url_str, label='url')

        return f"""
        <div class="image-item simg-edit-cell" id="cell-simg-{obj.id}">
            <img src="data:image/png;base64,{img_b64}">
            <div class="image-controls">
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
                {caption_field}
                {caption_joy_field}
                {prompt_field}
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
        for label in TaggerDef.LABELS['label']:
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
    ) -> str:
        """
        Renders a full editable text-field block:

            <div class="simg-edit-field">
                <div class="simg-edit-field-header">
                    <label>{label}</label>
                    <button class="simg-copy-btn">copy</button>
                </div>
                <textarea/input>
            </div>

        The copy button copies the textarea's *current* value (i.e. what the
        user sees, not necessarily what's saved) to the clipboard via the
        browser's clipboard API.
        """
        if value is None:
            value = ''

        # We use a simple JS hook on `change` (fires on blur for textareas/inputs).
        # The JS reads the current value, packages a cmd-data payload and dispatches
        # the cmd_run via the existing hidden cmd-button + databus.
        elem_id_btn = AppHtml.elem_id_cmd_button()
        elem_id_bus = AppHtml.elem_id_cmd_databus()

        # cmd skeleton; the actual value is filled in via JS at runtime.
        cmd_skeleton = {
            'type': 'image',
            'id': obj.id,
            'cmd': 'db_query',
            'payload': {attr_setter: '__VALUE__'},
            'label': label,
        }
        skeleton_json = json.dumps(cmd_skeleton)

        # Build JS that updates the cmd payload with the textarea's current value,
        # writes the JSON into the cmd databus, and clicks the hidden cmd button.
        onchange_js = (
            f"const v = this.value;"
            f"const skel = JSON.parse('{skeleton_json}');"
            f"skel.payload['{attr_setter}'] = v;"
            f"const bus = document.querySelector('#{elem_id_bus} textarea');"
            f"bus.value = JSON.stringify(skel);"
            f"bus.dispatchEvent(new Event('input', {{ bubbles: true }}));"
            f"document.getElementById('{elem_id_btn}').click();"
        ).replace('"', '&quot;')

        # Escape value for safe HTML embedding
        safe_value = html_lib.escape(value, quote=True)
        elem_id = f'simg-{attr_setter}-{obj.id}'

        if multiline:
            input_html = (
                f'<textarea id="{elem_id}" class="simg-edit-textarea" rows="3" '
                f'onchange="{onchange_js}">{safe_value}</textarea>'
            )
        else:
            input_html = (
                f'<input type="text" id="{elem_id}" class="simg-edit-input" '
                f'value="{safe_value}" onchange="{onchange_js}">'
            )

        copy_btn_html = AppSceneImageCell._html_copy_button(elem_id)

        return f"""
        <div class="simg-edit-field">
            <div class="simg-edit-field-header">
                <label class="simg-edit-label" for="{elem_id}">{label}</label>
                {copy_btn_html}
            </div>
            {input_html}
        </div>
        """

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
        for label in TaggerDef.LABELS['label']:
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
        return f"""
        <div class="image-item simg-unreg-cell">
            <img src="data:image/png;base64,{img_b64}">
            <div class="image-controls">
                <div class="simg-edit-id-row">
                    <div class="simg-edit-id" title="{safe_path}">{safe_name}</div>
                    {url_copy_btn}
                </div>
                <button type="button" class="simg-register-btn" onclick="{onclick_js}">
                    register
                </button>
            </div>
        </div>
        """

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
            /* Copy + register buttons share the look-and-feel of the
               selectable labels in `.operation-radio-group label`. */
            .simg-copy-btn,
            .simg-register-btn {
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
            .simg-register-btn:hover {
                background-color: #777777;
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
        </style>
        """
