from aidb.app.html import AppHtml, AppOpMmode, HtmlHelper
from aidb.scene import Scene, SceneDef
from aidb.tagger_defines import TaggerDef

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
    ) -> str:
        """
        Generates the HTML string for a single scene cell.

        Args:
            scene: The Scene object for which to generate the cell.
            mode: e.g info, rate, label ...

        Returns:
            str: The HTML string for the scene cell.
        """
        grid_img_base64 = HtmlHelper.pil_to_base64(image_from_url(obj.url_thumbnail))
        if grid_img_base64 is None:
            grid_img_base64 = ''
            print(
                f'Warning: No thumbnail available for image ID: {obj.id}. Displaying empty image.'
            )

        return f"""
        <div class="image-item" id="cell-scene-{obj.id}">
            <img src="data:image/png;base64,{grid_img_base64}">
            <div class="image-controls">
                {AppSceneCell.html_operation(obj, mode)}
            </div>
        </div>
        """

    @staticmethod
    def html_operation(
        obj: Scene,
        mode: AppOpMmode,
    ) -> str:
        html = ''
        if mode == 'none':
            pass
        elif mode == 'info':
            html = AppSceneCell._html_op_info(obj)
        elif mode == 'rate':
            html = AppSceneCell._html_op_rate(obj)
        elif mode == 'label':
            html = AppSceneCell._html_op_label(obj)

        return f"""
                <div class="operation-radio-group">
                    {html}
                </div>
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
        for label in TaggerDef.LABELS['label']:
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
            )
        return html
