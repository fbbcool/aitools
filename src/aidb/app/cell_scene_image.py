import html as html_lib
import json
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage

from aidb.app.html import AppHtml, HtmlHelper
from aidb.scene import Scene, SceneDef
from aidb.scene.scene_image import SceneImage
from aidb.tagger_defines import TaggerDef

from ait.tools.images import image_from_url, _image_extract_prompt_from_info_ext


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
            with_save=False,
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
        with_save: bool = True,
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
                f'<textarea id="{elem_id}" class="simg-edit-textarea" rows="3">'
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

        return f"""
        <div class="simg-edit-field">
            <div class="simg-edit-field-header">
                <label class="simg-edit-label" for="{elem_id}">{label}</label>
                <div class="simg-edit-field-actions">
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

        # Extract the embedded prompt from the image (if any). When no prompt
        # can be extracted, fall back to the file url as the value to copy.
        prompt = AppSceneImageCell._extract_prompt_from_url(url)
        prompt_value = prompt if prompt else url_str
        prompt_copy_btn = AppSceneImageCell._html_copy_static_button(
            prompt_value, label='prompt'
        )
        return f"""
        <div class="image-item simg-unreg-cell">
            <img src="data:image/png;base64,{img_b64}">
            <div class="image-controls">
                <div class="simg-edit-id-row">
                    <div class="simg-edit-id" title="{safe_path}">{safe_name}</div>
                    {url_copy_btn}
                </div>
                <div class="simg-unreg-actions">
                    {prompt_copy_btn}
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
            /* Copy / save / register buttons share the look-and-feel of
               the selectable labels in `.operation-radio-group label`. */
            .simg-copy-btn,
            .simg-save-btn,
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
            .simg-save-btn:hover,
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
            .simg-edit-field-actions {
                display: flex;
                gap: 4px;
                align-items: center;
            }
        </style>
        """
