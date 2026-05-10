import html as html_lib

from aidb.app.cell_scene_image import editor_labels
from aidb.app.html import AppHtml, AppOpMmode, HtmlHelper
from aidb.scene import Scene, SceneDef

from ait.tools.images import image_from_url


class AppSceneCell:
    """
    A helper class to encapsulate the HTML generation logic for a single scene cell
    in the Gradio grid display.
    """

    @staticmethod
    def html(
        obj: Scene,
        mode: AppOpMmode,
        extras_below_image: str = '',
    ) -> str:
        """
        Generates the HTML string for a single scene cell.

        Args:
            scene: The Scene object for which to generate the cell.
            mode: e.g info, rate, label ...
            extras_below_image: optional HTML inserted directly below the
                thumbnail (centered) and above the operation block.

        Returns:
            str: The HTML string for the scene cell.
        """
        grid_img_base64 = HtmlHelper.pil_to_base64(image_from_url(obj.url_thumbnail))
        if grid_img_base64 is None:
            grid_img_base64 = ''
            print(
                f'Warning: No thumbnail available for image ID: {obj.id}. Displaying empty image.'
            )

        onclick_js = AppSceneCell._html_thumb_onclick_js(obj.id)
        extras_html = ''
        if extras_below_image:
            extras_html = (
                f'<div class="scene-cell-extras">{extras_below_image}</div>'
            )
        cell_classes = 'image-item'
        try:
            if obj.is_prototype:
                cell_classes += ' scene-cell-prototype'
        except Exception:
            pass
        return f"""
        <div class="{cell_classes}" id="cell-scene-{obj.id}">
            <div class="scene-cell-top">
                <img src="data:image/png;base64,{grid_img_base64}" onclick="{onclick_js}">
                {extras_html}
            </div>
            <div class="image-controls">
                {AppSceneCell.html_operation(obj, mode)}
            </div>
        </div>
        """

    @staticmethod
    def _html_thumb_onclick_js(scene_id: str) -> str:
        """
        JS run when a scene thumbnail is clicked: writes the scene id into the
        SceneImage editor databus, fires the hidden trigger button (which makes
        the backend render the editor cells), and switches to the editor tab.
        """
        elem_id_btn = AppHtml.elem_id_simg_editor_open_button()
        elem_id_bus = AppHtml.elem_id_simg_editor_databus()
        # Use single-quoted JS strings so we don't have to escape double quotes
        # for the surrounding HTML attribute. Newlines get squashed at the end.
        js = f"""
        event.stopPropagation();
        const bus = document.querySelector('#{elem_id_bus} textarea');
        if (bus) {{
            bus.value = '{scene_id}';
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
        const btn = document.getElementById('{elem_id_btn}');
        if (btn) {{ btn.click(); }}
        const tabBtns = document.querySelectorAll('button[role=&quot;tab&quot;]');
        for (let i = 0; i < tabBtns.length; i++) {{
            const t = tabBtns[i];
            if (t.textContent) {{
                if (t.textContent.trim() === 'Scene Editor') {{
                    t.click();
                    break;
                }}
            }}
        }}
        """.replace('\n', ' ').replace('"', '&quot;')
        return js

    @staticmethod
    def html_operation(
        obj: Scene,
        mode: AppOpMmode,
    ) -> str:
        html = ''
        extras = ''
        if mode == 'none':
            pass
        elif mode == 'info':
            html = AppSceneCell._html_op_info(obj)
            try:
                subdir = obj.url.parent.name
            except Exception:
                subdir = ''
            if subdir:
                safe = html_lib.escape(subdir, quote=True)
                extras = f'<div class="scene-cell-subdir">{safe}</div>'
        elif mode == 'rate':
            html = AppSceneCell._html_op_rate(obj)
        elif mode == 'label':
            html = AppSceneCell._html_op_label(obj)
        elif mode == 'set':
            html = AppSceneCell._html_op_set(obj)

        return f"""
                <div class="operation-radio-group">
                    {html}
                </div>
                {extras}
                """

    @staticmethod
    def _html_op_info(obj: Scene) -> str:
        fields = ['id', 'url', 'prompt', 'caption']

        html = ''
        for field in fields:
            html += AppHtml.html_make_cmd_button(
                AppHtml.make_cmd_data(
                    'scene',
                    obj.id,
                    'to_clipspace',
                    payload=field,
                    label=field,
                )
            )
        return html

    @staticmethod
    def _html_op_rate(obj: Scene) -> str:
        current_rating = obj.rating

        html = ''
        for r in range(SceneDef.RATING_MIN, SceneDef.RATING_MAX + 1):
            # new code
            checked = True if current_rating == r else False
            html += AppHtml.html_make_cmd_button(
                AppHtml.make_cmd_data(
                    'scene', obj.id, 'db_query', payload={'set_rating': r}, label=str(r)
                ),
                checked=checked,
            )
        html += '<br>'
        html += AppHtml.html_make_cmd_button(
            AppHtml.make_cmd_data('scene', obj.id, 'to_clipspace', payload='url', label='url')
        )
        return html

    @staticmethod
    def _html_op_label(obj: Scene) -> str:
        current_labels = obj.labels

        html = ''
        for label in editor_labels():
            checked = True if label in current_labels else False
            html += AppHtml.html_make_cmd_button(
                AppHtml.make_cmd_data(
                    'scene',
                    obj.id,
                    'db_query',
                    payload={'switch_label': label},
                    label=label,
                ),
                checked=checked,
                toggle=True,
            )
        return html

    @staticmethod
    def _html_op_set(obj: Scene) -> str:
        current_labels = obj.labels

        html = ''
        for label in SceneDef.label_sets():
            checked = True if label in current_labels else False
            html += AppHtml.html_make_cmd_button(
                AppHtml.make_cmd_data(
                    'scene',
                    obj.id,
                    'db_query',
                    payload={'switch_label': label},
                    label=label,
                ),
                checked=checked,
                toggle=True,
            )
        return html
