import base64
from io import BytesIO
from typing_extensions import Literal
from PIL import Image as PILImage

# import html
import gradio as gr

from aidb.app.html import AppHtml
from aidb.scene import Scene, SceneDef
from aidb.tagger_defines import TaggerDef

from ait.tools.images import image_from_url


class AppSceneCell:
    """
    A helper class to encapsulate the HTML generation logic for a single scene cell
    in the Gradio grid display for showing rating and contributing tags.
    The rating can be changed by clicking.
    """

    @staticmethod
    def make(
        scene: Scene,
        mode: Literal['rate', 'labels', 'none'],
        get_full_scene_data_trigger_id: str,
    ) -> str:
        """
        Generates the HTML string for a single scene cell.

        Args:
            image_obj (Scene): The Scene object for which to generate the cell.
            get_full_scene_data_trigger_id (str): The HTML ID of the hidden button to trigger modal data fetch.
            rating_update_trigger_id (str): The HTML ID of the hidden button to trigger rating update.

        Returns:
            str: The HTML string for the scene cell.
        """
        grid_thumb_pil = image_from_url(scene.url_thumbnail)

        if grid_thumb_pil is not None:
            grid_img_base64 = AppSceneCell._pil_to_base64(grid_thumb_pil)
        else:
            grid_img_base64 = ''  # Or a base64 encoded placeholder image
            print(
                f'Warning: No thumbnail available for image ID: {scene.id}. Displaying empty image.'
            )

        # Format contributing tags for display
        contributing_tags_html = ''
        # if scene.contributing_tags:
        #    contributing_tags_html = "<div class='tag-contribution'><strong>Tags:</strong><br>"
        #    for tag, prob in sorted(
        #        scene.contributing_tags, key=lambda x: x[1], reverse=True
        #    ):  # Sort contributing tags by probability
        #        contributing_tags_html += f'{html.escape(tag)}: {prob:.2f}<br>'
        #    contributing_tags_html += '</div>'

        # n0 = img.neighbor0
        # caption = f"Score: {img.score:.2f} ({img.image_id}, {n0[1]:.2f}->{n0[0]}) "
        caption = ''
        # tiny_info = []
        # if scene.caption is not None:
        #    tiny_info.append('C')
        # if scene.prompt is not None:
        #    tiny_info.append('P')
        # caption = f'Score: {scene.score:.2f} ({scene.id}) {"/".join(tiny_info)}'

        # The onclick for the image now also uses the data bus pattern.
        class_img = 'image-item'

        img_onclick_js = f"""
        const bus = document.querySelector('#image_id_bus_elem textarea');
        bus.value = '{scene.id}';
        bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        document.getElementById('{get_full_scene_data_trigger_id}').click();""".replace(
            '\n', ' '
        ).replace('"', '&quot;')

        return f"""
        <div class="{class_img}" id="image-{scene.id}">
            <img src="data:image/png;base64,{grid_img_base64}" alt="Image Preview" onclick="{img_onclick_js}">
            <div class="image-caption">{caption}</div>
            <div class="image-controls">
                {AppSceneCell.html_operation(scene, mode)}
            </div>
            {contributing_tags_html}
        </div>
        """

    @staticmethod
    def html_operation(
        scene: Scene,
        mode: Literal['rate', 'labels', 'none'],
    ) -> str:
        if mode is None:
            return ''
        elif mode == 'none':
            return ''
        elif mode == 'rate':
            return AppSceneCell._html_op_rate(scene)
        elif mode == 'labels':
            return AppSceneCell._html_op_labels(scene)

    @staticmethod
    def _html_op_rate(scene: Scene) -> str:
        current_rating = scene.get_rating

        operation_html = ''
        for r in range(SceneDef.RATING_MIN, SceneDef.RATING_MAX + 1):
            checked = 'checked' if current_rating == r else ''
            # if clicked it should immediatly highlight
            # The onclick event now uses a more robust pattern:
            # 1. Find the hidden 'data bus' textbox.
            # 2. Set its value to the 'image_id,rating' string.
            # 3. Dispatch an 'input' event so Gradio recognizes the change.
            # 4. Programmatically click the hidden trigger button.
            onclick_js = f"""
            event.stopPropagation();
            const bus = document.querySelector('#{AppHtml.make_elem_id_databus('rate')} textarea');
            bus.value = '{scene.id},{r}';
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
            document.getElementById('{AppHtml.make_elem_id_button_update('rate')}').click();""".replace(
                '\n', ' '
            ).replace('"', '&quot;')
            operation_html += f"""
                <input type="radio" id="rating-{scene.id}-{r}" name="rating-{scene.id}" value="{r}" {checked}
                       onclick="{onclick_js}">
                <label for="rating-{scene.id}-{r}" class="rating-label-btn">{r}</label>
                """

        return f"""
                <div class="rating-label">Rating:</div>
                <div class="operation-radio-group">
                    {operation_html}
                </div>
                """

    @staticmethod
    def _html_op_labels(scene: Scene) -> str:
        current_labels = scene.get_labels

        operation_html = ''
        for label in TaggerDef.LABELS['label']:
            checked = 'checked' if label in current_labels else ''
            add_del = '-' if label in current_labels else '+'
            # if clicked it should immediatly highlight
            # The onclick event now uses a more robust pattern:
            # 1. Find the hidden 'data bus' textbox.
            # 2. Set its value to the 'image_id,rating' string.
            # 3. Dispatch an 'input' event so Gradio recognizes the change.
            # 4. Programmatically click the hidden trigger button.
            onclick_js = f"""
            event.stopPropagation();
            const bus = document.querySelector('#{AppHtml.make_elem_id_databus('label')} textarea');
            bus.value = '{scene.id},{add_del}{label}';
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
            document.getElementById('{AppHtml.make_elem_id_button_update('label')}').click();""".replace(
                '\n', ' '
            ).replace('"', '&quot;')
            operation_html += f"""
                <input type="checkbox" id="scene-{scene.id}-{label}" name="scene-{scene.id}" value="{label}" {checked}
                       onclick="{onclick_js}">
                <label for="scene-{scene.id}-{label}" class="scene-label-btn">{label}</label>
                """

        return f"""
                <div class="scene-label">Scene:</div>
                <div class="operation-checkbox-group">
                    {operation_html}
                </div>
                """

    @staticmethod
    def _pil_to_base64(pil_image: PILImage.Image) -> str:
        """Converts a PIL Image to a base64 encoded string."""
        buffered = BytesIO()
        pil_image.save(buffered, format='PNG')
        return base64.b64encode(buffered.getvalue()).decode()

    @staticmethod
    def html_image_modal() -> gr.HTML:
        # Pure HTML for the full-page image overlay (modal)
        return gr.HTML("""
        <style>
            #fullPageImageOverlay {
                display: none; /* Hidden by default */
                position: fixed; /* Stay in place */
                z-index: 1000; /* Sit on top */
                left: 0;
                top: 0;
                width: 100%; /* Full width */
                height: 100%; /* Full height */
                overflow: auto; /* Enable scroll if needed */
                background-color: rgba(0,0,0,0.9); /* Black w/ opacity */
                /* Removed display: flex; from here. It will be set by JS when shown. */
                justify-content: center;
                align-items: center;
                flex-direction: row; /* To stack image and details side-by-side */
                /*flex-direction: column;*/ /* To stack image and details */
                gap: 20px;
            }
            #fullPageImageOverlay img {
                max-width: 60%;
                max-height: 90%;
                object-fit: contain;
            }
            #fullPageImageOverlay textarea {
                width: 100%;
                height: 100px;
            }
            #fullPageImageCaption {
                background-color: #333333; /* Dark grey background for details */
                padding: 20px;
                border-radius: 8px;
                color: #ffffff; /* White text for details */
            }
            #modalRightColumn {
                display: flex;
                max-width: 100%;
                overflow-y: auto; /* Allow scrolling for long details */
                max-height: 40%;
                color: #ffffff; /* White text for details */
            }
            #fullPageImageCaption h4 {
                color: #ffffff; /* White heading */
            }
            #fullPageImageCaption p {
                color: #cccccc; /* Light grey text for paragraphs */
            }
            #fullPageImageCaption strong {
                color: #ffffff; /* White for strong tags */
            }
            #fullPageImageCaption pre {
                background-color: #555555; /* Slightly lighter grey for preformatted text */
                color: #ffffff; /* White text for preformatted text */
            }
            #fullPageImageDetails {
                background-color: #333333; /* Dark grey background for details */
                padding: 20px;
                border-radius: 8px;
                max-width: 100%;
                overflow-y: auto; /* Allow scrolling for long details */
                max-height: 50%;
                color: #ffffff; /* White text for details */
            }
            #fullPageImageDetails h4 {
                color: #ffffff; /* White heading */
            }
            #fullPageImageDetails p {
                color: #cccccc; /* Light grey text for paragraphs */
            }
            #fullPageImageDetails strong {
                color: #ffffff; /* White for strong tags */
            }
            #fullPageImageDetails pre {
                background-color: #555555; /* Slightly lighter grey for preformatted text */
                color: #ffffff; /* White text for preformatted text */
            }
            #fullPageCloseButton {
                position: absolute;
                top: 15px;
                right: 35px;
                color: #f1f1f1;
                font-size: 40px;
                font-weight: bold;
                transition: 0.3s;
                cursor: pointer;
            }
            #fullPageCloseButton:hover,
            #fullPageCloseButton:focus {
                color: #bbb;
                text-decoration: none;
                cursor: pointer;
            }
        </style>
        <div id="fullPageImageOverlay" onclick="this.style.display='none';">
            <span id="fullPageCloseButton" onclick="event.stopPropagation(); var copyText = document.getElementById('imgCaptionString'); navigator.clipboard.writeText(copyText.value); document.getElementById('fullPageImageOverlay').style.display='none';">&times;</span>
            <img id="fullPageImage" src="" alt="Full Size Image">
            <div id="modalRightColumn">
                <div id="fullPageImageCaption"></div><br>
                <div id="fullPageImageDetails"></div>
            </div>
        </div>
        """)
