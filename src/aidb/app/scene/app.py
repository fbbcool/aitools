import json
import os
import re
import gradio as gr
import pyperclip
from pathlib import Path
from typing import Any, Optional

from aidb import SceneManager, SceneDef
from aidb.app.cell_scene import AppSceneCell
from aidb.app.cell_scene_image import AppSceneImageCell, editor_labels
from aidb.app.html import AppHtml, AppOpMmode, AppHelper, HtmlHelper

from ait.tools.files import imgs_from_url
from ait.tools.images import image_from_url


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

            # Hidden trigger + databus for captioning an image (registered or
            # unregistered) using Joy / JoySceneDB.
            button_hidden_simg_editor_caption = gr.Button(
                'Hidden SceneImage Editor Caption',
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_caption_button(),
            )
            databus_simg_editor_caption = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_caption_databus(),
            )

            # Hidden trigger + in/out databuses for the per-cell 'set' button.
            # The in-databus carries the image id; the out-databus carries
            # the JSON `{image_id, caption}` result that the JS .then()
            # callback reads to populate the caption / caption_joy textareas.
            button_hidden_simg_editor_set = gr.Button(
                'Hidden SceneImage Editor Set',
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_set_button(),
            )
            databus_simg_editor_set_in = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_set_databus(),
            )
            databus_simg_editor_set_out = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_set_result_databus(),
            )

            # Hidden trigger + in/out databuses for the full-size lightbox.
            button_hidden_simg_editor_lightbox = gr.Button(
                'Hidden SceneImage Editor Lightbox',
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_lightbox_button(),
            )
            databus_simg_editor_lightbox_in = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_lightbox_databus(),
            )
            databus_simg_editor_lightbox_out = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_lightbox_result_databus(),
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
                        choices=['Ignore', 'Empty'] + editor_labels(),
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

                # Single shared full-size image lightbox. position:fixed so
                # it overlays everything regardless of where it's placed.
                gr.HTML(value=AppSceneImageCell.html_lightbox_modal())

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

            # SceneImage editor: opening triggered from a scene-cell thumbnail
            # click. We FIRST wipe the editor outputs (so DOM state from the
            # previously-loaded scene is fully gone before the new scene is
            # rendered), THEN load + render the new scene from a fresh DB read.
            button_hidden_simg_editor_open.click(
                self._editor_clear,
                inputs=[],
                outputs=editor_outputs,
            ).then(
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

            # Manual refresh of the editor view (uses the currently-loaded
            # scene id). Same clear-then-load pattern.
            simg_editor_refresh_button.click(
                self._editor_clear,
                inputs=[],
                outputs=editor_outputs,
            ).then(
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

            # Caption an image (registered SceneImage via JoySceneDB, or an
            # unregistered file via Joy directly). The caption is only copied
            # to the clipboard - no DB writes, no UI refresh.
            button_hidden_simg_editor_caption.click(
                self._html_simg_editor_caption,
                inputs=[databus_simg_editor_caption],
                outputs=[],
            )

            # 'set' button (per-cell, on the caption field). The Python side
            # generates a caption when caption_joy is empty and writes the
            # JSON result `{image_id, caption}` into the out-databus. A JS
            # `.then()` callback then reads it and sets the caption_joy +
            # caption textareas in the DOM (no DB write).
            button_hidden_simg_editor_set.click(
                self._caption_set_generate,
                inputs=[databus_simg_editor_set_in],
                outputs=[databus_simg_editor_set_out],
            ).then(
                fn=None,
                inputs=[databus_simg_editor_set_out],
                outputs=None,
                js="""
                (resultStr) => {
                    if (!resultStr) return;
                    let data;
                    try { data = JSON.parse(resultStr); } catch (e) { return; }
                    if (!data || !data.image_id || !data.caption) return;
                    const cj = document.getElementById('simg-set_caption_joy-' + data.image_id);
                    const c  = document.getElementById('simg-set_caption-' + data.image_id);
                    if (cj) { cj.value = data.caption; }
                    if (c)  { c.value  = data.caption; }
                }
                """,
            )

            # Lightbox: thumbnail click -> server reads the full image and
            # returns base64; JS .then() callback sets the modal img and
            # shows the overlay (fit-to-screen via CSS).
            button_hidden_simg_editor_lightbox.click(
                self._lightbox_load,
                inputs=[databus_simg_editor_lightbox_in],
                outputs=[databus_simg_editor_lightbox_out],
            ).then(
                fn=None,
                inputs=[databus_simg_editor_lightbox_out],
                outputs=None,
                js="""
                (b64) => {
                    if (!b64) return;
                    const img = document.getElementById('simg-lightbox-img');
                    const overlay = document.getElementById('simg-lightbox-overlay');
                    if (!img || !overlay) return;
                    img.src = 'data:image/png;base64,' + b64;
                    overlay.style.display = 'flex';
                }
                """,
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

    @staticmethod
    def _editor_clear() -> tuple[str, str, str, str]:
        """
        Wipes every editor output to a clean placeholder. Used as the first
        step of any editor (re-)load so no stale DOM state from the
        previously-displayed scene can survive into the next one.
        """
        loading = '<p><em>loading...</em></p>'
        return '', '', loading, ''

    @staticmethod
    def _flush_state() -> None:
        """
        Best-effort flush of any leftover Python / GPU state from previous
        captioning, scene rendering or DB activity. Called at the start of
        every editor render so a fresh scene cannot inherit GPU memory or
        garbage references from a previous one.
        """
        try:
            import gc

            gc.collect()
        except Exception:
            pass
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass

    def _html_simg_editor_open(
        self, scene_id: Optional[str]
    ) -> tuple[str, str, str, str]:
        """
        Renders the editor for the given scene. Returns:
            (scene_id, scene_info_html, registered_imgs_html, unregistered_imgs_html)

        The Scene + SceneImage objects are constructed fresh from the DB on
        every call (no in-process caching), so values shown reflect the
        current persisted state of the requested scene only.
        """
        # Aggressively flush any leftover state from a previous render or a
        # previous captioner run before we start.
        self._flush_state()

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
                registered_html = AppHtml.html_styled_cells_grid(cells, columns=2)
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

    # ------------------------------------------------------------------
    # captioning
    # ------------------------------------------------------------------
    #
    # IMPORTANT: caption models are *not* cached. A fresh Joy / JoySceneDB
    # instance is created for every click and explicitly destroyed afterwards
    # so the GPU memory is freed for other (external) tasks. We never write
    # captions back to the DB - the result is only copied to the clipboard
    # and the user can decide what to do with it.

    def _html_simg_editor_caption(self, data_str: Optional[str]) -> None:
        """
        Generates a caption for either a registered SceneImage (uses a
        fresh JoySceneDB instance) or an unregistered image file (uses a
        fresh Joy instance), copies the result to the clipboard and frees
        the model.
        """
        if not data_str or not isinstance(data_str, str):
            gr.Warning('Caption: invalid request.')
            return None

        try:
            data = json.loads(data_str)
        except Exception as e:
            print(f'ERROR: caption databus json parse: {e}')
            gr.Warning(f'Caption: malformed request: {e}')
            return None

        target_type = data.get('type')
        target = data.get('target')
        trigger = data.get('trigger')
        if not target_type or not target or not trigger:
            gr.Warning('Caption: incomplete request.')
            return None

        if target_type == 'registered':
            self._caption_registered(target, trigger)
        elif target_type == 'unregistered':
            self._caption_unregistered(target, trigger)
        else:
            gr.Warning(f'Caption: unknown target type [{target_type}].')
        return None

    @staticmethod
    def _release_gpu(obj: Any) -> None:
        """
        Best-effort destruction of a captioner instance and its underlying
        torch model so VRAM is released for other tasks.
        """
        try:
            # If it's a JoySceneDB it owns a Joy via .__joy / ._joy
            inner = getattr(obj, '_JoySceneDB__joy', None)
            if inner is None:
                inner = getattr(obj, '_joy', None)
            for o in (inner, obj):
                if o is None:
                    continue
                for attr in ('model', 'processor'):
                    try:
                        if hasattr(o, attr):
                            setattr(o, attr, None)
                    except Exception:
                        pass
        except Exception as e:
            print(f'WARN: caption release pre-cleanup: {e}')

        del obj

        try:
            import gc

            gc.collect()
        except Exception:
            pass
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception as e:
            print(f'WARN: cuda cache clear failed: {e}')

    def _caption_registered(self, image_id: str, trigger: str) -> None:
        try:
            from ait.caption.joy_scenedb import JoySceneDB
        except Exception as e:
            print(f'ERROR: JoySceneDB import failed: {e}')
            gr.Warning(f'Caption init failed: {e}')
            return None

        gr.Info(
            f'Captioning image {image_id} with trigger [{trigger}]...',
            duration=2.0,
        )
        cfg_name = self._scm._dbc.config.config
        jdb = None
        caption: Optional[str] = None
        try:
            jdb = JoySceneDB(
                config=cfg_name,
                trigger=trigger,
                verbose=1,
                force=True,
            )
            _prompt, caption = jdb._id_caption(image_id)
        except Exception as e:
            print(f'ERROR: caption registered [{image_id}]: {e}')
            gr.Warning(f'Caption failed: {e}')
        finally:
            if jdb is not None:
                self._release_gpu(jdb)

        if not caption:
            gr.Warning(f'No caption produced for image {image_id}.')
            return None

        try:
            pyperclip.copy(caption)
        except Exception as e:
            print(f'WARN: clipboard copy failed: {e}')

        preview = caption if len(caption) <= 80 else caption[:77] + '...'
        gr.Info(
            f'Caption copied to clipboard: {preview}',
            duration=2.5,
        )
        return None

    # ------------------------------------------------------------------
    # lightbox (full-size image modal)
    # ------------------------------------------------------------------

    def _lightbox_load(self, data_str: Optional[str]) -> str:
        """
        Loads the full-size image for a registered SceneImage (by id) or an
        unregistered file (by url) and returns it as a base64 string. The
        JS `.then()` callback wired to this handler injects the result into
        the shared lightbox modal.

        Returns '' on failure (the JS callback then no-ops).

        Always runs `_flush_state()` afterwards so any temporary PIL bytes
        / large strings used for the encode are released.
        """
        if not data_str or not isinstance(data_str, str):
            return ''
        try:
            data = json.loads(data_str)
        except Exception as e:
            print(f'ERROR: lightbox json parse: {e}')
            return ''

        target_type = data.get('type')
        target = data.get('target')
        if not target_type or not target:
            return ''

        pil = None
        b64: Optional[str] = None
        try:
            if target_type == 'registered':
                try:
                    simg = self._scm.scene_image_manager().image_from_id_or_url(target)
                except Exception as e:
                    print(f'ERROR: lightbox load registered [{target}]: {e}')
                    gr.Warning(f'Lightbox load failed: {e}')
                    return ''
                pil = simg.pil
            elif target_type == 'unregistered':
                url = Path(str(target).strip())
                if not url.exists():
                    gr.Warning(f'Lightbox: file does not exist: {url}')
                    return ''
                pil = image_from_url(url)
            else:
                gr.Warning(f'Lightbox: unknown target type [{target_type}].')
                return ''

            if pil is None:
                gr.Warning('Lightbox: could not open image.')
                return ''

            try:
                b64 = HtmlHelper.pil_to_base64(pil)
            except Exception as e:
                print(f'ERROR: lightbox base64 encode failed: {e}')
                gr.Warning(f'Lightbox encode failed: {e}')
                return ''
        finally:
            # Eagerly drop the PIL handle and any large temporary buffers,
            # then flush so subsequent renders / GPU users start clean.
            if pil is not None:
                try:
                    pil.close()
                except Exception:
                    pass
            del pil
            self._flush_state()

        if not b64:
            return ''
        return b64

    def _caption_set_generate(self, image_id_str: Optional[str]) -> str:
        """
        Backend handler for the per-cell 'set' button when caption_joy is
        empty: generates a caption with a fresh JoySceneDB instance (then
        destroys it) and returns a JSON `{image_id, caption}` string.

        The frontend `.then()` JS callback writes the returned caption into
        both the caption_joy and caption textareas (DOM only - no DB write).
        """
        if not image_id_str or not isinstance(image_id_str, str):
            return ''
        image_id = image_id_str.strip()
        if not image_id:
            return ''

        try:
            from ait.caption.joy_scenedb import JoySceneDB
        except Exception as e:
            print(f'ERROR: JoySceneDB import failed: {e}')
            gr.Warning(f'Caption init failed: {e}')
            return ''

        # 'set' always captions with the '1xlasm' trigger via JoySceneDB.
        trigger = '1xlasm'
        gr.Info(
            f"Generating caption for image {image_id} (set, trigger '{trigger}')...",
            duration=2.0,
        )
        cfg_name = self._scm._dbc.config.config
        jdb = None
        caption: Optional[str] = None
        try:
            jdb = JoySceneDB(
                config=cfg_name,
                trigger=trigger,
                verbose=1,
                force=True,
            )
            _prompt, caption = jdb._id_caption(image_id)
        except Exception as e:
            print(f'ERROR: caption set [{image_id}]: {e}')
            gr.Warning(f'Caption failed: {e}')
        finally:
            if jdb is not None:
                self._release_gpu(jdb)

        if not caption:
            gr.Warning(f'No caption produced for image {image_id}.')
            return ''

        gr.Info(
            f'Caption generated for image {image_id} (not saved - click "save image" to persist).',
            duration=2.5,
        )
        return json.dumps({'image_id': image_id, 'caption': caption})

    def _caption_unregistered(self, url_str: str, trigger: str) -> None:
        url = Path(url_str.strip())
        if not url.exists():
            gr.Warning(f'Caption: file does not exist: {url}')
            return None

        try:
            from ait.caption.joy import Joy
        except Exception as e:
            print(f'ERROR: Joy import failed: {e}')
            gr.Warning(f'Caption init failed: {e}')
            return None

        gr.Info(
            f'Captioning {url.name} with trigger [{trigger}]...',
            duration=2.0,
        )
        joy = None
        caption: Optional[str] = None
        try:
            joy = Joy(trigger=trigger)
            _prompt, caption = joy.imgurl_caption(str(url))
        except Exception as e:
            print(f'ERROR: caption unregistered [{url}]: {e}')
            gr.Warning(f'Caption failed: {e}')
        finally:
            if joy is not None:
                self._release_gpu(joy)

        if not caption:
            gr.Warning(f'No caption produced for {url.name}.')
            return None

        try:
            pyperclip.copy(caption)
        except Exception as e:
            print(f'WARN: clipboard copy failed: {e}')

        preview = caption if len(caption) <= 80 else caption[:77] + '...'
        gr.Info(
            f'Caption copied to clipboard: {preview}',
            duration=2.5,
        )
        return None

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
