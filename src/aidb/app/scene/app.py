import os
import gradio as gr
from typing import Optional

from aidb import SceneManager, SceneDef
from aidb.tagger_defines import TaggerDef
from aidb.app.cell_scene import AppSceneCell
from aidb.app.html import AppHtml, AppOpMmode, AppHelper


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
        self._dbc = self._scm._dbc
        self._apphelper = AppHelper(self._dbc)

        self._interface = self._create_interface()

    def _create_interface(self):
        """
        Creates the Gradio interface for the application.
        This method will define the UI components and their associated functions.
        """

        with gr.Blocks() as if_app:
            gr.Markdown('# AIDB Scene Metadata Manager')
            gr.Markdown('Welcome to the AIDB frontend. Use the search options below.')

            # --- Hidden Components for Robust Event Handling ---
            button_hidden_cmd = gr.Button(
                'Hidden Cmd Update Trigger',
                visible=False,
                elem_id=AppHtml.make_elem_id_button_update('cmd'),  # has to be a mode
            )

            # Data bus textboxes (hold data passed from JS to Python)
            databus_cmd = gr.Textbox(
                visible=False, elem_id=AppHtml.make_elem_id_databus_textbox('cmd')
            )  # has to be a mode
            # --- End Hidden Components ---

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
                    self._html_scenes_search_and_op,
                    inputs=[
                        rating_min,
                        rating_max,
                        mode,
                        label_dropdown,
                    ],
                    outputs=[advanced_search_html_display],
                )

            # Link hidden triggers to functions
            button_hidden_cmd.click(
                self._apphelper.cmd_run,  # Call the update function first
                inputs=[databus_cmd],  # Input is the data bus textbox
                outputs=[],  # This function doesn't update UI directly
            )
        return if_app

    def _html_scenes_search_and_op(
        self,
        rating_min: Optional[str],
        rating_max: Optional[str],
        mode: Optional[AppOpMmode],
        opt_label: Optional[str],
    ) -> str:
        """
        Performs an advanced search and initializes pagination.
        Returns the html for the result grid of scene cells.
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

        html_scenes = ''
        for scene in scenes:
            html_scenes += AppSceneCell.html(
                scene,
                mode,
            )
        return AppHtml.html_styled_cells_grid(html_scenes)

    def launch(self, **kwargs):
        print('Launching Gradio application...')
        self._interface.launch(**kwargs)


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
