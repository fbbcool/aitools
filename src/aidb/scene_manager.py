from pathlib import Path
from typing import Final
import json
from aidb.dbmanager import DBManager


class SceneManager:
    DOTFILE: Final = '.scenemanager'
    FIELD_DBID: Final = 'dbid'
    SCENE_COLLECTION: Final = 'scenes'

    def __init__(self, dbm: DBManager) -> None:
        self.dbm = dbm

        # this is not necessary since mongo handles collection creation automatically
        # dbm.create_collection(self.SCENE_COLLECTION)

    @classmethod
    def _url_dotfile_path(cls, url: str | Path) -> Path:
        url = Path(url)
        return url.parent / cls.DOTFILE

    @classmethod
    def _url_dotfile_load(cls, url: str | Path) -> None | dict:
        dotfile = cls._url_dotfile_path(url)
        if not dotfile.exists():
            return None
        ret = None
        with dotfile.open('r') as f:
            ret = json.load(f)
        return ret

    @classmethod
    def _url_dbid(cls, url: str | Path) -> None | str:
        data = cls._url_dotfile_load(url)
        if data is None:
            return None
        dbid = data.get(cls.FIELD_DBID, None)
        return dbid

    def url_add(self, url: str | Path):
        url = Path(url)
