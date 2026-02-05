from pathlib import Path
import pprint
from typing import Any, Generator

from ait.tools.files import imgs_from_url, img_latest_from_url
from ait.tools.images import thumbnail_to_url

from .scene_common import SceneDef
from .scene_manager import SceneManager


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
            data = scm.data_from_url_dotfile(url)
            if data is None:
                data = scm.data_from_url_db(url)
                url = None

        if data is None:
            url = None
            data = scm.data_from_id(id_or_url)

        if data is None:
            raise ValueError('Scene does not exist')

        self._data = data
        self._url_called = url

        if self._url_called is None:
            if not self.url.exists():
                raise FileNotFoundError(
                    f"Scene (id={self.id}, url={self.url}) doesn't physically exist!"
                )

    @property
    def id(self) -> str:
        return str(self._data.get(SceneDef.FIELD_OID, ''))

    @property
    def data(self) -> dict:
        return self._data

    @property
    def url(self) -> Path:
        return self.url_from_data

    @property
    def urls_img(self) -> Generator:
        for url in imgs_from_url(self.url):
            yield url

    @property
    def url_thumbnail(self) -> Path:
        filename_thumbnail = SceneDef.filename_thumbnail_from_id(self.id)
        if filename_thumbnail is None:
            raise ValueError("Filename for thumbnail couldn't be created!")
        return self._scm.url_thumbnails / filename_thumbnail

    @property
    def url_from_data(self) -> Path:
        return Path(self._data.get(SceneDef.FIELD_URL, ''))

    def _url_sync(self) -> bool:
        """
        If scene was successfully instanciated from a specific url, this url
        will be synced to the url in the database.
        Warning: the url stored in the database will be overwritten and no checks
        of physical existence will be applied!
        """
        if self._url_called is None:
            return False
        url = str(self._url_called)
        if str(self.url_from_data) != url:
            self._data |= {SceneDef.FIELD_URL: url}
            return self._dbstore()
        return False

    def _dbstore(self) -> bool:
        return self._scm._db_update_scene(self._data)

    def update(self) -> None:
        if self._url_sync():
            self._log(f'synced url[{self._url_called}]', level='message')
        if self._update_thumbnail():
            self._log('thumbnail update.', level='message')

        # add init data, if not present
        self._init_data()

        # store
        if self._dbstore():
            self._log('data update.', level='message')

    def _update_thumbnail(self) -> bool:
        latest = img_latest_from_url(self.url)
        if latest is None:
            return False
        ts_latest = latest.stat().st_ctime
        if self.url_thumbnail.exists():
            ts_thumbnail = self.url_thumbnail.stat().st_ctime
            if ts_thumbnail > ts_latest:
                return False
        thumbnail_to_url(latest, self.url_thumbnail, size=self._scm._dbm._default_thumbnail_size[0])
        return True

    def _init_data(self) -> None:
        # rating
        if self._data.get(SceneDef.FIELD_RATING, None) is None:
            self.set_rating(self.get_rating)
        # labels
        if self._data.get(SceneDef.FIELD_LABELS, None) is None:
            self.set_labels(self.get_labels)

    @property
    def get_rating(self) -> int:
        """
        Returns the rating as int.

        If rating isn't set, the init value is given.
        """
        get_data = self._data.get(SceneDef.FIELD_RATING, SceneDef.RATING_INIT)
        return get_data

    def set_rating(self, value: int) -> None:
        if not isinstance(value, int):
            return
        if value < SceneDef.RATING_MIN:
            value = SceneDef.RATING_MIN
        if value > SceneDef.RATING_MAX:
            value = SceneDef.RATING_MAX

        set_data = {SceneDef.FIELD_RATING: value}
        self._data |= set_data
        return

    def set_labels(self, value: list[str]) -> None:
        if not isinstance(value, list):
            return

        set_data = {SceneDef.FIELD_LABELS: list(set(value))}
        self._data |= set_data
        return

    @property
    def get_labels(self) -> list[str]:
        """
        Returns the labels as a list of strings.

        If labels aren't set, an empty list is given.
        """
        get_data = self._data.get(SceneDef.FIELD_LABELS, [])
        return get_data

    def update_label(self, label: str) -> None:
        """
        Updates the labels by adding or removing the given label.

        a subsequent + or - given in the label string indicates adding or removing.
        if no +|- is given, adding is asumed.
        """
        if len(label) <= 2:  # at least 2 chars!
            return
        labels = self.get_labels.copy()
        op = label[0]

        if op == '-':
            labels.remove(label[1:])
        elif op == '+':
            labels.append(label[1:])
        else:
            labels.append(label)

        self.set_labels(labels)
        return

    def __str__(self) -> str:
        ret = f'url: {self._url_called}\n'
        ret += 'data: ' + pprint.pformat(self._data)
        return ret

    def _log(self, msg: str, level: str = 'message') -> None:
        print(f'[scene id({self.id}):{level}] {msg}')
