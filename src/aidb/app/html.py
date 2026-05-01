import json
from typing import Any, Final, Literal, Optional

import base64
from io import BytesIO
from PIL import Image as PILImage

import pyperclip
import gradio as gr

from aidb.scene import DBConnection
from aidb import Scene, SceneImageManager, SceneManager, SceneSetManager
from aidb.scene.scene_common import Sceneical
from aidb.scene.scene_image import SceneImage


AppOpMmode = Literal['info', 'rate', 'label', 'set', 'none']


class AppHtml:
    ELEM_ID: Final = 'elem_id'

    @staticmethod
    def make_elem_id(obj: str, action: Optional[str] = None, html_obj: Optional[str] = None) -> str:
        if action is None:
            action = ''
        if html_obj is None:
            html_obj = ''
        return '_'.join([AppHtml.ELEM_ID, obj, action, html_obj])

    @staticmethod
    def make_elem_id_hidden_button(obj: str) -> str:
        return AppHtml.make_elem_id(obj, action='hidden', html_obj='button')

    @staticmethod
    def make_elem_id_button_get(obj: str) -> str:
        return AppHtml.make_elem_id(obj, action='get', html_obj='button')

    @staticmethod
    def make_elem_id_databus_textbox(obj: str) -> str:
        return AppHtml.make_elem_id(obj, action='hidden', html_obj='databus')

    @staticmethod
    def elem_id_cmd_button() -> str:
        return AppHtml.make_elem_id_hidden_button('cmd')

    @staticmethod
    def elem_id_cmd_databus() -> str:
        return AppHtml.make_elem_id_databus_textbox('cmd')

    @staticmethod
    def elem_id_simg_editor_open_button() -> str:
        return AppHtml.make_elem_id_hidden_button('simg_editor_open')

    @staticmethod
    def elem_id_simg_editor_databus() -> str:
        return AppHtml.make_elem_id_databus_textbox('simg_editor')

    @staticmethod
    def elem_id_simg_editor_tab() -> str:
        return AppHtml.make_elem_id('simg_editor', html_obj='tab')

    @staticmethod
    def make_cmd_data(
        type_obj: str,
        id: str,
        cmd: str,
        payload: Optional[Any] = None,
        label: Optional[str] = None,
    ) -> dict:
        # print(f'[make cmd]: type[{type_obj}] id[{id}] cmd[{cmd}] payload[{payload}] label[{label}]')
        data = {'type': type_obj, 'id': id, 'cmd': cmd}
        if payload is not None:
            data |= {'payload': payload}
        if label is None:
            label = cmd
        data |= {'label': label}
        return data

    @staticmethod
    def make_cmd_data_str(
        type_obj: str,
        id: str,
        cmd: str,
        payload: Optional[Any] = None,
        label: Optional[str] = None,
    ) -> str:
        return json.dumps(AppHtml.make_cmd_data(type_obj, id, cmd, payload=payload, label=label))

    @staticmethod
    def html_make_cmd_button(data_cmd: dict, checked: bool = False) -> str:
        type_obj = data_cmd.get('type', None)
        id = data_cmd.get('id', None)
        cmd = data_cmd.get('cmd', None)
        label = data_cmd.get('label', None)
        payload = str(data_cmd.get('payload', None))

        checked_html = ''
        if checked:
            checked_html = 'checked'
        onclick_js = f"""
        console.log("cmd button clicked!");
        event.stopPropagation();
        elem_id_btn = '{AppHtml.elem_id_cmd_button()}';
        btn_elem = document.getElementById(elem_id_btn);
        console.log(elem_id_btn);
        console.log(btn_elem);
        elem_id_bus = '{AppHtml.elem_id_cmd_databus()}';
        bus_elem = document.getElementById(elem_id_bus);
        console.log(elem_id_bus);
        console.log(bus_elem);
        const bus = document.querySelector('#{AppHtml.elem_id_cmd_databus()} textarea');
        bus.value = '{json.dumps(data_cmd)}';
        bus.dispatchEvent(new Event('input', {{ bubbles: true }}));
        document.getElementById('{AppHtml.elem_id_cmd_button()}').click();""".replace(
            '\n', ' '
        ).replace('"', '&quot;')
        output_html = f"""
            <input type="radio" id="{cmd}-{type_obj}-{id}-{payload}" {checked_html} onclick="{onclick_js}">
            <label for="{cmd}-{type_obj}-{id}-{payload}">{label}</label>
            """
        return output_html

    @staticmethod
    def html_styled_cells_grid(inner_html: str, img_width: int = 250) -> str:
        html = f"""
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
        {inner_html}
        </div>
        """
        return html


