from pathlib import Path
import pprint
from aidb.scene_manager import SceneManager


class Scene:
    def __init__(self, scm: SceneManager, id_or_url: str | Path) -> None:
        self._scm = scm
        url = Path(id_or_url)

        id = str(id_or_url)
        data = scm.id_data(id)
        if data is None:
            data = scm.url_data(url)

        if data is None:
            raise ValueError('Scene does not exist')

        data |= {'id': str(data.get('_id'))}
        self._data = data

    @property
    def id(self) -> str:
        return str(self._data.get('_id', ''))

    @property
    def url(self) -> Path:
        return Path(self._data.get('url', ''))

    @property
    def data(self) -> dict:
        return self._data

    def __str__(self) -> str:
        return pprint.pformat(self.data)
