from pathlib import Path
import pprint
from typing import Any
from .scene_image_manager import SceneImageManager


class SceneImage:
    def __init__(self, im: SceneImageManager, id_or_url: Any) -> None:
        self._im = im

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
            data = im.data_from_url_dotfile(url)
            if data is None:
                data = im.data_from_url_db(url)
                url = None

        if data is None:
            url = None
            data = im.data_from_id(id_or_url)

        if data is None:
            raise ValueError('Scene does not exist')

        self.data = data
        self.url = url
        """the "called" url, not the db stored! should be None if data was loaded from id."""

    @property
    def id(self) -> str:
        return str(self.data.get(SceneManager.FIELD_OID, ''))

    @property
    def url_from_data(self) -> Path:
        return Path(self.data.get(SceneManager.FIELD_URL, ''))

    def url_sync(self) -> bool:
        """
        If scene was successfully instanciated from a specific url, this url
        will be synced to the url in the database.
        Warning: the url stored in the database will be overwritten and no checks
        of physical existence will be applied!
        """
        if self.url is None:
            return False
        url = str(self.url)
        if str(self.url_from_data) != url:
            self.data |= {SceneManager.FIELD_URL: url}
            return self._dbstore()
        return False

    def _dbstore(self) -> bool:
        return self._im._db_update_scene(self.data)

    def update(self) -> None:
        if self.url_sync():
            print(f'synced url[{self.url}]')

    def __str__(self) -> str:
        ret = f'url: {self.url}\n'
        ret += 'data: ' + pprint.pformat(self.data)
        return ret