class AppHelper:
    def __init__(self, dbc: DBConnection) -> None:
        self._dbc = dbc

    def cmd_run(self, data_cmd: dict) -> None:
        """
        Executes a command from the comand databus.
        This function is triggered by a hidden button and receives its data from a hidden 'cmd_databus' textbox.
        """
        print(f"[DEBUG:run cmd]: '{data_cmd}'")

        if not data_cmd or not isinstance(data_cmd, str):
            print(f'ERROR: Invalid or empty data [{data_cmd}]')
            gr.Warning('[cmd_run]: Invalid data received from frontend.')
            return None

        data = json.loads(data_cmd)
        if not isinstance(data, dict):
            print(f'ERROR: Invalid or empty data [{data_cmd}]')
            gr.Warning('[cmd_run]: data couldnt be jsoned.')
            return None

        if data.get('type', '') not in ['scene', 'set', 'image']:
            print(f'ERROR: unknown type data [{str(data)}]')
            gr.Warning('[cmd_run]: no scene type data.')
            return None

        cmd = data.get('cmd', None)
        if cmd is None:
            print(f'ERROR: invalid id or cmd [{str(data)}]')
            gr.Warning('[cmd_run]: invalid id or cmd.')
            return None

        id = data.get('id', None)
        if id is None:
            print(f'ERROR: id is none [{str(data)}]')
            gr.Warning('[cmd_run]: id is none.')
            return None

        obj: Optional[Sceneical] = None
        obj_type = data.get('type', None)
        if obj_type is None:
            print(f'ERROR: obj type is none [{str(data)}]')
            gr.Warning('[cmd_run]: obj type is none.')
            return None
        elif obj_type == 'scene':
            mgr = SceneManager(dbc=self._dbc)
            try:
                obj = mgr.scene_from_id_or_url(id)
            except Exception:
                print(f'ERROR: couldnt make scene [{str(data)}]')
                gr.Warning('[cmd_run]: couldnt make scene.')
                return None
        elif obj_type == 'image':
            mgr = SceneImageManager(dbc=self._dbc)
            try:
                obj = mgr.image_from_id_or_url(id)
            except Exception:
                print(f'ERROR: couldnt make scene [{str(data)}]')
                gr.Warning('[cmd_run]: couldnt make scene.')
                return None
        elif obj_type == 'set':
            mgr = SceneSetManager(dbc=self._dbc)
            try:
                obj = mgr.set_from_id_or_name(id)
            except Exception:
                print(f'ERROR: couldnt make scene [{str(data)}]')
                gr.Warning('[cmd_run]: couldnt make scene.')
                return None

        if obj is None:
            print(f'ERROR: obj is none [{str(data)}]')
            gr.Warning('[cmd_run]: obj is none.')
            return None

        payload = data.get('payload', None)
        if cmd == 'to_clipspace':
            self._cmd_attr_to_clipspace(obj, payload)
        if cmd == 'db_query':
            self._cmd_db_query(obj, payload)

        return None

    @classmethod
    def _cmd_attr_to_clipspace(cls, obj: Sceneical, payload: Any) -> None:
        if not isinstance(payload, str):
            raise ValueError('attr not str!')
        attr = payload

        clipspace = str(getattr(obj, attr))
        if clipspace:
            pyperclip.copy(clipspace)
        return None

    @classmethod
    def _cmd_db_query(cls, obj: Sceneical, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise ValueError('payload not dict!')

        # only look at the first key/val
        attr = next(iter(payload))
        val = payload.get(attr, None)
        if attr is None or val is None:
            raise ValueError('None attr or val')

        if not isinstance(obj, (Scene, SceneImage)):
            raise ValueError('obj not correct instance type!')
        if not hasattr(obj, attr):
            raise ValueError(f'obj has no attr {attr}')

        func = getattr(obj, attr)
        func(val)

        obj.db_store()

        return None


class HtmlHelper:
    @staticmethod
    def pil_to_base64(pil: Optional[PILImage.Image]) -> Optional[str]:
        """Converts a PIL Image to a base64 encoded string."""
        if pil is None:
            return None
        buffered = BytesIO()
        pil.save(buffered, format='PNG')
        return base64.b64encode(buffered.getvalue()).decode()
