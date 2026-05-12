import json
import os
import re
import gradio as gr
import pyperclip
from pathlib import Path
from typing import Any, Optional

from aidb import SceneManager, SceneDef
from aidb.scene.scene_set_manager import SceneSetManager
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
        self._ssm = SceneSetManager(dbc=self._dbc, verbose=0)
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

            # Hidden trigger + databus for registering an unregistered image
            # AS prototype (same flow as `register`, but flips the new
            # SceneImage's `prototype` field to True before refresh).
            button_hidden_simg_editor_register_prototype = gr.Button(
                'Hidden SceneImage Editor Register Prototype',
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_register_prototype_button(),
            )
            databus_simg_editor_register_prototype = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_register_prototype_databus(),
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
            # Out-databus carrying JSON {image_id, caption_joy?, caption_prompt?}
            # so a .then() callback can update the per-cell textareas in the
            # DOM after the server-side save.
            databus_simg_editor_caption_out = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_simg_editor_caption_result_databus(),
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

            # Hidden trigger + in/out databuses for per-cell server refresh.
            # JS writes JSON {img_id, set_id?, mode='edit'|'info'} to the
            # in-databus, fires the button. The Python handler re-renders the
            # cell and writes JSON {target_id, html} to the out-databus. A
            # .then() JS callback swaps the matching DOM element by id.
            button_hidden_cell_refresh = gr.Button(
                'Hidden Cell Refresh',
                visible='hidden',
                elem_id=AppHtml.elem_id_cell_refresh_button(),
            )
            databus_cell_refresh_in = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_cell_refresh_databus_in(),
            )
            databus_cell_refresh_out = gr.Textbox(
                visible='hidden',
                elem_id=AppHtml.elem_id_cell_refresh_databus_out(),
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

            # Single shared full-size image lightbox, mounted once at the top
            # level so it overlays correctly regardless of which tab is active.
            gr.HTML(value=AppSceneImageCell.html_lightbox_modal())

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
                    set_dropdown = gr.Dropdown(
                        label='Set',
                        choices=['Ignore', 'Empty'] + list(SceneDef.TAG_SETS),
                        value='Ignore',
                        allow_custom_value=False,
                        interactive=True,
                    )

                search_button = gr.Button('Search Scenes')

                with gr.Row():
                    search_show_active = gr.Checkbox(
                        label='show active',
                        value=True,
                        interactive=True,
                    )
                    search_show_prototype = gr.Checkbox(
                        label='show prototype',
                        value=True,
                        interactive=True,
                    )

                with gr.Column(visible=True):
                    # in the title, the number of selected scenes should be shown
                    curr_label = 'Matching Scenes (Highest Score First)'
                    advanced_search_html_display = gr.HTML(label=curr_label)

                search_button.click(
                    lambda: '',
                    inputs=[],
                    outputs=[advanced_search_html_display],
                ).then(
                    self._html_scenes_search_and_op,
                    inputs=[
                        rating_min,
                        rating_max,
                        mode,
                        label_dropdown,
                        set_dropdown,
                        search_show_active,
                        search_show_prototype,
                    ],
                    outputs=[advanced_search_html_display],
                )

            with gr.Tab(
                'Scene Editor',
                elem_id=AppHtml.elem_id_simg_editor_tab(),
            ):
                gr.Markdown('## Scene Editor')
                gr.Markdown(
                    'Click a thumbnail in the **Scene Search** tab to load that '
                    "scene's images here for editing (rating, caption, prompt)."
                )
                gr.HTML(
                    value=(
                        '<style>'
                        '#simg-editor-go-button button, '
                        '#set-editor-load-button button { '
                        'background-color: #2ea043; '
                        'color: white; '
                        'border-color: #2ea043; '
                        '}'
                        '#simg-editor-go-button button:hover, '
                        '#set-editor-load-button button:hover { '
                        'background-color: #2c974b; '
                        'border-color: #2c974b; '
                        '}'
                        '</style>'
                    ),
                )
                with gr.Row():
                    simg_editor_scene_id = gr.Textbox(
                        label='Scene ID',
                        interactive=True,
                    )
                    with gr.Column():
                        simg_editor_go_button = gr.Button(
                            'Go',
                            elem_id='simg-editor-go-button',
                        )
                        simg_editor_url_button = gr.Button('url')
                simg_editor_scene_info_html = gr.HTML(label='Scene')
                with gr.Row():
                    simg_editor_caption_empty_button = gr.Button('caption')
                    simg_editor_prototype_all_button = gr.Button('prototype all')
                    simg_editor_refresh_button = gr.Button('Refresh')
                gr.Markdown('### Registered Images')
                simg_editor_html = gr.HTML(label='Scene Images')
                gr.Markdown('### Unregistered Images')
                simg_editor_unregistered_html = gr.HTML(label='Unregistered Images')

            with gr.Tab('Set Editor'):
                gr.Markdown('## Set Editor')
                gr.Markdown(
                    'Select a set to edit all images contained in it '
                    '(per-image rating, caption, prompt, labels).'
                )
                with gr.Row():
                    _set_editor_choices = self._set_names()
                    set_editor_name = gr.Dropdown(
                        label='Set',
                        choices=_set_editor_choices,
                        value='gts_v3' if 'gts_v3' in _set_editor_choices else None,
                        allow_custom_value=False,
                        interactive=True,
                    )
                with gr.Tabs():
                    with gr.Tab('Images'):
                        with gr.Row():
                            with gr.Column(scale=2):
                                with gr.Row():
                                    set_editor_rating_min = gr.Dropdown(
                                        label='Rating Min',
                                        choices=[
                                            str(x)
                                            for x in list(
                                                range(
                                                    SceneDef.RATING_MIN,
                                                    SceneDef.RATING_MAX + 1,
                                                )
                                            )
                                        ],
                                        value=f'{SceneDef.RATING_INIT}',
                                        allow_custom_value=False,
                                        interactive=True,
                                    )
                                    set_editor_rating_max = gr.Dropdown(
                                        label='Rating Max',
                                        choices=[
                                            str(x)
                                            for x in list(
                                                range(
                                                    SceneDef.RATING_MIN,
                                                    SceneDef.RATING_MAX + 1,
                                                )
                                            )
                                        ],
                                        value=f'{SceneDef.RATING_MAX}',
                                        allow_custom_value=False,
                                        interactive=True,
                                    )
                                with gr.Row():
                                    set_editor_show_active = gr.Checkbox(
                                        label='show active',
                                        value=True,
                                        interactive=True,
                                    )
                                    set_editor_show_prototype = gr.Checkbox(
                                        label='show prototypes',
                                        value=False,
                                        interactive=True,
                                    )
                                    set_editor_show_excluded = gr.Checkbox(
                                        label='show excluded',
                                        value=False,
                                        interactive=True,
                                    )
                                with gr.Row():
                                    set_editor_hints = gr.Dropdown(
                                        label='Hints',
                                        choices=['ignore', 'empty', 'set'],
                                        value='ignore',
                                        allow_custom_value=False,
                                        interactive=True,
                                    )
                                    set_editor_caption = gr.Dropdown(
                                        label='Caption',
                                        choices=['ignore', 'empty', 'set'],
                                        value='ignore',
                                        allow_custom_value=False,
                                        interactive=True,
                                    )
                                    set_editor_caption_joy = gr.Dropdown(
                                        label='Caption Joy',
                                        choices=['ignore', 'empty', 'set'],
                                        value='ignore',
                                        allow_custom_value=False,
                                        interactive=True,
                                    )
                                    set_editor_labels = gr.Dropdown(
                                        label='Labels',
                                        choices=['ignore', 'empty', 'set'],
                                        value='ignore',
                                        allow_custom_value=False,
                                        interactive=True,
                                    )
                            with gr.Column(scale=1):
                                set_editor_load_button = gr.Button(
                                    'Load',
                                    elem_id='set-editor-load-button',
                                )
                                set_editor_load_todo_button = gr.Button(
                                    'load todo 20'
                                )
                                set_editor_load_todo_low_button = gr.Button(
                                    'load todo 20 low'
                                )
                                set_editor_load_todo_ai_button = gr.Button(
                                    'load sugg 20'
                                )
                                set_editor_load_done_button = gr.Button(
                                    'load done'
                                )
                                set_editor_load_edit_button = gr.Button(
                                    'load edit 50'
                                )
                                set_editor_load_ood_cap_button = gr.Button(
                                    'load ood cap 50'
                                )
                                set_editor_caption_empty_button = gr.Button('caption')
                        set_editor_html = gr.HTML(label='Set Images')
                    with gr.Tab('Scenes'):
                        with gr.Row():
                            set_editor_scenes_load_button = gr.Button(
                                'Load',
                                elem_id='set-editor-scenes-load-button',
                            )
                        with gr.Row():
                            set_editor_scenes_show_active = gr.Checkbox(
                                label='show active',
                                value=True,
                                interactive=True,
                            )
                            set_editor_scenes_show_suppressed = gr.Checkbox(
                                label='show suppressed',
                                value=False,
                                interactive=True,
                            )
                            set_editor_scenes_show_prototype = gr.Checkbox(
                                label='show prototypes',
                                value=False,
                                interactive=True,
                            )
                            set_editor_scenes_show_excluded = gr.Checkbox(
                                label='show excluded',
                                value=False,
                                interactive=True,
                            )
                        set_editor_scenes_html = gr.HTML(label='Set Scenes')
                    with gr.Tab('Statistics'):
                        with gr.Row():
                            set_editor_stats_load_button = gr.Button(
                                'Load',
                                elem_id='set-editor-stats-load-button',
                            )
                        set_editor_stats_html = gr.HTML(label='Set Statistics')

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
            # The new scene id arrives via `databus_simg_editor`, not from
            # the textbox, so it's safe to wipe the textbox in the clear step.
            button_hidden_simg_editor_open.click(
                self._editor_clear_all,
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
            # scene id). Same clear-then-load pattern but the clear step
            # PRESERVES the scene-id textbox so the .then() step can read
            # it back as input.
            simg_editor_refresh_button.click(
                self._editor_clear_content,
                inputs=[simg_editor_scene_id],
                outputs=editor_outputs,
            ).then(
                self._html_simg_editor_open,
                inputs=[simg_editor_scene_id],
                outputs=editor_outputs,
            )

            simg_editor_go_button.click(
                self._editor_clear_content,
                inputs=[simg_editor_scene_id],
                outputs=editor_outputs,
            ).then(
                self._html_simg_editor_open,
                inputs=[simg_editor_scene_id],
                outputs=editor_outputs,
            )

            # Batch caption: for the currently-loaded scene, run JoySceneDB
            # ('1xlasm') on every registered image whose caption_joy is
            # empty, store each result to the DB, then refresh. Preserves
            # the scene-id textbox during the clear step (same reason).
            simg_editor_caption_empty_button.click(
                self._editor_clear_content,
                inputs=[simg_editor_scene_id],
                outputs=editor_outputs,
            ).then(
                self._html_simg_editor_caption_empty,
                inputs=[simg_editor_scene_id],
                outputs=editor_outputs,
            )

            # 'prototype all': flag every registered image of the loaded scene
            # as prototype, then refresh.
            simg_editor_prototype_all_button.click(
                self._editor_clear_content,
                inputs=[simg_editor_scene_id],
                outputs=editor_outputs,
            ).then(
                self._html_simg_editor_prototype_all,
                inputs=[simg_editor_scene_id],
                outputs=editor_outputs,
            )

            # Register an unregistered image (driven by per-image register button
            # in the unregistered-images section). Toast-only; no editor refresh
            # — the user can register multiple images quickly and refresh manually.
            button_hidden_simg_editor_register.click(
                self._html_simg_editor_register,
                inputs=[databus_simg_editor_register, simg_editor_scene_id],
                outputs=[],
                show_progress='hidden',
            )

            # Register an unregistered image as prototype (sets
            # `prototype: True` on the new SceneImage). Toast-only; no refresh.
            button_hidden_simg_editor_register_prototype.click(
                self._html_simg_editor_register_prototype,
                inputs=[
                    databus_simg_editor_register_prototype,
                    simg_editor_scene_id,
                ],
                outputs=[],
                show_progress='hidden',
            )

            # Caption an image (registered SceneImage via JoySceneDBNG /
            # legacy JoySceneDB, or an unregistered file via Joy directly).
            # The caption is copied to the clipboard. For non-clip flows the
            # backend force-stores caption_prompt (and caption_joy for the
            # 1xlasm skin); the JSON written to the out-databus drives a JS
            # .then() callback that mirrors those writes into the per-cell
            # textareas so the DOM matches the DB without a manual reload.
            button_hidden_simg_editor_caption.click(
                self._html_simg_editor_caption,
                inputs=[databus_simg_editor_caption],
                outputs=[databus_simg_editor_caption_out],
            ).then(
                fn=None,
                inputs=[databus_simg_editor_caption_out],
                outputs=None,
                js="""
                (resultStr) => {
                    if (!resultStr) return;
                    let data;
                    try { data = JSON.parse(resultStr); } catch (e) { return; }
                    if (!data || !data.image_id) return;
                    if (typeof data.caption_joy === 'string') {
                        const cj = document.getElementById('simg-set_caption_joy-' + data.image_id);
                        if (cj) {
                            cj.value = data.caption_joy;
                            const f = cj.closest('.simg-edit-field');
                            if (f) f.classList.remove('simg-stale');
                        }
                    }
                    if (typeof data.caption_prompt === 'string') {
                        const cp = document.getElementById('simg-set_caption_prompt-' + data.image_id);
                        if (cp) {
                            cp.value = data.caption_prompt;
                            const f = cp.closest('.simg-edit-field');
                            if (f) f.classList.remove('simg-stale');
                        }
                    }
                }
                """,
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

            # Per-cell server refresh: re-renders one image cell server-side
            # and swaps the matching DOM element by id. Use after any mutation
            # that should be reflected in the cell's rendered state (label
            # highlights, exclude/prototype frames, etc.).
            button_hidden_cell_refresh.click(
                self._html_cell_refresh,
                inputs=[databus_cell_refresh_in],
                outputs=[databus_cell_refresh_out],
            ).then(
                fn=None,
                inputs=[databus_cell_refresh_out],
                outputs=None,
                js="""
                (resultStr) => {
                    if (!resultStr) return;
                    let data;
                    try { data = JSON.parse(resultStr); } catch (e) { return; }
                    if (!data || !data.target_id || !data.html) return;
                    const target = document.getElementById(data.target_id);
                    if (!target) return;
                    const tmp = document.createElement('div');
                    tmp.innerHTML = data.html.trim();
                    const newCell = tmp.firstElementChild;
                    if (newCell) target.replaceWith(newCell);
                }
                """,
            )

            # Lightbox: thumbnail click -> server reads the full image and
            # returns a JSON payload `{b64, type, image_id?, caption?}`.
            # The JS .then() callback decodes it, sets the modal image,
            # populates the editable caption textarea (registered only) and
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
                (resultStr) => {
                    if (!resultStr) return;
                    let data;
                    try { data = JSON.parse(resultStr); } catch (e) { return; }
                    if (!data || !data.b64) return;

                    const img      = document.getElementById('simg-lightbox-img');
                    const overlay  = document.getElementById('simg-lightbox-overlay');
                    const caption  = document.getElementById('simg-lightbox-caption');
                    const proto    = document.getElementById('simg-lightbox-prototype');
                    const excl     = document.getElementById('simg-lightbox-exclude');
                    if (!img || !overlay) return;

                    img.src = 'data:image/png;base64,' + data.b64;

                    const content = overlay.querySelector('.simg-lightbox-content');
                    if (data.type === 'registered' && data.image_id) {
                        overlay.dataset.targetType = 'registered';
                        overlay.dataset.imageId = data.image_id;
                        overlay.dataset.setId = data.set_id || '';
                        if (caption) { caption.value = data.caption || ''; }
                        if (content) { content.classList.add('simg-lightbox-with-caption'); }
                        if (proto) {
                            proto.checked = !!data.prototype;
                            const pp = proto.closest('label');
                            if (pp) { pp.style.display = 'inline-flex'; }
                        }
                        if (excl) {
                            const ep = excl.closest('label');
                            if (data.set_id) {
                                excl.checked = !!data.excluded;
                                if (ep) { ep.style.display = 'inline-flex'; }
                            } else {
                                excl.checked = false;
                                if (ep) { ep.style.display = 'none'; }
                            }
                        }
                    } else {
                        overlay.dataset.targetType = data.type || '';
                        overlay.dataset.imageId = '';
                        overlay.dataset.setId = '';
                        if (caption) { caption.value = ''; }
                        if (content) { content.classList.remove('simg-lightbox-with-caption'); }
                        if (proto) {
                            proto.checked = false;
                            const pp = proto.closest('label');
                            if (pp) { pp.style.display = 'none'; }
                        }
                        if (excl) {
                            excl.checked = false;
                            const ep = excl.closest('label');
                            if (ep) { ep.style.display = 'none'; }
                        }
                    }

                    overlay.style.display = 'flex';
                }
                """,
            )

            set_editor_filter_inputs = [
                set_editor_name,
                set_editor_rating_min,
                set_editor_rating_max,
                set_editor_hints,
                set_editor_caption,
                set_editor_caption_joy,
                set_editor_labels,
                set_editor_show_active,
                set_editor_show_prototype,
                set_editor_show_excluded,
            ]

            set_editor_load_button.click(
                lambda: '',
                inputs=[],
                outputs=[set_editor_html],
            ).then(
                self._html_set_editor_open,
                inputs=set_editor_filter_inputs,
                outputs=[set_editor_html],
            )

            set_editor_caption_empty_button.click(
                lambda: '',
                inputs=[],
                outputs=[set_editor_html],
            ).then(
                self._html_set_editor_caption_empty,
                inputs=set_editor_filter_inputs,
                outputs=[set_editor_html],
            )

            set_editor_load_todo_button.click(
                lambda: '',
                inputs=[],
                outputs=[set_editor_html],
            ).then(
                self._html_set_editor_open_todo,
                inputs=[set_editor_name],
                outputs=[set_editor_html],
            )

            set_editor_load_todo_low_button.click(
                lambda: '',
                inputs=[],
                outputs=[set_editor_html],
            ).then(
                self._html_set_editor_open_todo_low,
                inputs=[set_editor_name],
                outputs=[set_editor_html],
            )

            set_editor_load_todo_ai_button.click(
                lambda: '',
                inputs=[],
                outputs=[set_editor_html],
            ).then(
                self._html_set_editor_open_todo_ai,
                inputs=[set_editor_name],
                outputs=[set_editor_html],
            )

            set_editor_load_done_button.click(
                lambda: '',
                inputs=[],
                outputs=[set_editor_html],
            ).then(
                self._html_set_editor_open_done,
                inputs=[set_editor_name],
                outputs=[set_editor_html],
            )

            set_editor_load_edit_button.click(
                lambda: '',
                inputs=[],
                outputs=[set_editor_html],
            ).then(
                self._html_set_editor_open_edit,
                inputs=[set_editor_name],
                outputs=[set_editor_html],
            )

            set_editor_load_ood_cap_button.click(
                lambda: '',
                inputs=[],
                outputs=[set_editor_html],
            ).then(
                self._html_set_editor_open_ood_cap,
                inputs=[set_editor_name],
                outputs=[set_editor_html],
            )

            set_editor_scenes_load_button.click(
                lambda: '',
                inputs=[],
                outputs=[set_editor_scenes_html],
            ).then(
                self._html_set_editor_open_scenes,
                inputs=[
                    set_editor_name,
                    set_editor_scenes_show_active,
                    set_editor_scenes_show_suppressed,
                    set_editor_scenes_show_prototype,
                    set_editor_scenes_show_excluded,
                ],
                outputs=[set_editor_scenes_html],
            )

            set_editor_stats_load_button.click(
                lambda: '',
                inputs=[],
                outputs=[set_editor_stats_html],
            ).then(
                self._html_set_editor_open_stats,
                inputs=[set_editor_name],
                outputs=[set_editor_stats_html],
            )

        return if_app

    def _set_names(self) -> list[str]:
        names: list[str] = []
        for sid in self._ssm.ids:
            data = self._ssm.data_from_id(sid)
            if not data:
                continue
            name = data.get(SceneDef.FIELD_NAME)
            if isinstance(name, str) and name:
                names.append(name)
        names.sort()
        return names

    def _set_editor_filter_imgs(
        self,
        scene_set,
        rating_min: Optional[str],
        rating_max: Optional[str],
        hints_mode: Optional[str],
        caption_mode: Optional[str],
        caption_joy_mode: Optional[str],
        labels_mode: Optional[str],
        show_excluded: bool = False,
    ) -> list:
        r_min = int(rating_min) if rating_min is not None else SceneDef.RATING_MIN
        r_max = int(rating_max) if rating_max is not None else SceneDef.RATING_MAX

        field_modes = [
            (SceneDef.FIELD_HINTS, hints_mode),
            (SceneDef.FIELD_CAPTION, caption_mode),
            (SceneDef.FIELD_CAPTION_JOY, caption_joy_mode),
            (SceneDef.FIELD_LABELS, labels_mode),
        ]

        if show_excluded:
            simg_mgr = self._scm.scene_image_manager()
            imgs_iter: list = []
            for iid in scene_set.imgs_exclude:
                try:
                    imgs_iter.append(simg_mgr.image_from_id_or_url(iid))
                except Exception:
                    continue
        else:
            imgs_iter = scene_set.imgs

        out = []
        for img in imgs_iter:
            rating = img.data.get(SceneDef.FIELD_RATING, SceneDef.RATING_MIN)
            if not (r_min <= rating <= r_max):
                continue
            ok = True
            for field, mode in field_modes:
                if mode is None or mode == 'ignore':
                    continue
                is_empty = not img.data.get(field)
                if mode == 'empty' and not is_empty:
                    ok = False
                    break
                if mode == 'set' and is_empty:
                    ok = False
                    break
            if ok:
                out.append(img)
        return out

    def _html_set_editor_open(
        self,
        name: Optional[str],
        rating_min: Optional[str],
        rating_max: Optional[str],
        hints_mode: Optional[str] = 'ignore',
        caption_mode: Optional[str] = 'ignore',
        caption_joy_mode: Optional[str] = 'ignore',
        labels_mode: Optional[str] = 'ignore',
        show_active: bool = True,
        show_prototype: bool = False,
        show_excluded: bool = False,
    ) -> str:
        if not name or not isinstance(name, str):
            return '<p>No set selected.</p>'
        try:
            scene_set = self._ssm.set_from_id_or_name(name)
        except Exception as e:
            return f'<p>Failed to load set <code>{name}</code>: {e}</p>'

        try:
            imgs_non_excluded_all = self._set_editor_filter_imgs(
                scene_set, rating_min, rating_max,
                hints_mode, caption_mode, caption_joy_mode, labels_mode,
                show_excluded=False,
            )
            imgs_active = (
                [i for i in imgs_non_excluded_all if not i.prototype]
                if show_active else []
            )
            imgs_prototype = (
                [i for i in imgs_non_excluded_all if i.prototype]
                if show_prototype else []
            )
            imgs_excluded = self._set_editor_filter_imgs(
                scene_set, rating_min, rating_max,
                hints_mode, caption_mode, caption_joy_mode, labels_mode,
                show_excluded=True,
            ) if show_excluded else []
        except Exception as e:
            return f'<p>Failed to list images for set <code>{name}</code>: {e}</p>'

        if not imgs_active and not imgs_prototype and not imgs_excluded:
            return (
                f'<p>Set <code>{name}</code> contains no images matching the current filter.</p>'
            )

        styles = AppSceneImageCell.html_styles() + """
        <style>
            .set-editor-img-excluded {
                outline: 2px dashed #b91c1c;
                outline-offset: -2px;
                opacity: 0.6;
            }
            .set-editor-img-prototype {
                outline: 2px dashed #2563eb;
                outline-offset: -2px;
            }
        </style>
        """
        excluded_ids = set(scene_set.imgs_exclude)

        parts = [styles]
        if imgs_active:
            cells_a = ''.join(
                AppSceneImageCell.html(
                    img, set_id=scene_set.id, excluded=img.id in excluded_ids
                )
                for img in imgs_active
            )
            parts.append(AppHtml.html_styled_cells_grid(cells_a, columns=1))
        if imgs_prototype:
            cells_p = ''.join(
                f'<div class="set-editor-img-prototype">'
                f'{AppSceneImageCell.html_info(img, set_id=scene_set.id, excluded=img.id in excluded_ids)}'
                f'</div>'
                for img in imgs_prototype
            )
            parts.append(
                '<h3 style="margin-top:24px;color:#2563eb;">Prototype</h3>'
            )
            parts.append(AppHtml.html_styled_cells_grid(cells_p, columns=4))
        if imgs_excluded:
            cells_e = ''.join(
                f'<div class="set-editor-img-excluded">'
                f'{AppSceneImageCell.html_info(img, set_id=scene_set.id, excluded=True)}'
                f'</div>'
                for img in imgs_excluded
            )
            parts.append(
                '<h3 style="margin-top:24px;color:#b91c1c;">Excluded</h3>'
            )
            parts.append(AppHtml.html_styled_cells_grid(cells_e, columns=4))
        return ''.join(parts)

    def _html_set_editor_caption_empty(
        self,
        name: Optional[str],
        rating_min: Optional[str],
        rating_max: Optional[str],
        hints_mode: Optional[str] = 'ignore',
        caption_mode: Optional[str] = 'ignore',
        caption_joy_mode: Optional[str] = 'ignore',
        labels_mode: Optional[str] = 'ignore',
        show_active: bool = True,
        show_prototype: bool = False,
        show_excluded: bool = False,
    ) -> str:
        """
        Set-level batch caption: re-runs JoyCaptionNG on every filtered
        ACTIVE image in the selected set whose stored `caption_prompt` is
        non-empty AND newer than its `caption_joy` (or where `caption_joy`
        is empty). Images with empty `caption_prompt` are skipped — the
        compile step (`/imgs_update_caption_prompt`) is the upstream that
        populates this field. Excluded images are never captioned.
        """
        refresh_args = (
            name, rating_min, rating_max,
            hints_mode, caption_mode, caption_joy_mode, labels_mode,
            show_active, show_prototype, show_excluded,
        )
        if not name or not isinstance(name, str):
            gr.Warning('No set selected.')
            return self._html_set_editor_open(*refresh_args)

        try:
            scene_set = self._ssm.set_from_id_or_name(name)
        except Exception as e:
            print(f'ERROR: caption-empty load set [{name}]: {e}')
            gr.Warning(f'Failed to load set: {e}')
            return self._html_set_editor_open(*refresh_args)

        try:
            imgs_filtered = self._set_editor_filter_imgs(
                scene_set, rating_min, rating_max,
                hints_mode, caption_mode, caption_joy_mode, labels_mode,
                show_excluded=False,
            )
            ids_empty: list[str] = []
            for img in imgs_filtered:
                d = img.data
                cprompt = (d.get(SceneDef.FIELD_CAPTION_PROMPT) or '').strip()
                if not cprompt:
                    continue   # skip: no compiled prompt, nothing to caption against
                cjoy = (d.get(SceneDef.FIELD_CAPTION_JOY) or '').strip()
                if not cjoy:
                    ids_empty.append(img.id)
                    continue
                ts_p = d.get(SceneDef.FIELD_TIMESTAMP_CAPTION_PROMPT)
                ts_j = d.get(SceneDef.FIELD_TIMESTAMP_CAPTION_JOY)
                # Only re-caption when the prompt is genuinely newer.
                # Missing prompt-timestamp + present caption_joy → assume
                # the prompt was set BEFORE we started timestamping it
                # (legacy migration backfill); skip rather than re-run.
                if ts_p is None:
                    continue
                if ts_j is None or ts_p > ts_j:
                    ids_empty.append(img.id)
        except Exception as e:
            print(f'ERROR: caption-empty filter set [{name}]: {e}')
            gr.Warning(f'Failed to filter images: {e}')
            return self._html_set_editor_open(*refresh_args)

        if not ids_empty:
            gr.Info(
                'No filtered images need captioning '
                '(caption_prompt empty or older than caption_joy).'
            )
            return self._html_set_editor_open(*refresh_args)

        gr.Info(
            f"Batch captioning {len(ids_empty)} image(s) with skin '1xlasm'...",
            duration=3.0,
        )

        cfg_name = self._scm._dbc.config.config
        sim = self._scm.scene_image_manager()
        jdb: Any = None
        n_done = 0
        n_failed = 0
        try:
            from ait.caption.joy_scenedb_ng import JoySceneDBNG
            jdb = JoySceneDBNG(
                config=cfg_name,
                skin='1xlasm',
                verbose=1,
                force=True,
            )
            for img_id in ids_empty:
                try:
                    prompt, caption = jdb.caption_image(img_id)
                except Exception as e:
                    print(f'ERROR: caption-empty inference [{img_id}]: {e}')
                    n_failed += 1
                    continue
                if not caption:
                    print(f'WARN: caption-empty produced no caption for [{img_id}]')
                    n_failed += 1
                    continue
                try:
                    simg = sim.image_from_id_or_url(img_id)
                    simg.set_caption_joy(caption)
                    if prompt:
                        simg.set_caption_prompt(prompt)
                    simg.db_store()
                    n_done += 1
                except Exception as e:
                    print(f'ERROR: caption-empty store [{img_id}]: {e}')
                    n_failed += 1
        except Exception as e:
            print(f'ERROR: caption-empty batch run: {e}')
            gr.Warning(f'Batch caption failed: {e}')
        finally:
            if jdb is not None:
                self._release_gpu(jdb)

        n_skipped = len(ids_empty) - n_done - n_failed
        msg_parts = [f'Captioned {n_done}']
        if n_skipped > 0:
            msg_parts.append(f'skipped {n_skipped}')
        if n_failed > 0:
            msg_parts.append(f'failed {n_failed}')
        msg = ', '.join(msg_parts) + '.'
        if n_done > 0:
            gr.Info(msg, duration=3.0)
        elif n_failed > 0:
            gr.Warning(msg)
        else:
            gr.Info(msg)

        return self._html_set_editor_open(*refresh_args)

    def _html_set_editor_open_todo(self, name: Optional[str]) -> str:
        """
        Loads up to 20 'todo' images of the selected set as edit cells.

        Todoness is a priority code derived from emptiness of the four
        editable fields, weighted so the order is
            hints (8) > labels (4) > caption_joy (2) > caption (1)
        i.e. an image with empty hints always ranks above one whose hints
        is set, regardless of the other three fields. Range 0..15; images
        with todoness 0 are skipped. Within the same todoness, sort by
        latest update / creation timestamp desc. Prototype and excluded
        images are skipped.
        """
        if not name or not isinstance(name, str):
            return '<p>No set selected.</p>'
        try:
            scene_set = self._ssm.set_from_id_or_name(name)
        except Exception as e:
            return f'<p>Failed to load set <code>{name}</code>: {e}</p>'

        try:
            scored: list[tuple[int, float, object]] = []
            for img in scene_set.imgs:
                if img.prototype:
                    continue
                d = img.data
                empty_hints = not d.get(SceneDef.FIELD_HINTS)
                empty_labels = not d.get(SceneDef.FIELD_LABELS)
                empty_caption_joy = not d.get(SceneDef.FIELD_CAPTION_JOY)
                empty_caption = not d.get(SceneDef.FIELD_CAPTION)
                todoness = (
                    int(empty_hints) * 8
                    + int(empty_labels) * 4
                    + int(empty_caption_joy) * 2
                    + int(empty_caption) * 1
                )
                if todoness == 0:
                    continue
                ts = SceneDef.get_timestamp_update_from_data(img)
                scored.append((todoness, ts, img))
        except Exception as e:
            return f'<p>Failed to scan images for set <code>{name}</code>: {e}</p>'

        if not scored:
            return f'<p>Set <code>{name}</code>: no todo images.</p>'

        scored.sort(key=lambda t: (-t[0], -t[1]))
        scored = scored[:20]

        styles = AppSceneImageCell.html_styles()
        excluded_ids = set(scene_set.imgs_exclude)
        cells = ''.join(
            AppSceneImageCell.html(
                img, set_id=scene_set.id, excluded=img.id in excluded_ids
            )
            for _, _, img in scored
        )
        return styles + AppHtml.html_styled_cells_grid(cells, columns=1)

    def _html_set_editor_open_todo_low(self, name: Optional[str]) -> str:
        """
        Loads up to 20 'todo' images of the selected set, lowest todoness
        first ("almost done"). Same scoring as `_html_set_editor_open_todo`
        but ascending sort: an image with only `caption` empty (todoness 1)
        ranks above one with everything empty (todoness 15). Within the
        same todoness, latest update / creation timestamp desc. Prototype
        and excluded images are skipped; todoness 0 is excluded.
        """
        if not name or not isinstance(name, str):
            return '<p>No set selected.</p>'
        try:
            scene_set = self._ssm.set_from_id_or_name(name)
        except Exception as e:
            return f'<p>Failed to load set <code>{name}</code>: {e}</p>'

        try:
            scored: list[tuple[int, float, object]] = []
            for img in scene_set.imgs:
                if img.prototype:
                    continue
                d = img.data
                empty_hints = not d.get(SceneDef.FIELD_HINTS)
                empty_labels = not d.get(SceneDef.FIELD_LABELS)
                empty_caption_joy = not d.get(SceneDef.FIELD_CAPTION_JOY)
                empty_caption = not d.get(SceneDef.FIELD_CAPTION)
                todoness = (
                    int(empty_hints) * 8
                    + int(empty_labels) * 4
                    + int(empty_caption_joy) * 2
                    + int(empty_caption) * 1
                )
                if todoness == 0:
                    continue
                ts = SceneDef.get_timestamp_update_from_data(img)
                scored.append((todoness, ts, img))
        except Exception as e:
            return f'<p>Failed to scan images for set <code>{name}</code>: {e}</p>'

        if not scored:
            return f'<p>Set <code>{name}</code>: no todo images.</p>'

        # Ascending todoness (lowest first), tiebreak: most recent first.
        scored.sort(key=lambda t: (t[0], -t[1]))
        scored = scored[:20]

        styles = AppSceneImageCell.html_styles()
        excluded_ids = set(scene_set.imgs_exclude)
        cells = ''.join(
            AppSceneImageCell.html(
                img, set_id=scene_set.id, excluded=img.id in excluded_ids
            )
            for _, _, img in scored
        )
        return styles + AppHtml.html_styled_cells_grid(cells, columns=1)

    def _html_set_editor_open_todo_ai(self, name: Optional[str]) -> str:
        """
        Loads up to 20 active (non-prototype) images from the selected
        set that need curator review:

          - have non-empty `_SUGGESTION` fields (labels or hints), AND
          - canonical `labels_ng` AND `hints` are still empty
            (suggestions haven't been promoted yet).

        Sorted by newest image creation timestamp first. This narrows the
        list to images where /img_suggest has run but the curator hasn't
        yet reviewed — exactly the queue for the curator-review step of
        the workflow.

        (Function name is legacy — the button now reads "load sugg 20".)
        """
        if not name or not isinstance(name, str):
            return '<p>No set selected.</p>'
        try:
            scene_set = self._ssm.set_from_id_or_name(name)
        except Exception as e:
            return f'<p>Failed to load set <code>{name}</code>: {e}</p>'

        excluded_ids = set(scene_set.imgs_exclude)
        pending: list[tuple[float, object]] = []
        for img in scene_set.imgs:
            if img.prototype:
                continue
            # Canonical fields must be blank — already-curated images are
            # excluded so the queue only shows actionable items.
            if img.labels_ng:
                continue
            if (img.hints or '').strip():
                continue
            # Must have at least one _SUGGESTION field populated.
            labels_sug = img.labels_ng_suggestion or []
            hint_sug = (img.hints_suggestion or '').strip()
            if not labels_sug and not hint_sug:
                continue
            ts_created = img.data.get(SceneDef.FIELD_TIMESTAMP_CREATED, 0) or 0
            pending.append((ts_created, img))

        pending.sort(key=lambda t: -t[0])
        top = pending[:20]

        if not top:
            return (
                f'<p>No pending suggestions to review in set '
                f'<code>{name}</code>. (Looking for images with '
                f'<code>_SUGGESTION</code> populated AND canonical '
                f'<code>labels_ng</code>/<code>hints</code> still blank.) '
                f'Run <code>/img_suggest &lt;id&gt;</code> on blank '
                f'images, then refresh.</p>'
            )

        cells_parts: list[str] = []
        for _, img in top:
            cells_parts.append(
                AppSceneImageCell.html(
                    img, set_id=scene_set.id, excluded=img.id in excluded_ids
                )
            )

        header = (
            f'<p style="color:#888;font-size:0.85em;margin:0 0 6px 0;">'
            f'Pending review in set <code>{name}</code>: '
            f'showing {len(cells_parts)} of {len(pending)} '
            f'(active imgs with _SUGGESTION set + canonical labels/hints '
            f'empty; sorted by newest image first).</p>'
        )
        styles = AppSceneImageCell.html_styles()
        return styles + header + AppHtml.html_styled_cells_grid(''.join(cells_parts), columns=1)

    def _html_set_editor_open_done(self, name: Optional[str]) -> str:
        """
        Loads ALL 'done' active images of the selected set as edit cells.
        Done = all four editable fields (hints, labels, caption_joy,
        caption) are non-empty. Prototype and excluded images are
        skipped. Sorted by latest update / creation timestamp desc.
        """
        if not name or not isinstance(name, str):
            return '<p>No set selected.</p>'
        try:
            scene_set = self._ssm.set_from_id_or_name(name)
        except Exception as e:
            return f'<p>Failed to load set <code>{name}</code>: {e}</p>'

        try:
            done: list[tuple[float, object]] = []
            for img in scene_set.imgs:
                if img.prototype:
                    continue
                d = img.data
                if not d.get(SceneDef.FIELD_HINTS):
                    continue
                if not d.get(SceneDef.FIELD_LABELS):
                    continue
                if not d.get(SceneDef.FIELD_CAPTION_JOY):
                    continue
                if not d.get(SceneDef.FIELD_CAPTION):
                    continue
                ts = SceneDef.get_timestamp_update_from_data(img)
                done.append((ts, img))
        except Exception as e:
            return f'<p>Failed to scan images for set <code>{name}</code>: {e}</p>'

        if not done:
            return f'<p>Set <code>{name}</code>: no done images.</p>'

        done.sort(key=lambda t: -t[0])

        styles = AppSceneImageCell.html_styles()
        excluded_ids = set(scene_set.imgs_exclude)
        cells = ''.join(
            AppSceneImageCell.html(
                img, set_id=scene_set.id, excluded=img.id in excluded_ids
            )
            for _, img in done
        )
        return styles + AppHtml.html_styled_cells_grid(cells, columns=1)

    def _html_set_editor_open_edit(self, name: Optional[str]) -> str:
        """
        Loads the 50 most recently edited active images of the selected set.
        An image counts as edited when at least one of its editable fields
        (hints, labels, caption_joy, caption) is non-empty. Sorted by latest
        update / creation timestamp desc. Prototype images are skipped;
        excluded images are already filtered by `scene_set.imgs`.
        """
        if not name or not isinstance(name, str):
            return '<p>No set selected.</p>'
        try:
            scene_set = self._ssm.set_from_id_or_name(name)
        except Exception as e:
            return f'<p>Failed to load set <code>{name}</code>: {e}</p>'

        try:
            edited: list[tuple[float, object]] = []
            for img in scene_set.imgs:
                if img.prototype:
                    continue
                d = img.data
                if not (
                    d.get(SceneDef.FIELD_HINTS)
                    or d.get(SceneDef.FIELD_LABELS)
                    or d.get(SceneDef.FIELD_CAPTION_JOY)
                    or d.get(SceneDef.FIELD_CAPTION)
                ):
                    continue
                ts = SceneDef.get_timestamp_update_from_data(img)
                edited.append((ts, img))
        except Exception as e:
            return f'<p>Failed to scan images for set <code>{name}</code>: {e}</p>'

        if not edited:
            return f'<p>Set <code>{name}</code>: no edited images.</p>'

        edited.sort(key=lambda t: -t[0])
        edited = edited[:50]

        styles = AppSceneImageCell.html_styles()
        excluded_ids = set(scene_set.imgs_exclude)
        cells = ''.join(
            AppSceneImageCell.html(
                img, set_id=scene_set.id, excluded=img.id in excluded_ids
            )
            for _, img in edited
        )
        return styles + AppHtml.html_styled_cells_grid(cells, columns=1)

    def _html_set_editor_open_ood_cap(self, name: Optional[str]) -> str:
        """
        Loads the 50 active images whose `caption` is out-of-date relative
        to `caption_joy` — i.e. `timestamp_caption_joy > timestamp_caption`,
        with both fields non-empty. Sorted by `rating` ascending (lowest
        ranked first — they need attention soonest), tiebreak by
        `timestamp_caption_joy` desc (most recently regenerated first).
        Prototype images are skipped; excluded images are already filtered
        by `scene_set.imgs`.
        """
        if not name or not isinstance(name, str):
            return '<p>No set selected.</p>'
        try:
            scene_set = self._ssm.set_from_id_or_name(name)
        except Exception as e:
            return f'<p>Failed to load set <code>{name}</code>: {e}</p>'

        try:
            ood: list[tuple[int, float, object]] = []
            for img in scene_set.imgs:
                if img.prototype:
                    continue
                d = img.data
                if not d.get(SceneDef.FIELD_CAPTION):
                    continue
                if not d.get(SceneDef.FIELD_CAPTION_JOY):
                    continue
                ts_cap = d.get(SceneDef.FIELD_TIMESTAMP_CAPTION) or 0.0
                ts_cap_joy = d.get(SceneDef.FIELD_TIMESTAMP_CAPTION_JOY) or 0.0
                if ts_cap_joy <= ts_cap:
                    continue
                rating = d.get(SceneDef.FIELD_RATING, SceneDef.RATING_INIT)
                ood.append((rating, ts_cap_joy, img))
        except Exception as e:
            return f'<p>Failed to scan images for set <code>{name}</code>: {e}</p>'

        if not ood:
            return f'<p>Set <code>{name}</code>: no out-of-date captions.</p>'

        # Lower rating first; within same rating, more recently regenerated first.
        ood.sort(key=lambda t: (t[0], -t[1]))
        ood = ood[:50]

        styles = AppSceneImageCell.html_styles()
        excluded_ids = set(scene_set.imgs_exclude)
        cells = ''.join(
            AppSceneImageCell.html(
                img, set_id=scene_set.id, excluded=img.id in excluded_ids
            )
            for _, _, img in ood
        )
        return styles + AppHtml.html_styled_cells_grid(cells, columns=1)

    def _html_set_editor_open_scenes(
        self,
        name: Optional[str],
        show_active: bool = True,
        show_suppressed: bool = False,
        show_prototype: bool = False,
        show_excluded: bool = False,
    ) -> str:
        if not name or not isinstance(name, str):
            return '<p>No set selected.</p>'
        try:
            scene_set = self._ssm.set_from_id_or_name(name)
        except Exception as e:
            return f'<p>Failed to load set <code>{name}</code>: {e}</p>'

        scm = self._scm
        try:
            all_ids = list(scm.ids_from_query(scene_set.query))
        except Exception as e:
            return f'<p>Failed to enumerate scenes for set <code>{name}</code>: {e}</p>'

        scenes = []
        for sid in all_ids:
            try:
                sc = scm.scene_from_id_or_url(sid)
            except Exception:
                continue
            if sc is not None:
                scenes.append(sc)

        if not scenes:
            return f'<p>Set <code>{name}</code> contains no scenes.</p>'

        try:
            suppressed = set(scene_set.ids_scene_surpressed)
        except Exception:
            suppressed = set()
        removed = set(scene_set.scenes_exclude)

        SceneDef.sort_by_rating(scenes)
        prototype_ids: set[str] = set()
        for s in scenes:
            try:
                if s.is_prototype:
                    prototype_ids.add(s.id)
            except Exception:
                pass
        top = [
            s for s in scenes
            if s.id not in suppressed and s.id not in removed
        ]
        proto = [
            s for s in scenes
            if s.id in prototype_ids and s.id not in removed
        ]
        # Suppressed: non-prototype suppressed first (rating-sorted), then
        # prototype scenes appended at the end. Prototype scenes are by
        # definition suppressed (all images non-active); listing them here
        # too keeps the suppressed section complete (intentional duplication
        # with the Prototype section).
        supp_non_proto = [
            s for s in scenes
            if s.id in suppressed
            and s.id not in prototype_ids
            and s.id not in removed
        ]
        supp = supp_non_proto + proto
        excl = [s for s in scenes if s.id in removed]

        def render(scene) -> str:
            chk = AppSceneImageCell.html_scene_exclude_checkbox(
                set_id=scene_set.id,
                scene_id=scene.id,
                checked=scene.id in removed,
            )
            cell = AppSceneCell.html(scene, 'info', extras_below_image=chk)
            if scene.id in suppressed or scene.id in removed:
                wrap_cls = 'set-editor-scene-wrap'
                if scene.id in suppressed:
                    wrap_cls += ' set-editor-scene-suppressed'
                if scene.id in removed:
                    wrap_cls += ' set-editor-scene-excluded'
                return f'<div class="{wrap_cls}">{cell}</div>'
            return cell

        cells_non = ''.join(render(s) for s in top) if show_active else ''
        cells_proto = ''.join(render(s) for s in proto) if show_prototype else ''
        cells_supp = ''.join(render(s) for s in supp) if show_suppressed else ''
        cells_excl = ''.join(render(s) for s in excl) if show_excluded else ''

        styles = AppSceneImageCell.html_styles() + """
        <style>
            .scene-cell-extras {
                display: flex;
                justify-content: center;
                padding: 6px 4px 4px 4px;
            }
            .set-editor-scene-suppressed {
                outline: 2px dashed #d97706;
                outline-offset: -2px;
                opacity: 0.65;
            }
            .set-editor-scene-excluded {
                outline: 2px dashed #b91c1c;
                outline-offset: -2px;
                opacity: 0.55;
            }
        </style>
        """

        parts = [styles]
        if cells_non:
            parts.append(AppHtml.html_styled_cells_grid(cells_non))
        if cells_supp:
            parts.append(
                '<h3 style="margin-top:24px;color:#d97706;">Suppressed</h3>'
            )
            parts.append(AppHtml.html_styled_cells_grid(cells_supp))
        if cells_proto:
            parts.append(
                '<h3 style="margin-top:24px;color:#2563eb;">Prototype</h3>'
            )
            parts.append(AppHtml.html_styled_cells_grid(cells_proto))
        if cells_excl:
            parts.append(
                '<h3 style="margin-top:24px;color:#b91c1c;">Excluded</h3>'
            )
            parts.append(AppHtml.html_styled_cells_grid(cells_excl))
        return ''.join(parts)

    def _html_set_editor_open_stats(self, name: Optional[str]) -> str:
        """
        Renders aggregate counts for the selected set: scenes split by
        bucket (active / prototype / suppressed / excluded) and images
        split by bucket (active / prototype / excluded), plus a small
        todoness breakdown across active images.
        """
        if not name or not isinstance(name, str):
            return '<p>No set selected.</p>'
        try:
            scene_set = self._ssm.set_from_id_or_name(name)
        except Exception as e:
            return f'<p>Failed to load set <code>{name}</code>: {e}</p>'

        try:
            removed_scene_ids = set(scene_set.scenes_exclude)
            scm = self._scm
            all_scene_ids = list(scm.ids_from_query(scene_set.query))
        except Exception as e:
            return f'<p>Failed to enumerate scenes for set <code>{name}</code>: {e}</p>'

        n_scenes_total = len(all_scene_ids)
        n_scenes_excluded = len(
            [sid for sid in all_scene_ids if sid in removed_scene_ids]
        )
        try:
            suppressed_ids = set(scene_set.ids_scene_surpressed)
        except Exception:
            suppressed_ids = set()
        n_scenes_suppressed = len(suppressed_ids)

        n_scenes_prototype = 0
        for sid in all_scene_ids:
            if sid in removed_scene_ids:
                continue
            try:
                sc = scm.scene_from_id_or_url(sid)
            except Exception:
                continue
            if sc is not None and sc.is_prototype:
                n_scenes_prototype += 1

        n_scenes_active = (
            n_scenes_total - n_scenes_excluded - n_scenes_suppressed
        )

        # Image-level counts (driven by the set's iteration semantics).
        n_imgs_excluded = len(scene_set.imgs_exclude)
        n_imgs_active = 0
        n_imgs_prototype = 0
        n_imgs_total_in_scenes = 0
        todoness_buckets = {
            'caption': 0,
            'caption_joy': 0,
            'labels': 0,
            'hints': 0,
        }
        rating_counts: dict[int, int] = {
            r: 0 for r in range(SceneDef.RATING_MIN, SceneDef.RATING_MAX + 1)
        }
        n_imgs_unrated = 0
        for img in scene_set.imgs:
            n_imgs_total_in_scenes += 1
            if img.prototype:
                n_imgs_prototype += 1
                continue
            n_imgs_active += 1
            d = img.data
            if not d.get(SceneDef.FIELD_HINTS):
                todoness_buckets['hints'] += 1
            if not d.get(SceneDef.FIELD_LABELS):
                todoness_buckets['labels'] += 1
            if not d.get(SceneDef.FIELD_CAPTION_JOY):
                todoness_buckets['caption_joy'] += 1
            if not d.get(SceneDef.FIELD_CAPTION):
                todoness_buckets['caption'] += 1
            r_raw = d.get(SceneDef.FIELD_RATING)
            if r_raw is None:
                n_imgs_unrated += 1
            else:
                try:
                    ri = int(r_raw)
                    if ri in rating_counts:
                        rating_counts[ri] += 1
                    else:
                        n_imgs_unrated += 1
                except Exception:
                    n_imgs_unrated += 1

        def row(label: str, value, color: str = '#cccccc') -> str:
            return (
                f'<tr><td style="padding:4px 12px;color:{color};">{label}</td>'
                f'<td style="padding:4px 12px;text-align:right;color:#fff;'
                f'font-variant-numeric:tabular-nums;">{value}</td></tr>'
            )

        scenes_table = (
            '<h3>Scenes</h3>'
            '<table style="border-collapse:collapse;">'
            + row('total (matching query)', n_scenes_total)
            + row('active', n_scenes_active)
            + row('prototype', n_scenes_prototype, color='#2563eb')
            + row('suppressed', n_scenes_suppressed, color='#d97706')
            + row('excluded', n_scenes_excluded, color='#b91c1c')
            + '</table>'
        )

        imgs_table = (
            '<h3 style="margin-top:18px;">Images</h3>'
            '<table style="border-collapse:collapse;">'
            + row('active', n_imgs_active)
            + row('prototype', n_imgs_prototype, color='#2563eb')
            + row('excluded', n_imgs_excluded, color='#b91c1c')
            + '</table>'
        )

        todo_table = (
            '<h3 style="margin-top:18px;">Active images: empty fields</h3>'
            '<table style="border-collapse:collapse;">'
            + row('hints empty', todoness_buckets['hints'])
            + row('labels empty', todoness_buckets['labels'])
            + row('caption_joy empty', todoness_buckets['caption_joy'])
            + row('caption empty', todoness_buckets['caption'])
            + '</table>'
        )

        # Rating histogram across active images. Bars rendered as inline-HTML
        # divs with width proportional to the largest bucket. Unrated images
        # (rating field missing or non-integer) are shown as a separate row.
        max_count = max(rating_counts.values()) or 1
        if n_imgs_unrated > max_count:
            max_count = n_imgs_unrated
        hist_rows: list[str] = []
        for r in sorted(rating_counts):
            cnt = rating_counts[r]
            pct = (cnt * 100 / max_count) if max_count else 0
            hist_rows.append(
                '<tr>'
                f'<td style="padding:3px 10px;color:#cccccc;text-align:right;'
                f'font-variant-numeric:tabular-nums;">{r}</td>'
                '<td style="padding:3px 10px;width:280px;">'
                f'<div style="background:#3b82f6;height:14px;width:{pct:.1f}%;'
                'border-radius:2px;"></div>'
                '</td>'
                '<td style="padding:3px 10px;text-align:right;color:#fff;'
                f'font-variant-numeric:tabular-nums;">{cnt}</td>'
                '</tr>'
            )
        if n_imgs_unrated:
            pct = (n_imgs_unrated * 100 / max_count) if max_count else 0
            hist_rows.append(
                '<tr>'
                '<td style="padding:3px 10px;color:#888;text-align:right;">—</td>'
                '<td style="padding:3px 10px;width:280px;">'
                f'<div style="background:#888;height:14px;width:{pct:.1f}%;'
                'border-radius:2px;"></div>'
                '</td>'
                '<td style="padding:3px 10px;text-align:right;color:#fff;'
                f'font-variant-numeric:tabular-nums;">{n_imgs_unrated}</td>'
                '</tr>'
            )
        hist_table = (
            '<h3 style="margin-top:18px;">Active images: rating histogram</h3>'
            '<table style="border-collapse:collapse;">'
            + ''.join(hist_rows)
            + '</table>'
        )

        return (
            f'<div style="padding:8px 4px;">'
            f'<h2>Set <code>{name}</code></h2>'
            f'{scenes_table}{imgs_table}{todo_table}{hist_table}'
            f'</div>'
        )

    def _html_scenes_search_and_op(
        self,
        rating_min: Optional[str],
        rating_max: Optional[str],
        mode: Optional[AppOpMmode],
        opt_label: Optional[str],
        opt_set: Optional[str],
        show_active: bool = True,
        show_prototype: bool = True,
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

        if opt_set is None or opt_set in ['Ignore', 'None']:
            set_query = None
        elif opt_set == 'Empty':
            set_query = {
                SceneDef.FIELD_LABELS: {
                    '$not': {'$regex': f'^{SceneDef.TAG_PREFIX_SET}'}
                }
            }
        else:
            set_query = {
                SceneDef.FIELD_LABELS: f'{SceneDef.TAG_PREFIX_SET}{opt_set}'
            }

        ids = list(self._scm.ids_from_rating(r_min, r_max, labels=labels))
        if set_query is not None:
            ids = [
                str(oid)
                for oid in self._dbc.filter_oids_by_query(
                    SceneDef.COLLECTION_SCENES, ids, [set_query]
                )
            ]
        scenes = [self._scm.scene_from_id_or_url(id) for id in ids]
        SceneDef.sort_by_rating(scenes)
        print(f'Found {len(scenes)} scenes matching advanced search criteria.')

        if mode is None:
            mode = 'none'

        scenes_active = [s for s in scenes if s is not None and not s.is_prototype]
        scenes_proto = [s for s in scenes if s is not None and s.is_prototype]

        ordered: list = []
        if show_active:
            ordered.extend(scenes_active)
        if show_prototype:
            ordered.extend(scenes_proto)

        html_scenes = ''
        for scene in ordered:
            html_scenes += AppSceneCell.html(scene, mode)
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
    def _editor_clear_all() -> tuple[str, str, str, str]:
        """
        Wipes EVERY editor output to a clean placeholder, including the
        scene-id textbox. Used as the first step of the thumbnail-click
        load path: the new scene id arrives via the editor's hidden
        in-databus, NOT from the textbox, so wiping the textbox is fine
        and ensures no stale state survives.
        """
        loading = '<p><em>loading...</em></p>'
        return '', '', loading, ''

    @staticmethod
    def _editor_clear_content(scene_id: Optional[str]) -> tuple[str, str, str, str]:
        """
        Wipes only the content panes (scene-info / registered / unregistered
        HTMLs) and PRESERVES the scene-id textbox. Used as the first step
        of refresh / batch-caption paths whose `.then()` step reads the
        scene id back from the textbox - if we cleared it, the load step
        would get an empty string and lose the scene context.
        """
        loading = '<p><em>loading...</em></p>'
        return (scene_id or ''), '', loading, ''

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
            imgs_active = SceneDef.sort_by_rating(scene.imgs_active)
            imgs_prototype = SceneDef.sort_by_rating(scene.imgs_prototype)
        except Exception as e:
            print(f'ERROR: couldnt list imgs for scene [{scene_id}]: {e}')
            imgs_active = []
            imgs_prototype = []
            registered_html = (
                f'<p>Failed to list images for scene <code>{scene_id}</code>: {e}</p>'
            )
        else:
            if not imgs_active and not imgs_prototype:
                registered_html = (
                    f'<p>No SceneImages registered for scene <code>{scene_id}</code>.</p>'
                )
            else:
                proto_styles = """
                <style>
                    .simg-editor-img-prototype {
                        outline: 2px dashed #2563eb;
                        outline-offset: -2px;
                    }
                </style>
                """
                parts: list[str] = [proto_styles]
                if imgs_active:
                    cells_a = ''.join(
                        AppSceneImageCell.html(img) for img in imgs_active
                    )
                    parts.append(AppHtml.html_styled_cells_grid(cells_a, columns=1))
                if imgs_prototype:
                    cells_p = ''.join(
                        f'<div class="simg-editor-img-prototype">'
                        f'{AppSceneImageCell.html(img)}'
                        f'</div>'
                        for img in imgs_prototype
                    )
                    parts.append(
                        '<h3 style="margin-top:24px;color:#2563eb;">Prototype</h3>'
                    )
                    parts.append(AppHtml.html_styled_cells_grid(cells_p, columns=1))
                registered_html = ''.join(parts)

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
    ) -> None:
        """
        Registers an unregistered image file by url. Shows a toast only;
        does NOT re-render the editor (user refreshes manually).
        """
        self._html_simg_editor_register_impl(url_str, scene_id, prototype=False)

    def _html_simg_editor_register_prototype(
        self, url_str: Optional[str], scene_id: Optional[str]
    ) -> None:
        """
        Registers an unregistered image file by url and flags it as prototype.
        Shows a toast only; does NOT re-render the editor.
        """
        self._html_simg_editor_register_impl(url_str, scene_id, prototype=True)

    def _html_simg_editor_register_impl(
        self,
        url_str: Optional[str],
        scene_id: Optional[str],
        prototype: bool = False,
    ) -> None:
        if not url_str or not isinstance(url_str, str):
            gr.Warning('Register: invalid url.')
            return

        url = Path(url_str.strip())
        if not url.exists():
            gr.Warning(f'Register: file does not exist: {url}')
            return

        try:
            im = self._scm.scene_image_manager()
            new_id = im.register_from_url(url)
        except Exception as e:
            print(f'ERROR: register_from_url [{url}]: {e}')
            gr.Warning(f'Register failed: {e}')
            return

        if new_id is None:
            gr.Warning(f'Register: could not register {url} (not an img/vid or already managed).')
            return

        if prototype:
            try:
                simg = im.image_from_id_or_url(new_id)
                simg.set_prototype(True)
                simg.db_store()
            except Exception as e:
                print(f'WARN: set_prototype on new id [{new_id}] failed: {e}')

        label = 'prototype' if prototype else 'image'
        gr.Info(f'{url.name} registered as {label}.', duration=0.5)

    # ------------------------------------------------------------------
    # prototype-all: bulk-flag every registered image of the loaded scene
    # ------------------------------------------------------------------

    def _html_simg_editor_prototype_all(
        self, scene_id: Optional[str]
    ) -> tuple[str, str, str, str]:
        if not scene_id or not isinstance(scene_id, str):
            gr.Warning('No scene loaded.')
            return self._html_simg_editor_open(scene_id)

        scene_id = scene_id.strip()
        try:
            scene = self._scm.scene_from_id_or_url(scene_id)
        except Exception as e:
            print(f'ERROR: prototype-all load scene [{scene_id}]: {e}')
            gr.Warning(f'Failed to load scene: {e}')
            return self._html_simg_editor_open(scene_id)

        try:
            n_done, n_skipped, n_failed = scene.make_prototype()
        except Exception as e:
            print(f'ERROR: prototype-all batch [{scene_id}]: {e}')
            gr.Warning(f'prototype-all failed: {e}')
            return self._html_simg_editor_open(scene_id)

        msg_parts = [f'Flagged {n_done} as prototype']
        if n_skipped > 0:
            msg_parts.append(f'skipped {n_skipped}')
        if n_failed > 0:
            msg_parts.append(f'failed {n_failed}')
        msg = ', '.join(msg_parts) + '.'
        if n_failed > 0:
            gr.Warning(msg)
        else:
            gr.Info(msg, duration=2.0)

        return self._html_simg_editor_open(scene_id)

    # ------------------------------------------------------------------
    # batch captioning of registered images
    # ------------------------------------------------------------------

    def _html_simg_editor_caption_empty(
        self, scene_id: Optional[str]
    ) -> tuple[str, str, str, str]:
        """
        Scene-level batch caption.

        Pipeline:
          1. Query the DB for all SceneImage ids belonging to this scene
             whose `caption_joy` field is missing / null / empty string.
          2. Construct a single JoySceneDB(trigger='1xlasm', force=True);
             its underlying Joy model is loaded lazily once and reused for
             the whole loop. force=True is required because our query
             already filtered the ids; JoySceneDB's own skip check would
             otherwise refuse to caption images whose caption_joy is the
             empty string ('' is not None -> skip).
          3. For every id, call `jdb._id_caption(id)` -> (prompt, caption)
             and persist the caption EXPLICITLY to FIELD_CAPTION_JOY via
             `simg.set_caption_joy(caption)` + `simg.db_store()`. We never
             touch FIELD_CAPTION - only the empty caption_joy column is
             written.
          4. Release the GPU (`_release_gpu(jdb)` in `finally`) and re-render
             the editor with fresh DB data.
        """
        if not scene_id or not isinstance(scene_id, str):
            gr.Warning('No scene loaded.')
            return self._html_simg_editor_open(scene_id)

        scene_id = scene_id.strip()
        try:
            scene = self._scm.scene_from_id_or_url(scene_id)
        except Exception as e:
            print(f'ERROR: caption-empty load scene [{scene_id}]: {e}')
            gr.Warning(f'Failed to load scene: {e}')
            return self._html_simg_editor_open(scene_id)

        # 1. Find ids of registered scene images whose caption_joy is empty.
        empty_query = {
            '$or': [
                {SceneDef.FIELD_CAPTION_JOY: {'$exists': False}},
                {SceneDef.FIELD_CAPTION_JOY: None},
                {SceneDef.FIELD_CAPTION_JOY: ''},
            ]
        }
        try:
            ids_empty = list(scene.ids_img_from_query(empty_query))
        except Exception as e:
            print(f'ERROR: caption-empty query [{scene_id}]: {e}')
            gr.Warning(f'Failed to query empty captions: {e}')
            return self._html_simg_editor_open(scene_id)

        if not ids_empty:
            gr.Info('All registered images already have a caption_joy.')
            return self._html_simg_editor_open(scene_id)

        # 2. Caption the ids with a single JoySceneDBNG run (1xlasm skin).
        gr.Info(
            f"Batch captioning {len(ids_empty)} image(s) with skin '1xlasm'...",
            duration=3.0,
        )

        cfg_name = self._scm._dbc.config.config
        sim = self._scm.scene_image_manager()
        jdb: Any = None
        n_done = 0
        n_failed = 0
        try:
            # IMPORTANT: force=True. Our query already filtered for empty
            # caption_joy; JoySceneDBNG.caption_image's internal skip check
            # would otherwise skip images whose caption_joy is the empty
            # string '' (`'' is not None` is True), so trust our filter.
            from ait.caption.joy_scenedb_ng import JoySceneDBNG
            jdb = JoySceneDBNG(
                config=cfg_name,
                skin='1xlasm',
                verbose=1,
                force=True,
            )
            # 3. For every id, run a single inference (the underlying JoyNG
            #    model is lazy-loaded once on the JoySceneDBNG instance and
            #    reused for the rest of the loop) and persist the result
            #    EXPLICITLY to caption_joy via set_caption_joy + db_store.
            for img_id in ids_empty:
                try:
                    prompt, caption = jdb.caption_image(img_id)
                except Exception as e:
                    print(f'ERROR: caption-empty inference [{img_id}]: {e}')
                    n_failed += 1
                    continue
                if not caption:
                    # JoySceneDBNG returns (None, None) when it could not
                    # open the image (`simg.pil` was None) or when the
                    # model produced nothing.
                    print(f'WARN: caption-empty produced no caption for [{img_id}]')
                    n_failed += 1
                    continue
                try:
                    simg = sim.image_from_id_or_url(img_id)
                    simg.set_caption_joy(caption)  # writes FIELD_CAPTION_JOY
                    if prompt:
                        simg.set_caption_prompt(prompt)  # writes FIELD_CAPTION_PROMPT
                    simg.db_store()
                    n_done += 1
                except Exception as e:
                    print(f'ERROR: caption-empty store [{img_id}]: {e}')
                    n_failed += 1
        except Exception as e:
            print(f'ERROR: caption-empty batch run: {e}')
            gr.Warning(f'Batch caption failed: {e}')
        finally:
            if jdb is not None:
                self._release_gpu(jdb)

        n_skipped = len(ids_empty) - n_done - n_failed
        msg_parts = [f'Captioned {n_done}']
        if n_skipped > 0:
            msg_parts.append(f'skipped {n_skipped}')
        if n_failed > 0:
            msg_parts.append(f'failed {n_failed}')
        msg = ', '.join(msg_parts) + '.'
        if n_done > 0:
            gr.Info(msg, duration=3.0)
        elif n_failed > 0:
            gr.Warning(msg)
        else:
            gr.Info(msg)

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

    def _html_simg_editor_caption(self, data_str: Optional[str]) -> str:
        """
        Generates a caption for either a registered SceneImage (uses a fresh
        JoySceneDBNG / JoySceneDB instance) or an unregistered image file
        (uses a fresh Joy instance), copies the result to the clipboard and
        frees the model.

        Returns a JSON string `{image_id, caption_joy?, caption_prompt?}`
        that the click's `.then()` JS callback uses to mirror the server-side
        save into the per-cell textareas. Empty string when nothing was
        persisted (clip-only flow, unregistered target, or failure).
        """
        if not data_str or not isinstance(data_str, str):
            gr.Warning('Caption: invalid request.')
            return ''

        try:
            data = json.loads(data_str)
        except Exception as e:
            print(f'ERROR: caption databus json parse: {e}')
            gr.Warning(f'Caption: malformed request: {e}')
            return ''

        target_type = data.get('type')
        target = data.get('target')
        trigger = data.get('trigger')
        clip_only = bool(data.get('clip_only', False))
        if not target_type or not target or not trigger:
            gr.Warning('Caption: incomplete request.')
            return ''

        if target_type == 'registered':
            return self._caption_registered(target, trigger, clip_only=clip_only) or ''
        if target_type == 'unregistered':
            self._caption_unregistered(target, trigger)
            return ''
        gr.Warning(f'Caption: unknown target type [{target_type}].')
        return ''

    @staticmethod
    def _release_gpu(obj: Any) -> None:
        """
        Best-effort destruction of a captioner instance and its underlying
        torch model so VRAM is released for other tasks.
        """
        try:
            # If it's a JoySceneDB / JoySceneDBNG it owns a Joy / JoyNG via
            # .__joy / ._joy.
            inner = getattr(obj, '_JoySceneDB__joy', None)
            if inner is None:
                inner = getattr(obj, '_JoySceneDBNG__joy', None)
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

    def _caption_registered(
        self, image_id: str, trigger: str, clip_only: bool = False
    ) -> str:
        """Return JSON `{image_id, caption_joy?, caption_prompt?}` describing
        the server-side save so the click's .then() callback can mirror the
        write into the DOM textareas. Empty string when nothing was persisted
        (clip_only / non-1xlasm without prompt / failures).
        """
        # 1xlasm auto-persists into caption_joy, so refuse if a stored
        # caption_joy would be overwritten. clip_only paths skip persistence
        # entirely, so the guard does not apply.
        if trigger == '1xlasm' and not clip_only:
            try:
                sim = self._scm.scene_image_manager()
                existing = sim.img_from_id(image_id)
                if existing is not None and (existing.caption_joy or '').strip():
                    gr.Warning(
                        f'1xlasm rejected: caption_joy already set for {image_id}. '
                        f'Clear it first to re-caption.'
                    )
                    return ''
            except Exception as e:
                print(f'WARN: 1xlasm pre-check failed [{image_id}]: {e}')

        gr.Info(
            f'Captioning image {image_id} with trigger [{trigger}]...',
            duration=2.0,
        )
        cfg_name = self._scm._dbc.config.config
        jdb: Any = None
        caption: Optional[str] = None
        prompt: Optional[str] = None
        try:
            if trigger == '1xlasm':
                # NG path: skin-driven, uses JoyNG runtime under the hood.
                from ait.caption.joy_scenedb_ng import JoySceneDBNG
                jdb = JoySceneDBNG(
                    config=cfg_name,
                    skin='1xlasm',
                    verbose=1,
                    force=True,
                )
                prompt, caption = jdb.caption_image(image_id)
            else:
                # Legacy path for other triggers (gts_prompter, …) until they
                # migrate to the JSON-skin pipeline.
                from ait.caption.joy_scenedb import JoySceneDB
                jdb = JoySceneDB(
                    config=cfg_name,
                    trigger=trigger,
                    verbose=1,
                    force=True,
                )
                prompt, caption = jdb._id_caption(image_id)
        except Exception as e:
            print(f'ERROR: caption registered [{image_id}]: {e}')
            gr.Warning(f'Caption failed: {e}')
        finally:
            if jdb is not None:
                self._release_gpu(jdb)

        if not caption:
            gr.Warning(f'No caption produced for image {image_id}.')
            return ''

        try:
            pyperclip.copy(caption)
        except Exception as e:
            print(f'WARN: clipboard copy failed: {e}')

        # Persistence: every caption flow that is NOT clip-only force-stores
        # the prompt that was sent to the model (FIELD_CAPTION_PROMPT) so the
        # exact inputs are auditable. 1xlasm additionally writes caption_joy
        # (the canonical model output for that recipe). Other triggers leave
        # caption_joy alone — they're prompt-shaping helpers, not
        # caption-source-of-truth.
        result: dict[str, Any] = {'image_id': image_id}
        if not clip_only:
            try:
                sim = self._scm.scene_image_manager()
                simg = sim.img_from_id(image_id)
                if simg is not None:
                    if prompt:
                        simg.set_caption_prompt(prompt)
                        result['caption_prompt'] = prompt
                    if trigger == '1xlasm':
                        simg.set_caption_joy(caption)
                        result['caption_joy'] = caption
                    simg.db_store()
                    if trigger == '1xlasm':
                        gr.Info(
                            f'caption_joy + prompt saved for {image_id}.',
                            duration=1.5,
                        )
                    else:
                        gr.Info(
                            f'caption_prompt saved for {image_id}.',
                            duration=1.5,
                        )
            except Exception as e:
                print(f'ERROR: caption persist [{image_id}]: {e}')
                gr.Warning(f'Caption save failed: {e}')
                # state of DOM is uncertain; bail without a result update
                return ''

        preview = caption if len(caption) <= 80 else caption[:77] + '...'
        gr.Info(
            f'Caption copied to clipboard: {preview}',
            duration=2.5,
        )

        # Only emit a result when there's something for the .then() callback
        # to update (i.e. non-clip flows that wrote to caption_joy or
        # caption_prompt). Clip-only paths return empty so the JS no-ops.
        if 'caption_joy' in result or 'caption_prompt' in result:
            return json.dumps(result)
        return ''

    # ------------------------------------------------------------------
    # per-cell server refresh
    # ------------------------------------------------------------------

    def _html_cell_refresh(self, payload_str: Optional[str]) -> str:
        """
        Re-render a single image cell server-side and return JSON
        `{target_id, html}` for the JS .then() swap callback.

        `payload_str` is JSON: `{img_id, set_id?, mode}` where mode is
        'edit' (full edit cell) or 'info' (compact read-only cell).
        Optional `set_id` controls whether the per-cell exclude toggle is
        rendered and reads the current excluded state from that set's
        `imgs_exclude` field.

        Returns the empty string on any failure so the JS swap is a no-op.
        """
        if not payload_str or not isinstance(payload_str, str):
            return ''
        try:
            payload = json.loads(payload_str)
        except Exception:
            return ''
        img_id = payload.get('img_id')
        set_id = payload.get('set_id') or None
        mode = payload.get('mode', 'edit')
        if not img_id:
            return ''

        try:
            sim = self._scm.scene_image_manager()
            img = sim.img_from_id(img_id)
        except Exception:
            return ''
        if img is None:
            return ''

        excluded = False
        if set_id:
            try:
                scene_set = self._ssm.set_from_id_or_name(set_id)
                excluded = img_id in scene_set.imgs_exclude
            except Exception:
                excluded = False

        if mode == 'info':
            cell_html = AppSceneImageCell.html_info(
                img, set_id=set_id, excluded=excluded
            )
            target_id = f'cell-simg-info-{img_id}'
        else:
            cell_html = AppSceneImageCell.html(
                img, set_id=set_id, excluded=excluded
            )
            target_id = f'cell-simg-{img_id}'

        return json.dumps({'target_id': target_id, 'html': cell_html})

    # ------------------------------------------------------------------
    # lightbox (full-size image modal)
    # ------------------------------------------------------------------

    def _lightbox_load(self, data_str: Optional[str]) -> str:
        """
        Loads the full-size image for a registered SceneImage (by id) or an
        unregistered file (by url) and returns a JSON-serialised payload
        consumed by the lightbox JS .then() callback:

            {
              "b64":      "<image bytes base64>",
              "type":     "registered" | "unregistered",
              "image_id": "<oid>",        # only for registered targets
              "caption":  "<current caption>"  # only for registered targets
            }

        Returns '' on failure (the JS callback no-ops).

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
        set_id_in = data.get('set_id') or ''
        if not target_type or not target:
            return ''

        pil = None
        b64: Optional[str] = None
        caption_text: Optional[str] = None
        prototype_flag: bool = False
        excluded_flag: bool = False
        try:
            if target_type == 'registered':
                try:
                    simg = self._scm.scene_image_manager().image_from_id_or_url(target)
                except Exception as e:
                    print(f'ERROR: lightbox load registered [{target}]: {e}')
                    gr.Warning(f'Lightbox load failed: {e}')
                    return ''
                pil = simg.pil
                caption_text = simg.caption or ''
                prototype_flag = bool(simg.prototype)
                if set_id_in:
                    try:
                        scene_set = self._ssm.set_from_id_or_name(set_id_in)
                        excluded_flag = str(target) in set(scene_set.imgs_exclude)
                    except Exception as e:
                        print(f'WARN: lightbox set lookup [{set_id_in}]: {e}')
                        set_id_in = ''
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

        result: dict = {'b64': b64, 'type': target_type}
        if target_type == 'registered':
            result['image_id'] = str(target)
            result['caption'] = caption_text or ''
            result['prototype'] = prototype_flag
            if set_id_in:
                result['set_id'] = set_id_in
                result['excluded'] = excluded_flag
        return json.dumps(result)

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

        # 'set' always captions with the '1xlasm' skin via JoySceneDBNG.
        trigger = '1xlasm'
        gr.Info(
            f"Generating caption for image {image_id} (set, skin '{trigger}')...",
            duration=2.0,
        )
        cfg_name = self._scm._dbc.config.config
        jdb: Any = None
        caption: Optional[str] = None
        try:
            from ait.caption.joy_scenedb_ng import JoySceneDBNG
            jdb = JoySceneDBNG(
                config=cfg_name,
                skin=trigger,
                verbose=1,
                force=True,
            )
            prompt, caption = jdb.caption_image(image_id)
        except Exception as e:
            print(f'ERROR: caption set [{image_id}]: {e}')
            gr.Warning(f'Caption failed: {e}')
        finally:
            if jdb is not None:
                self._release_gpu(jdb)

        if not caption:
            gr.Warning(f'No caption produced for image {image_id}.')
            return ''

        # Force-store the caption_prompt so the model inputs are auditable
        # even though caption_joy/caption write back to DOM only.
        if prompt:
            try:
                sim = self._scm.scene_image_manager()
                simg = sim.img_from_id(image_id)
                if simg is not None:
                    simg.set_caption_prompt(prompt)
                    simg.db_store()
            except Exception as e:
                print(f'WARN: caption_prompt persist [{image_id}]: {e}')

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
