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
        scene: Scene,
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
        grid_img_base64 = HtmlHelper.pil_to_base64(image_from_url(scene.url_thumbnail))
        if grid_img_base64 is None:
            grid_img_base64 = ''  # Or a base64 encoded placeholder image
            print(
                f'Warning: No thumbnail available for image ID: {scene.id}. Displaying empty image.'
            )

        return f"""
        <div class="image-item" id="cell-scene-{scene.id}">
            <img src="data:image/png;base64,{grid_img_base64}">
            <div class="image-controls">
                {AppSceneCell.html_operation(scene, mode)}
            </div>
        </div>
        """

    @staticmethod
    def html_operation(
        scene: Scene,
        mode: AppOpMmode,
    ) -> str:
        html = ''
        if mode == 'none':
            pass
        elif mode == 'info':
            html = AppSceneCell._html_op_info(scene)
        elif mode == 'rate':
            html = AppSceneCell._html_op_rate(scene)
        elif mode == 'label':
            html = AppSceneCell._html_op_label(scene)

        return f"""
                <div class="operation-radio-group">
                    {html}
                </div>
                """

    @staticmethod
    def _html_op_info(scene: Scene) -> str:
        fields = ['id', 'url', 'prompt', 'caption']

        html = ''
        for field in fields:
            html += AppHtml.cmd_make_button(
                AppHtml.cmd_make_data(
                    'scene',
                    scene.id,
                    'to_clipspace',
                    payload=field,
                    label=field,
                )
            )
        return html

    @staticmethod
    def _html_op_rate(scene: Scene) -> str:
        current_rating = scene.get_rating

        html = ''
        for r in range(SceneDef.RATING_MIN, SceneDef.RATING_MAX + 1):
            # new code
            checked = True if current_rating == r else False
            html += AppHtml.cmd_make_button(
                AppHtml.cmd_make_data('scene', scene.id, 'rating', payload=r, label=str(r)),
                checked=checked,
            )
        html += '<br>'
        html += AppHtml.cmd_make_button(
            AppHtml.cmd_make_data('scene', scene.id, 'to_clipspace', payload='url', label='url')
        )
        return html

    @staticmethod
    def _html_op_label(scene: Scene) -> str:
        current_labels = scene.get_labels

        html = ''
        for label in TaggerDef.LABELS['label']:
            checked = True if label in current_labels else False
            html += AppHtml.cmd_make_button(
                AppHtml.cmd_make_data(
                    'scene',
                    scene.id,
                    'label_swap',
                    payload=label,
                    label=label,
                ),
                checked=checked,
            )
        return html
