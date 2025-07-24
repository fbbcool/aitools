
import base64
from io import BytesIO
from PIL import Image as PILImage
import html
from typing import Final, List, Tuple
from aidb.image import Image
from aidb.tagger import TAGS_CUSTOM
import gradio as gr

class AppImageCell:
    """
    A helper class to encapsulate the HTML generation logic for a single image cell
    in the Gradio grid display for showing rating and contributing tags.
    The rating can be changed by clicking.
    """

    @staticmethod
    def make(
        img: Image,
        get_full_image_data_trigger_id: str,
        rating_update_trigger_id: str,
        scene_update_trigger_id: str,
    ) -> str:
        """
        Generates the HTML string for a single image cell.

        Args:
            image_obj (Image): The Image object for which to generate the cell.
            get_full_image_data_trigger_id (str): The HTML ID of the hidden button to trigger modal data fetch.
            rating_update_trigger_id (str): The HTML ID of the hidden button to trigger rating update.

        Returns:
            str: The HTML string for the image cell.
        """
        grid_thumb_pil = img.thumbnail 
        
        if grid_thumb_pil:
            grid_img_base64 = AppImageCell._pil_to_base64(grid_thumb_pil)
        else:
            grid_img_base64 = "" # Or a base64 encoded placeholder image
            print(f"Warning: No thumbnail available for image ID: {img.id}. Displaying empty image.")

        # Format contributing tags for display
        contributing_tags_html = ""
        if img.contributing_tags:
            contributing_tags_html = "<div class='tag-contribution'><strong>Tags:</strong><br>"
            for tag, prob in sorted(img.contributing_tags, key=lambda x: x[1], reverse=True): # Sort contributing tags by probability
                contributing_tags_html += f"{html.escape(tag)}: {prob:.2f}<br>"
            contributing_tags_html += "</div>"
        
        #n0 = img.neighbor0
        #caption = f"Score: {img.score:.2f} ({img.image_id}, {n0[1]:.2f}->{n0[0]}) "
        caption = f"Score: {img.score:.2f} ({img.id})"

        # The onclick for the image now also uses the data bus pattern.
        class_img = "image-item"

        img_onclick_js = f"""
        const bus = document.querySelector('#image_id_bus_elem textarea');
        bus.value = '{img.id}';
        bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        document.getElementById('{get_full_image_data_trigger_id}').click();""".replace('\n', ' ').replace('"', '&quot;')

        return f"""
        <div class="{class_img}" id="image-{img.id}">
            <img src="data:image/png;base64,{grid_img_base64}" alt="Image Preview" onclick="{img_onclick_js}">
            <div class="image-caption">{caption}</div>
            <div class="image-controls">
                {AppImageCell.html_operation(img, rating_update_trigger_id, scene_update_trigger_id)}
            </div>
            {contributing_tags_html}
        </div>
        """

    @staticmethod
    def html_operation(img: Image, rating_update_trigger_id: str, scene_update_trigger_id: str) -> str:
        if img.operation is None:
            return ""
        elif img.operation == "nop":
            return ""
        elif img.operation == "rate":
            return AppImageCell._html_op_rate(img, rating_update_trigger_id)
        elif img.operation == "scene":
            return AppImageCell._html_op_scene(img, scene_update_trigger_id)

    
    @staticmethod
    def _html_op_scene(img: Image, update_trigger_id: str) -> str:
        current_tags = img.get_tags_custom("bodypart")


        operation_html = ""
        for bodypart in TAGS_CUSTOM["bodypart"]:
            checked =  "checked" if bodypart in current_tags else ""
            # if clicked it should immediatly highlight
            # The onclick event now uses a more robust pattern:
            # 1. Find the hidden 'data bus' textbox.
            # 2. Set its value to the 'image_id,rating' string.
            # 3. Dispatch an 'input' event so Gradio recognizes the change.
            # 4. Programmatically click the hidden trigger button.
            onclick_js = f"""
            event.stopPropagation();
            const bus = document.querySelector('#scene_data_bus_elem textarea');
            bus.value = '{img.id},{bodypart}';
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
            document.getElementById('{update_trigger_id}').click();""".replace('\n', ' ').replace('"', '&quot;')
            operation_html += f"""
                <input type="checkbox" id="scene-{img.id}-{bodypart}" name="scene-{img.id}" value="{bodypart}" {checked}
                       onclick="{onclick_js}">
                <label for="scene-{img.id}-{bodypart}" class="scene-label-btn">{bodypart}</label>
                """
        
        return f"""
                <div class="scene-label">Scene:</div>
                <div class="operation-checkbox-group">
                    {operation_html}
                </div>
                """
    
    @staticmethod
    def _html_op_rate(img: Image, update_trigger_id: str) -> str:
        current_rating = img.data.get("rating", -1) # Get current rating, default -1

        operation_html = ""
        for r in range(-2, 6): # Ratings from -2 to 5
            checked = "checked" if current_rating == r else ""
            # if clicked it should immediatly highlight
            # The onclick event now uses a more robust pattern:
            # 1. Find the hidden 'data bus' textbox.
            # 2. Set its value to the 'image_id,rating' string.
            # 3. Dispatch an 'input' event so Gradio recognizes the change.
            # 4. Programmatically click the hidden trigger button.
            onclick_js = f"""
            event.stopPropagation();
            const bus = document.querySelector('#rating_data_bus_elem textarea');
            bus.value = '{img.id},{r}';
            bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
            document.getElementById('{update_trigger_id}').click();""".replace('\n', ' ').replace('"', '&quot;')
            operation_html += f"""
                <input type="radio" id="rating-{img.id}-{r}" name="rating-{img.id}" value="{r}" {checked}
                       onclick="{onclick_js}">
                <label for="rating-{img.id}-{r}" class="rating-label-btn">{r}</label>
                """
        
        return f"""
                <div class="rating-label">Rating:</div>
                <div class="operation-radio-group">
                    {operation_html}
                </div>
                """

    @staticmethod
    def _pil_to_base64(pil_image: PILImage.Image) -> str:
        """Converts a PIL Image to a base64 encoded string."""
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
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
