from pathlib import Path
import pprint
from typing import Any, Optional
from PIL import Image as PILImage

from ait.tools.images import image_from_url

from .scene_common import SceneDef
from .scene_image_manager import SceneImageManager


class SceneImage:
    def __init__(self, im: SceneImageManager, id_or_url: Any, verbose=1) -> None:
        """
        Only gets constructed:
            - when a given url contains an id
            - when a given id (explicit or via url)  is a valid id in the database.
        new image creation is done by the image manager!
        """
        self._im = im
        self._verbose = verbose

        data = None
        id = SceneDef.id_from_filename_orig(id_or_url)
        if id is None:
            id = id_or_url
        data = im.data_from_id(id)
        if data is None:
            raise ValueError(f'couldnt make scene image data from [{id_or_url}]!')
        self._data = data

    @property
    def id(self) -> str:
        return str(self._data.get(SceneDef.FIELD_OID, ''))

    @property
    def data(self) -> dict:
        return self._data

    @property
    def rating(self) -> Optional[int]:
        return self._data.get(SceneDef.FIELD_RATING, None)

    @property
    def url_from_data(self) -> Optional[Path]:
        id = self.id
        filename = SceneDef.filename_orig_from_id(id, suffix=SceneDef.SUFFIX_IMG_STD)
        if filename is None:
            return None
        parent = Path(str(self._data.get(SceneDef.FIELD_URL_PARENT)))
        return parent / filename

    @property
    def filename_train_from_data(self) -> str:
        """
        returns the filename as a string with the collections name ("images/") as a subfolder
        """
        id = self.id
        filename = SceneDef.filename_train_from_id(id, suffix=SceneDef.SUFFIX_IMG_STD)
        return f'{self._im._collection_name}/{filename}'

    @property
    def pil(self) -> Optional[PILImage.Image]:
        url = self.url_from_data
        if url is None:
            return None
        return image_from_url(url)

    def _dbstore(self) -> bool:
        return self._im._db_update_image(self._data)

    def update(self) -> None:
        pass

    @property
    def train_metadata_jsonl(self) -> Optional[dict]:
        filename = self.filename_train_from_data
        if filename is None:
            return None
        jsonl = {'file_name': self.filename_train_from_data}
        jsonl |= {'file_type': 'image/png'}

        caption = self._data.get(SceneDef.FIELD_CAPTION, None)
        if caption is not None:
            jsonl |= {SceneDef.FIELD_CAPTION: caption}

        prompt = self._data.get(SceneDef.FIELD_PROMPT, None)
        if prompt is not None:
            jsonl |= {SceneDef.FIELD_PROMPT: prompt}

        return jsonl

    def rate(self, rating_new: int) -> None:
        rating_new = int(rating_new)  # may throw which it shoulds!
        rating_current = self._data.get(SceneDef.FIELD_RATING, None)
        self._data |= {SceneDef.FIELD_RATING: rating_new}
        self._dbstore()
        self._log(f'{self.id}: [TEST] new rating [{rating_current}]->[{rating_new}]', level='info')
        return

    def __str__(self) -> str:
        ret = 'data: ' + pprint.pformat(self._data)
        return ret

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[simg:{level}] {msg}')
