import json
from typing import Any, Final, Literal, Optional

import pyperclip
import gradio as gr

from aidb.scene.db_connect import DBConnection
from aidb.scene.scene import Scene
from aidb.scene.scene_manager import SceneManager


AppOpMmode = Literal['info', 'rate', 'label', 'none']


class AppHtml:
    ELEM_ID: Final = 'elem_id'

    @classmethod
    def make_elem_id(
        cls, obj: str, action: Optional[str] = None, html_obj: Optional[str] = None
    ) -> str:
        if action is None:
            action = ''
        if html_obj is None:
            html_obj = ''
        return '_'.join([cls.ELEM_ID, obj, action, html_obj])

    @classmethod
    def make_elem_id_button_update(cls, obj: str) -> str:
        return cls.make_elem_id(obj, action='update', html_obj='button')

    @classmethod
    def make_elem_id_button_get(cls, obj: str) -> str:
        return cls.make_elem_id(obj, action='get', html_obj='button')

    @classmethod
    def make_elem_id_databus_textbox(cls, obj: str) -> str:
        return cls.make_elem_id(obj, html_obj='databus')

    @classmethod
    def cmd_make_data(
        cls,
        type_obj: str,
        id: str,
        cmd: str,
        payload: Optional[Any] = None,
    ) -> str:
        data = {'type': type_obj, 'id': id, 'cmd': cmd}
        if payload is not None:
            data |= {'payload': payload}
        return json.dumps(data)


class AppHelper:
    def __init__(self, dbc: DBConnection) -> None:
        self._dbc = dbc

    def cmd_run(self, data_cmd: dict) -> None:
        """
        Executes a command from the comand databus.
        This function is triggered by a hidden button and receives its data from a hidden 'cmd_databus' textbox.
        """
        print(f"DEBUG: cmd_run called with data from bus: '{data_cmd}'")

        # TODO: only inst when there is a scene cmd
        scm = SceneManager(dbc=self._dbc)

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

        obj = None
        obj_type = data.get('type', None)
        if obj_type is None:
            print(f'ERROR: obj type is none [{str(data)}]')
            gr.Warning('[cmd_run]: obj type is none.')
            return None
        elif obj_type == 'scene':
            try:
                obj = scm.scene_from_id_or_url(id)
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
            self._attr_to_clipspace(obj, payload)

        return None

    @classmethod
    def _attr_to_clipspace(cls, obj: Any, attr: Any) -> None:
        if not isinstance(attr, str):
            raise ValueError('attr not str!')

        if not isinstance(obj, (Scene)):
            raise ValueError('obj not correct instance type!')

        clipspace = str(getattr(obj, attr))
        if clipspace:
            pyperclip.copy(clipspace)
        return None
