import json
from pathlib import Path
import pprint
from typing import Any, Optional
from PIL import Image as PILImage

from ait.tools.files import is_img_or_vid
from ait.tools.images import image_from_url

from .scene_common import SceneDef
from .scene_image_manager import SceneImageManager


class SceneImage:
    def __init__(self, im: SceneImageManager, id_or_url: Any, verbose=1) -> None:
        self._im = im
        self._verbose = verbose

        data = None
        url = None

        if is_img_or_vid(id_or_url):
            self.url = Path(id_or_url)
            data = im.init_data_from_url(self.url)

        if isinstance(id_or_url, Path):
            url = id_or_url
        if isinstance(id_or_url, str):
            try:
                url = Path(id_or_url)
            except Exception:
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
        return str(self.data.get(SceneDef.FIELD_OID, ''))

    @property
    def url_from_data(self) -> Optional[Path]:
        id = self.id
        filename = SceneDef.filename_orig_from_id(id, suffix=SceneDef.SUFFIX_IMG_STD)
        if filename is None:
            return None
        parent = Path(str(self.data.get(SceneDef.FIELD_URL_PARENT)))
        return parent / filename

    @property
    def filename_train_from_data(self) -> Optional[str]:
        """
        returns the filename as a string with the collections name ("images/") as a subfolder
        """
        id = self.id
        filename = SceneDef.filename_train_from_id(id, suffix=SceneDef.SUFFIX_IMG_STD)
        if filename is None:
            return None
        return f'{self._im._collection}/{filename}'

    @property
    def pil(self) -> Optional[PILImage.Image]:
        url = self.url_from_data
        if url is None:
            return None
        return image_from_url(url)

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
            self.data |= {SceneDef.FIELD_URL: url}
            return self._dbstore()
        return False

    def _dbstore(self) -> bool:
        return self._im._db_update_image(self.data)

    def update(self) -> None:
        if self.url_sync():
            print(f'synced url[{self.url}]')

    @property
    def train_metadata_jsonl(self) -> Optional[str]:
        filename = self.filename_train_from_data
        if filename is None:
            return None
        jsonl = {'file_name': self.filename_train_from_data}
        jsonl |= {'file_type': 'image/png'}

        caption = self.data.get(SceneDef.FIELD_CAPTION, None)
        if caption is not None:
            jsonl |= {SceneDef.FIELD_CAPTION: caption}

        prompt = self.data.get(SceneDef.FIELD_PROMPT, None)
        if prompt is not None:
            jsonl |= {SceneDef.FIELD_PROMPT: prompt}

        return json.dumps(jsonl)

    def __str__(self) -> str:
        ret = f'url: {self.url}\n'
        ret += 'data: ' + pprint.pformat(self.data)
        return ret

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[simg:{level}] {msg}')
