import os
import gradio as gr
from typing import Optional
import json
import pyperclip

from aidb import SceneManager, SceneDef, Scene
from aidb.tagger_defines import TaggerDef
from aidb.app.cell_scene import AppSceneCell
from aidb.app.html import AppHtml, AppOpMmode

from ait.tools.images import image_from_url  # Import json for robust string escaping


class AIDBSceneApp:
    """
    A Gradio-based frontend for the AIDB image metadata management system.
    This class will encapsulate the Gradio UI components and their interactions
    with the DBManager.
    """

    def __init__(self, scm: SceneManager) -> None:
        """
        Initializes the Gradio application with a reference to the SceneManager.
        """

        self._scm = scm
        self._dbm = self._scm._dbc

        self.interface = self._create_interface()

    def _create_interface(self):
        """
        Creates the Gradio interface for the application.
        This method will define the UI components and their associated functions.
        """

        with gr.Blocks() as demo:
            gr.Markdown('# AIDB Scene Metadata Manager')
            gr.Markdown('Welcome to the AIDB frontend. Use the search options below.')

            # State variables for pagination (only advanced search cache is needed)
            advanced_search_scene_cache = gr.State(value=[])

            # --- Hidden Components for Robust Event Handling ---
            # Trigger buttons (no data, just event triggers)
            data_get_trigger = gr.Button(
                'Get Full Data Trigger',
                visible=False,
                elem_id=AppHtml.make_elem_id_button_get('data'),
            )
            info_update_trigger = gr.Button(
                'Hidden Info Update Trigger',
                visible=False,
                elem_id=AppHtml.make_elem_id_button_update('info'),  # has to be a mode
            )
            rate_update_trigger = gr.Button(
                'Hidden Rating Update Trigger',
                visible=False,
                elem_id=AppHtml.make_elem_id_button_update('rate'),  # has to be a mode
            )
            label_update_trigger = gr.Button(
                'Hidden Label Update Trigger',
                visible=False,
                elem_id=AppHtml.make_elem_id_button_update('label'),  # has to be a mode
            )

            # Data bus textboxes (hold data passed from JS to Python)
            info_data_bus = gr.Textbox(
                visible=False, elem_id=AppHtml.make_elem_id_databus_textbox('info')
            )  # has to be a mode
            rate_data_bus = gr.Textbox(
                visible=False, elem_id=AppHtml.make_elem_id_databus_textbox('rate')
            )  # has to be a mode
            label_data_bus = gr.Textbox(
                visible=False, elem_id=AppHtml.make_elem_id_databus_textbox('label')
            )  # has to be a mode

            # Data bus textboxes for the scene modal
            modal_img_data_bus = gr.Textbox(visible=False, elem_id='modal_img_data_bus_elem')
            modal_details_data_bus = gr.Textbox(
                visible=False, elem_id='modal_details_data_bus_elem'
            )
            # --- End Hidden Components ---

            AppSceneCell.html_image_modal()

            with gr.Tab('Scene Search'):  # Renamed tab for clarity
                gr.Markdown('## Advanced Scene Search with Mandatory and Optional Tags')
                gr.Markdown(
                    'Select up to 3 mandatory tags (all must be present) and up to 3 optional tags (contribute to score).'
                )

                with gr.Row():
                    rating_min = gr.Dropdown(
                        label='Rating Min',
                        choices=[
                            str(x)
                            for x in list(range(SceneDef.RATING_MIN, SceneDef.RATING_MAX + 1))
                        ],
                        value=f'{SceneDef.RATING_INIT}',
                        allow_custom_value=False,
                        interactive=True,
                    )
                    rating_max = gr.Dropdown(
                        label='Rating Max',
                        choices=[
                            str(x)
                            for x in list(range(SceneDef.RATING_MIN, SceneDef.RATING_MAX + 1))
                        ],
                        value=f'{SceneDef.RATING_MAX}',
                        allow_custom_value=False,
                        interactive=True,
                    )
                with gr.Row():
                    mode = gr.Dropdown(
                        label='Mode Operation',
                        choices=['info', 'rate', 'label'],
                        value='info',
                        allow_custom_value=False,
                        interactive=True,
                    )
                    label_dropdown = gr.Dropdown(
                        label='Label',
                        choices=['Ignore', 'Empty'] + TaggerDef.LABELS['label'],
                        value='Ignore',
                        allow_custom_value=False,
                        interactive=True,
                    )

                search_button = gr.Button('Search Scenes')

                with gr.Column(visible=True):
                    # in the title, the number of selected scenes should be shown
                    curr_label = 'Matching Scenes (Highest Score First)'
                    advanced_search_html_display = gr.HTML(label=curr_label)

                search_button.click(
                    self._scenes_search_and_op,
                    inputs=[
                        rating_min,
                        rating_max,
                        mode,
                        label_dropdown,
                    ],
                    outputs=[
                        advanced_search_html_display,
                        advanced_search_scene_cache,
                    ],
                )

            # Link hidden triggers to functions
            data_get_trigger.click(
                self._get_data_for_modal,
                inputs=[label_data_bus],
                outputs=[modal_img_data_bus, modal_details_data_bus],
            ).then(  # Chaining .then() to update the modal after data is received
                None,  # No Python function needed here, just JS
                [
                    modal_img_data_bus,
                    modal_details_data_bus,
                ],  # Inputs are the data buses
                None,  # No outputs to Gradio components for this JS part
                js="""
                (img_base64, details_json_string) => {
                    console.log('JS: Received data for modal. Updating modal content.');
                    const details = JSON.parse(details_json_string); // Parse the JSON string from the data bus

                    if (details.error) {
                        document.getElementById('fullPageScene').src = ''; // Clear scene
                        document.getElementById('fullPageSceneDetails').innerHTML = `
                            <h4>Error:</h4>
                            <p>${details.error}</p>
                        `;
                    } else {
                        document.getElementById('fullPageScene').src = 'data:image/png;base64,' + img_base64;
                        document.getElementById('fullPageSceneDetails').innerHTML = `
                            <h4>Scene Details:</h4>
                            <p><strong>ID:</strong> ${details.id}</p>
                            <p><strong>Full Path:</strong> ${details.full_path}</p>
                            <p><strong>Rating:</strong> ${details.rating}</p>
                            <p><strong>Category:</strong> ${details.category}</p>
                            <p><strong>Dimensions:</strong> ${details.dimensions_width}x${details.dimensions_height} ${details.dimensions_unit}</p>
                            <p><strong>Creation Date:</strong> ${details.creation_date}</p>
                            <p><strong>Last Modified Date:</strong> ${details.last_modified_date}</p>
                            <h4>WD Tags (Tag: Probability):</h4>
                            <pre>${details.tags_html}</pre>
                        `;
                        document.getElementById('fullPageSceneCaption').innerHTML = `
                            <h4>Caption:</h4>
                            <input type="text" value="${details.caption}" id="imgCaptionString">
                        `;
                    }
                    document.getElementById('fullPageSceneOverlay').style.display = 'flex'; // Use flex to center
                }
                """,
            )

            info_update_trigger.click(
                self._update_scene_info,  # Call the update function first
                inputs=[info_data_bus],  # Input is the data bus textbox
                outputs=[],  # This function doesn't update UI directly
            )
            rate_update_trigger.click(
                self._update_scene_rating,  # Call the update function first
                inputs=[rate_data_bus],  # Input is the data bus textbox
                outputs=[],  # This function doesn't update UI directly
            )
            label_update_trigger.click(
                self._update_scene_label,  # Call the update function first
                inputs=[label_data_bus],  # Input is the data bus textbox
                outputs=[],  # This function doesn't update UI directly
            )

            with gr.Tab('Scene View'):
                with gr.Column(visible=True):
                    scene_display_html = gr.HTML(label='Images in Scene')
                    with gr.Row():
                        scene_id_textbox = gr.Textbox(label='Scene id')
                        scene_go_button = gr.Button('Go')

                scene_go_button.click(
                    self.display_scene,
                    inputs=[
                        scene_id_textbox,
                        mode,
                    ],
                    outputs=[
                        scene_display_html,
                    ],
                )

        return demo

    def _generate_scene_html(self, scenes_on_page_data: list[Scene], mode: AppOpMmode) -> str:
        """
        Generates HTML for a two-column grid of scenes with captions, rating controls,
        and contributing tags.
        Includes client-side JavaScript for scene click to show full-size overlay.
        """

        img_width = 250
        html_content = f"""
        <style>
            .image-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax({img_width}px, 1fr));
                gap: 15px;
                padding: 10px;
            }}
            .image-item {{
                border: 1px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                text-align: center;
                background-color: #333333; /* Dark grey background */
                padding-bottom: 10px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                height: 100%;
            }}
            .image-item img {{
                max-width: 100%;
                height: auto;
                display: block;
                margin: 0 auto;
                border-bottom: 1px solid #eee;
                padding: 5px;
                cursor: pointer; /* Indicate clickable only on image itself */
            }}
            .image-item-warning {{
                border: 1px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                text-align: center;
                background-color: #aaaa33; /* Dark grey background */
                padding-bottom: 10px;
                doperationisplay: flex;
                flex-direction: column;
                justify-content: space-between;
                height: 100%;
            }}
            .image-item-error img {{
                max-width: 100%;
                height: auto;
                display: block;
                margin: 0 auto;
                border-bottom: 1px solid #eee;
                padding: 5px;
                cursor: pointer; /* Indicate clickable only on image itself */
            }}
            .image-item-error {{
                border: 1px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                text-align: center;
                background-color: #ff3333; /* Dark grey background */
                padding-bottom: 10px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                height: 100%;
            }}
            .image-item-warning img {{
                max-width: 100%;
                height: auto;
                display: block;
                margin: 0 auto;
                border-bottom: 1px solid #eee;
                padding: 5px;
                cursor: pointer; /* Indicate clickable only on image itself */
            }}
            .image-caption {{
                font-size: 0.9em;
                color: #ffffff; /* White font for caption */
                margin-top: 5px;
                padding: 0 10px;
                word-wrap: break-word;
            }}
            .image-controls {{
                margin-top: 10px;
                padding: 0 10px;
                color: #ffffff; /* White font for controls */
            }}
            .operation-radio-group {{
                display: flex;
                justify-content: center;
                gap: 5px;
                flex-wrap: wrap; /* Allow wrapping for smaller screens */
            }}
            .operation-radio-group input[type="radio"] {{
                display: none; /* Hide default radio button */
            }}
            .operation-radio-group label {{
                padding: 5px 8px;
                border: 1px solid #ccc;
                border-radius: 5px;
                cursor: pointer;
                font-size: 0.8em;
                transition: all 0.2s ease;
                background-color: #555555; /* Slightly lighter grey for radio buttons */
                color: #ffffff; /* White font for radio button labels */
            }}
            .operation-radio-group input[type="radio"]:checked + label {{
                background-color: #4CAF50; /* Green for selected */
                color: white;
                border-color: #4CAF50;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            }}
            .operation-radio-group label:hover {{
                background-color: #777777; /* Darker hover for radio buttons */
            }}
            .operation-checkbox-group {{
                display: flex;
                justify-content: center;
                gap: 5px;
                flex-wrap: wrap; /* Allow wrapping for smaller screens */
            }}
            .operation-checkbox-group input[type="checkbox"] {{
                display: none; /* Hide default checkbox button */
            }}
            .operation-checkbox-group label {{
                padding: 5px 8px;
                border: 1px solid #ccc;
                border-radius: 5px;
                cursor: pointer;
                font-size: 0.8em;
                transition: all 0.2s ease;
                background-color: #555555; /* Slightly lighter grey for checkbox buttons */
                color: #ffffff; /* White font for checkbox button labels */
            }}
            .operation-checkbox-group input[type="checkbox"]:checked + label {{
                background-color: #4CAF50; /* Green for selected */
                color: white;
                border-color: #4CAF50;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            }}
            .operation-checkbox-group label:hover {{
                background-color: #777777; /* Darker hover for checkbox buttons */
            }}
            .tag-contribution {{
                font-size: 0.8em;
                color: #cccccc; /* Light grey for tag contribution text */
                margin-top: 5px;
                padding: 0 10px;
                text-align: left;
            }}
            .tag-contribution strong {{
                color: #ffffff; /* White font for strong tags */
            }}
        </style>
        <div class="image-grid">
        """

        for scene in scenes_on_page_data:
            # Call AppImageCell.make to get the HTML for each cell
            html_content += AppSceneCell.make(
                scene,
                mode,
            )

        html_content += '</div>'
        return html_content

    def display_scene(
        self,
        scene_id: str,
        mode: AppOpMmode,
    ) -> tuple[str, int, str]:
        """
        Jumps to a specific page in the image display.
        """
        if not scene_id:
            return '', 1, 'Page 0/0'

        return ('', 0, '')

    def _scenes_search_and_op(
        self,
        rating_min: Optional[str],
        rating_max: Optional[str],
        mode: Optional[AppOpMmode],
        opt_label: Optional[str],
    ) -> tuple[str, list[Scene]]:
        """
        Performs an advanced search and initializes pagination.
        Returns (html_content, image_cache, current_page, page_info_text).
        """
        # add chosen operation to images
        r_min = SceneDef.RATING_MIN
        if rating_min is not None:
            r_min = int(rating_min)
        r_max = SceneDef.RATING_MAX
        if rating_max is not None:
            r_max = int(rating_max)
        if opt_label is None:
            labels = None
        elif opt_label in ['Ignore', 'None']:
            labels = None
        elif opt_label in ['Empty']:
            labels = []
        else:
            labels = [opt_label]
        scenes = [
            self._scm.scene_from_id_or_url(id)
            for id in self._scm.ids_from_rating(r_min, r_max, labels=labels)
        ]
        SceneDef.sort_by_rating(scenes)
        print(f'Found {len(scenes)} scenes matching advanced search criteria.')

        if mode is None:
            mode = 'none'
        html_output = self._generate_scene_html(scenes, mode=mode)

        return html_output, scenes

    def _get_data_for_modal(self, scene_id: str) -> tuple[str, str]:
        """
        Fetches full scene data for the modal display.
        Returns a raw base64 string and a JSON-serialized string of the scene details.
        These strings are intended to be placed in hidden Textbox components (data buses).
        """
        print(f'DEBUG: _get_full_scene_data_for_modal called for scene ID: {scene_id}')

        if not scene_id:
            print('ERROR: Received empty or invalid scene ID for modal data.')
            return '', json.dumps({'error': 'Invalid scene ID provided.'})  # pyright: ignore

        scene: Scene | None = self._scm.scene_from_id_or_url(scene_id)
        if scene is None:
            print(f"ERROR: Invalid ObjectId for image ID '{scene_id}'")
            return '', json.dumps({'error': f'Invalid image ID format: {scene_id}'})  # pyright: ignore

        pil_img = image_from_url(scene.url_thumbnail)
        if pil_img is None:
            print(f'ERROR: Could not load PIL image file for image ID: {scene_id}.')
            return '', json.dumps({'error': f'Could not load image file for ID: {scene_id}.'})  # pyright: ignore

        full_img_base64 = AppSceneCell._pil_to_base64(pil_img)

        return full_img_base64, json.dumps(scene.data)

    def _update_scene_info(
        self,
        data_str: str,
    ) -> None:  # No outputs from this function
        """
        Updates an scene's info in the database.
        This function is triggered by a hidden button and receives its data from a hidden 'data bus' textbox.
        """
        print(f"DEBUG: _update_scene_info called with data from bus: '{data_str}'")

        if not data_str or not isinstance(data_str, str):
            print(f'ERROR: Invalid or empty data [{data_str}]')
            gr.Warning('Could not update info: Invalid data received from frontend.')
            return None

        # We expect a string like "scene_id_val,new_info_val"
        parts = data_str.split(',')
        if len(parts) != 2:
            print(f'ERROR: Invalid data format for _update_scene_info: {data_str}')
            gr.Warning(f"Could not update info: Malformed data '{data_str}'.")
            return None

        scene_id = parts[0].strip()
        try:
            new_info = str(parts[1].strip())
        except ValueError:
            print(f'ERROR: Invalid info value received in data: {data_str}')
            gr.Warning(f"Could not update info: Invalid info value in '{data_str}'.")
            return None
        print(f'DEBUG: _update_scene_rating called for scene {scene_id} with info {new_info}')
        scene: Scene = self._scm.scene_from_id_or_url(scene_id)

        clipspace = ''
        if new_info == 'id':
            clipspace = str(scene.id)
        elif new_info == 'url':
            clipspace = str(scene.url)

        pyperclip.copy(clipspace)
        return None

    def _update_scene_rating(
        self,
        data_str: str,
    ) -> None:  # No outputs from this function
        """
        Updates an scene's rating in the database.
        This function is triggered by a hidden button and receives its data from a hidden 'data bus' textbox.
        """
        print(f"DEBUG: _update_scene_rating called with data from bus: '{data_str}'")

        if not data_str or not isinstance(data_str, str):
            print(f'ERROR: Invalid or empty data [{data_str}]')
            gr.Warning('Could not update rating: Invalid data received from frontend.')
            return None

        # We expect a string like "scene_id_val,new_rating_val"
        parts = data_str.split(',')
        if len(parts) != 2:
            print(f'ERROR: Invalid data format for _update_scene_rating: {data_str}')
            gr.Warning(f"Could not update rating: Malformed data '{data_str}'.")
            return None

        scene_id = parts[0].strip()
        try:
            new_rating = int(parts[1].strip())
        except ValueError:
            print(f'ERROR: Invalid rating value received in data: {data_str}')
            gr.Warning(f"Could not update rating: Invalid rating value in '{data_str}'.")
            return None
        print(f'DEBUG: _update_scene_rating called for scene {scene_id} with rating {new_rating}')
        # Update the database
        scene: Scene = self._scm.scene_from_id_or_url(scene_id)
        scene.set_rating(new_rating)
        scene._dbstore()
        gr.Info(f'Tried: rating for scene {scene_id} updated to {new_rating}.', duration=0.5)

        return None

    def _update_scene_label(
        self,
        data_str: str,
    ) -> None:  # No outputs from this function
        """
        Updates an scene's label in the database.
        This function is triggered by a hidden button and receives its data from a hidden 'data bus' textbox.
        """
        print(f"DEBUG: _update_scene_labels called with data from bus: '{data_str}'")

        if not data_str or not isinstance(data_str, str):
            print(f'ERROR: Invalid or empty data [{data_str}]')
            gr.Warning('Could not update labels: Invalid data received from frontend.')
            return None

        # We expect a string like "scene_id_val,{+|-}label"
        parts = data_str.split(',')
        if len(parts) != 2:
            print(f'ERROR: Invalid data format for _update_scene_label: {data_str}')
            gr.Warning(f"Could not update label: Malformed data '{data_str}'.")
            return None

        scene_id = parts[0].strip()
        try:
            update_label = str(parts[1].strip())
        except ValueError:
            print(f'ERROR: Invalid rating value received in data: {data_str}')
            gr.Warning(f"Could not update rating: Invalid rating value in '{data_str}'.")
            return None
        print(f'DEBUG: _update_scene_label called for scene {scene_id} with rating {update_label}')
        # Update the database
        scene: Scene = self._scm.scene_from_id_or_url(scene_id)
        scene.update_label(update_label)
        scene._dbstore()
        gr.Info(f'Tried: rating for scene {scene_id} updated to {update_label}.', duration=0.5)

        return None

    def launch(self, **kwargs):
        print('Launching Gradio application...')
        self.interface.launch(**kwargs)


if __name__ == '__main__':
    config = os.environ['AIDB_SCENE_CONFIG']
    print(f'from environment: config {[config]}')
    if not config:
        config = 'default'
    print(f'using config {[config]}')
    scm = SceneManager(config=config)  # type: ignore
    scm.scenes_update()
    app = AIDBSceneApp(scm)
    app.launch(server_port=7861)
