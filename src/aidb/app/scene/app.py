import os
import re
import gradio as gr
import pyperclip
from pathlib import Path
from typing import Optional

from aidb import SceneManager, SceneDef
from aidb.tagger_defines import TaggerDef
from aidb.app.cell_scene import AppSceneCell
from aidb.app.cell_scene_image import AppSceneImageCell
from aidb.app.html import AppHtml, AppOpMmode, AppHelper

from ait.tools.files import imgs_from_url


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

            button_hidden_cmd = gr.Button(
                'Hidden Cmd Button',
                visible='hidden',
                elem_id=AppHtml.elem_id_cmd_button(),
            )

            # Data bus textboxes (hold data passed from JS to Python)
            databus_cmd = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_cmd_databus(),
            )  # has to be a mode

            # Hidden trigger + databus for opening the SceneImage editor
            button_hidden_simg_editor_open = gr.Button(
                'Hidden SceneImage Editor Open',
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_open_button(),
            )
            databus_simg_editor = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_databus(),
            )

            # Hidden trigger + databus for registering an unregistered image
            button_hidden_simg_editor_register = gr.Button(
                'Hidden SceneImage Editor Register',
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_register_button(),
            )
            databus_simg_editor_register = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_register_databus(),
            )
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
                        choices=['info', 'rate', 'label', 'set'],
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

            with gr.Tab(
                'Scene Image Editor',
                elem_id=AppHtml.elem_id_simg_editor_tab(),
            ):
                gr.Markdown('## Scene Image Editor')
                gr.Markdown(
                    'Click a thumbnail in the **Scene Search** tab to load that '
                    "scene's images here for editing (rating, caption, prompt)."
                )
                with gr.Row():
                    simg_editor_scene_id = gr.Textbox(
                        label='Scene ID',
                        interactive=False,
                    )
                with gr.Row():
                    simg_editor_url_button = gr.Button('url')
                simg_editor_scene_info_html = gr.HTML(label='Scene')
                with gr.Row():
                    simg_editor_refresh_button = gr.Button('Refresh')
                gr.Markdown('### Registered Images')
                simg_editor_html = gr.HTML(label='Scene Images')
                gr.Markdown('### Unregistered Images')
                simg_editor_unregistered_html = gr.HTML(label='Unregistered Images')

            # Link hidden triggers to functions
            button_hidden_cmd.click(
                self._apphelper.cmd_run,  # Call the update function first
                inputs=[databus_cmd],  # Input is the data bus textbox
                outputs=[],  # This function doesn't update UI directly
            )

            # Outputs that all editor renders update.
            editor_outputs = [
                simg_editor_scene_id,
                simg_editor_scene_info_html,
                simg_editor_html,
                simg_editor_unregistered_html,
            ]

            # SceneImage editor: opening triggered from a scene-cell thumbnail click.
            button_hidden_simg_editor_open.click(
                self._html_simg_editor_open,
                inputs=[databus_simg_editor],
                outputs=editor_outputs,
            )

            # Copy the currently-loaded scene's url to the clipboard.
            simg_editor_url_button.click(
                self._simg_editor_copy_scene_url,
                inputs=[simg_editor_scene_id],
                outputs=[],
            )

            # Manual refresh of the editor view (uses the currently-loaded scene id).
            simg_editor_refresh_button.click(
                self._html_simg_editor_open,
                inputs=[simg_editor_scene_id],
                outputs=editor_outputs,
            )

            # Register an unregistered image (driven by per-image register button
            # in the unregistered-images section). Refreshes the editor afterwards.
            button_hidden_simg_editor_register.click(
                self._html_simg_editor_register,
                inputs=[databus_simg_editor_register, simg_editor_scene_id],
                outputs=editor_outputs,
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

    def _simg_editor_copy_scene_url(self, scene_id: Optional[str]) -> None:
        """
        Copies the scene's url (filesystem path) of the currently-loaded scene
        to the clipboard via pyperclip (matches the behaviour of the existing
        scene 'url' to_clipspace cmd).
        """
        if not scene_id or not isinstance(scene_id, str):
            gr.Warning('No scene loaded.')
            return None
        scene_id = scene_id.strip()
        try:
            scene = self._scm.scene_from_id_or_url(scene_id)
        except Exception as e:
            print(f'ERROR: couldnt load scene [{scene_id}]: {e}')
            gr.Warning(f'Failed to load scene {scene_id}: {e}')
            return None
        url = str(scene.url)
        if not url:
            gr.Warning('Scene has no url.')
            return None
        pyperclip.copy(url)
        gr.Info(f'Copied scene url: {url}', duration=1.5)
        return None

    def _html_simg_editor_open(
        self, scene_id: Optional[str]
    ) -> tuple[str, str, str, str]:
        """
        Renders the editor for the given scene. Returns:
            (scene_id, scene_info_html, registered_imgs_html, unregistered_imgs_html)
        """
        empty_msg = '<p>No scene selected. Click a scene thumbnail to load it.</p>'
        if not scene_id or not isinstance(scene_id, str):
            return '', '', empty_msg, ''

        scene_id = scene_id.strip()
        try:
            scene = self._scm.scene_from_id_or_url(scene_id)
        except Exception as e:
            print(f'ERROR: couldnt load scene [{scene_id}]: {e}')
            err = f'<p>Failed to load scene <code>{scene_id}</code>: {e}</p>'
            return scene_id, '', err, ''

        styles = AppSceneImageCell.html_styles()
        scene_info_html = styles + AppSceneImageCell.html_scene_info(scene)

        # registered images
        try:
            imgs = scene.imgs_sorted
        except Exception as e:
            print(f'ERROR: couldnt list imgs for scene [{scene_id}]: {e}')
            imgs = []
            registered_html = (
                f'<p>Failed to list images for scene <code>{scene_id}</code>: {e}</p>'
            )
        else:
            if imgs:
                cells = ''.join(AppSceneImageCell.html(img) for img in imgs)
                registered_html = AppHtml.html_styled_cells_grid(cells)
            else:
                registered_html = (
                    f'<p>No SceneImages registered for scene <code>{scene_id}</code>.</p>'
                )

        # unregistered images
        unregistered_urls = self._unregistered_urls_in_scene(scene)
        if unregistered_urls:
            cells = ''.join(
                AppSceneImageCell.html_unregistered_cell(u) for u in unregistered_urls
            )
            unregistered_html = AppHtml.html_styled_cells_grid(cells)
        else:
            unregistered_html = (
                f'<p>No unregistered images in scene <code>{scene.url}</code>.</p>'
            )

        return scene_id, scene_info_html, registered_html, unregistered_html

    def _unregistered_urls_in_scene(self, scene) -> list[Path]:
        """
        Returns image files in the scene's directory that are not yet
        registered (i.e. their filename has no orig/thumbnail/train prefix).
        """
        try:
            urls = imgs_from_url(scene.url)
        except Exception as e:
            print(f'ERROR: couldnt list dir [{scene.url}]: {e}')
            return []
        out: list[Path] = []
        for url in urls:
            if SceneDef.id_and_prefix_from_filename(url) is not None:
                # already managed (orig / thumbnail / train) - skip
                continue
            out.append(url)
        out.sort()
        return out

    def _html_simg_editor_register(
        self, url_str: Optional[str], scene_id: Optional[str]
    ) -> tuple[str, str, str, str]:
        """
        Registers an unregistered image file by url and refreshes the editor.
        """
        if not url_str or not isinstance(url_str, str):
            gr.Warning('Register: invalid url.')
            return self._html_simg_editor_open(scene_id)

        url = Path(url_str.strip())
        if not url.exists():
            gr.Warning(f'Register: file does not exist: {url}')
            return self._html_simg_editor_open(scene_id)

        try:
            im = self._scm.scene_image_manager()
            new_id = im.register_from_url(url)
        except Exception as e:
            print(f'ERROR: register_from_url [{url}]: {e}')
            gr.Warning(f'Register failed: {e}')
            return self._html_simg_editor_open(scene_id)

        if new_id is None:
            gr.Warning(f'Register: could not register {url} (not an img/vid or already managed).')
        else:
            gr.Info(f'Registered {url.name} as id {new_id}.', duration=1.5)

        # Re-sync the scene so its imgs list picks up the new SceneImage.
        try:
            scene = self._scm.scene_from_id_or_url(scene_id) if scene_id else None
            if scene is not None:
                scene.update()
        except Exception as e:
            print(f'WARN: scene.update after register failed: {e}')

        return self._html_simg_editor_open(scene_id)

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
