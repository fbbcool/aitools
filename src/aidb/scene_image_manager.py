import os
from pathlib import Path
from typing import Any, Final, Generator
import json

from aidb.dbmanager import DBManager
from .scene_common import SceneDef
from ait.tools.files import is_img_or_vid, subdir_inc, urls_to_dir, is_dir, imgs_from_url


class SceneImageManager:
    IMAGE_COLLECTION: Final = 'images'

    def __init__(self, dbm: DBManager | None = None, config: str | None = None) -> None:
        if config is None:
            config = SceneDef.CONFIG_DEFAULT
        self.config = config
        self.config_file = Path(os.environ['CONF_AIT']) / 'aidb' / f'dbmanager_{config}.yaml'
        if dbm is None:
            self._dbm = DBManager(config_file=str(self.config_file))
        else:
            self._dbm = dbm

    @property
    def root(self) -> Path:
        return Path(self._dbm._root)

    @property
    def url_imgs(self) -> Path:
        url = self.root
        return url

    def id_from_url(self, url: str | Path) -> None | str:
        data = self.data_from_url_db(url)
        if data is None:
            return None
        return str(data.get(SceneDef.FIELD_OID, ''))

    @property
    def ids(self) -> Generator:
        """Returns a generator of image oid's for all images in the db"""

        docs = self._dbm.find_documents(self.IMAGE_COLLECTION, query={})
        for doc in docs:
            yield str(doc['_id'])

    def data_from_id(self, id: Any) -> dict | None:
        oid = self._dbm.to_oid(id)
        if oid is None:
            return None
        docs = self._dbm.documents_from_oid(self.IMAGE_COLLECTION, oid)
        if len(docs) == 0:
            return None
        elif len(docs) == 1:
            return docs[0]

        self._log(f'DATABASE INCONSISTENCY: id {id} is multiple', level='error')
        return None

    def data_from_url_db(self, url: str | Path) -> dict | None:
        docs = self._dbm.find_documents(self.IMAGE_COLLECTION, query={SceneDef.FIELD_URL: str(url)})
        if len(docs) == 0:
            return None
        elif len(docs) == 1:
            return docs[0]

        self._log(f'DATABASE INCONSISTENCY: id {id} is multiple', level='error')
        return None

    def is_id(self, id: str) -> bool:
        if self.data_from_id(id) is not None:
            return True
        return False

    def _data_from_url(self, url: Path | str) -> dict | None:
        url = Path(url)
        if not is_img_or_vid(url):
            return None

        data = {}
        data |= {SceneDef.FIELD_URL: str(url)}
        return data

    def _image_update(self, data: dict) -> dict | None:
        url = data.get(SceneDef.FIELD_URL, '')
        if not url:
            self._log('no url found in meta!')
            return None

        # does url already exist?
        oid = self.id_from_url(url)
        if oid is None:
            oid = self._dbm.insert_document(self.IMAGE_COLLECTION, data)
            self._log('image added: {url}.', level='message')
        else:
            self._log(f'image not added, already exists: {url} oid={oid}.', level='debug')

        if oid:
            data |= {SceneDef.FIELD_OID: oid}

        return data

    @property
    def _dbc_images(self):
        return self._dbm._get_collection(self.IMAGE_COLLECTION)

    def _dbc_to_id(self, id: str):
        self._dbm.to_oid(id)

    def _db_insert_image(self, data: dict) -> str | None:
        dbc = self._dbc_images
        if dbc is None:
            return None

        oid = data.get(SceneDef.FIELD_OID, None)
        if oid is not None:
            return None
        set_data = data.copy()
        set_data.pop(SceneDef.FIELD_OID, None)
        id = self._dbm.insert_document(self.IMAGE_COLLECTION, set_data)
        return id

    def _db_update_image(self, data: dict) -> bool:
        dbc = self._dbc_images
        if dbc is None:
            return False

        oid = data.get(SceneDef.FIELD_OID, None)
        if oid is None:
            return False
        update_data = data.copy()
        update_data.pop(SceneDef.FIELD_OID, None)
        filter = {SceneDef.FIELD_OID: oid}
        update = {'$set': update_data}
        result = dbc.update_one(filter, update)

        if result is None:
            return False
        return True

    def image_from_id_or_url(self, id_or_url: str | Path) -> Any:
        from .scene_image import SceneImage

        self._log(f'make scene image from: [{str(id_or_url)}]', 'debug')
        return SceneImage(self, id_or_url)

    @staticmethod
    def _json_read(url: Path) -> dict:
        if not url.exists():
            return {}

        data = {}
        with url.open('r') as f:
            data = json.load(f)
        return data

    @staticmethod
    def _json_write(url: Path, data: dict) -> None:
        if not url.parent.exists():
            return
        with url.open('w') as f:
            json.dump(data, f)

    def _log(self, msg: str, level: str = 'warning') -> None:
        print(f'[im:{level}] {msg}')
