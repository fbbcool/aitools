from typing import Final, Optional


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
    def make_elem_id_databus(cls, obj: str) -> str:
        return cls.make_elem_id(obj, html_obj='databus')
