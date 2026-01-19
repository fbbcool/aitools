from pathlib import Path
import pprint
from typing import Any
from aidb.scene_manager import SceneManager


class Scene:
    def __init__(self, scm: SceneManager, id_or_url: Any) -> None:
        self._scm = scm

        data = None

        url = None
        if isinstance(id_or_url, Path):
            url = id_or_url
        if isinstance(id_or_url, str):
            try:
                url = Path(id_or_url)
            except Exception:
                url = None
        if url is not None:
            data = scm.data_from_url(url)

        if data is None:
            data = scm.data_from_id(id_or_url)

        if data is None:
            raise ValueError('Scene does not exist')

        self.data = data

    @property
    def id(self) -> str:
        return str(self.data.get(SceneManager.FIELD_OID, ''))

    @property
    def url(self) -> Path:
        return Path(self.data.get(SceneManager.FIELD_URL, ''))

    def _dbstore(self) -> bool:
        return self._scm._db_update_scene(self.data)

    def __str__(self) -> str:
        return pprint.pformat(self.data)
