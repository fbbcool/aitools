import html as html_lib
import json
from typing import Optional

from PIL import Image as PILImage

from aidb.app.html import AppHtml, HtmlHelper
from aidb.scene import SceneDef
from aidb.scene.scene_image import SceneImage

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
        caption_html = AppSceneImageCell._html_text_field(
            obj,
            attr_setter='set_caption',
            label='caption',
            value=obj.caption,
            multiline=True,
        )
        prompt_html = AppSceneImageCell._html_text_field(
            obj,
            attr_setter='set_prompt',
            label='prompt',
            value=obj.prompt,
            multiline=True,
        )

        return f"""
        <div class="image-item simg-edit-cell" id="cell-simg-{obj.id}">
            <img src="data:image/png;base64,{img_b64}">
            <div class="image-controls">
                <div class="simg-edit-id">id: {obj.id}</div>
                <div class="operation-radio-group">
                    {rating_html}
                </div>
                <div class="simg-edit-field">
                    <label class="simg-edit-label">caption</label>
                    {caption_html}
                </div>
                <div class="simg-edit-field">
                    <label class="simg-edit-label">prompt</label>
                    {prompt_html}
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
    def _html_text_field(
        obj: SceneImage,
        attr_setter: str,
        label: str,
        value: Optional[str],
        multiline: bool = True,
    ) -> str:
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
            return (
                f'<textarea id="{elem_id}" class="simg-edit-textarea" rows="3" '
                f'onchange="{onchange_js}">{safe_value}</textarea>'
            )
        return (
            f'<input type="text" id="{elem_id}" class="simg-edit-input" '
            f'value="{safe_value}" onchange="{onchange_js}">'
        )

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
                margin-bottom: 4px;
                word-break: break-all;
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
        </style>
        """
