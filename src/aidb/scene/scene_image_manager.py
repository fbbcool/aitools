from pathlib import Path
from typing import Any, Generator, Literal
import json

from .db_connect import DBConnection
from .scene_common import SceneDef

from ait.tools.files import is_img_or_vid, url_move_to_new_parent
from ait.tools.images import image_info_from_url


class SceneImageManager:
    def __init__(
        self,
        dbc: DBConnection | None = None,
        config: Literal['test', 'prod', 'default'] = 'default',
        verbose: int = 1,
    ) -> None:
        self._verbose = verbose
        if dbc is None:
            self._dbc = DBConnection(config=config, verbose=self._verbose)
        else:
            self._dbc = dbc

        self._collection = SceneDef.COLLECTION_IMAGES

    @property
    def root(self) -> Path:
        return Path(self._dbc.config.root)

    def id_from_url(self, url: str | Path) -> None | str:
        data = self.data_from_url_db(url)
        if data is None:
            return None
        return str(data.get(SceneDef.FIELD_OID, ''))

    @property
    def ids(self) -> Generator:
        """Returns a generator of image oid's for all images in the db"""

        docs = self._dbc.find_documents(self._collection, query={})
        for doc in docs:
            yield str(doc['_id'])

    def data_from_id(self, id: Any) -> dict | None:
        oid = self._dbc.to_oid(id)
        if oid is None:
            return None
        docs = self._dbc.documents_from_oid(self._collection, oid)
        if len(docs) == 0:
            return None
        elif len(docs) == 1:
            return docs[0]

        self._log(f'DATABASE INCONSISTENCY: id {id} is multiple', level='error')
        return None

    def register_from_url(self, url: Path | str) -> str | None:
        """
        Registers a new img/vid and returns the id on success.

        None is returned, when:
         - The url is no img or vid.
         - The url looks like an already registered one.
        """
        if not is_img_or_vid(url):
            return None
        if SceneDef.id_and_prefix_from_filename(url) is not None:
            return None
        data = self.init_data_from_url(url)
        if data is None:
            return
        ret = self._db_insert_image(data)

        return ret

    def data_from_url_db(self, url: str | Path) -> dict | None:
        docs = self._dbc.find_documents(self._collection, query={SceneDef.FIELD_URL: str(url)})
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

    def init_data_from_url(self, url: Path | str) -> dict | None:
        data = image_info_from_url(url)
        if data is None:
            return None
        data |= {SceneDef.FIELD_URL_SRC: str(url)}
        return data

    def _image_update(self, data: dict) -> dict | None:
        url = data.get(SceneDef.FIELD_URL, '')
        if not url:
            self._log('no url found in meta!')
            return None

        # does url already exist?
        oid = self.id_from_url(url)
        if oid is None:
            oid = self._dbc.insert_document(self._collection, data)
            self._log('image added: {url}.', level='message')
        else:
            self._log(f'image not added, already exists: {url} oid={oid}.', level='debug')

        if oid:
            data |= {SceneDef.FIELD_OID: oid}

        return data

    @property
    def _dbc_images(self):
        return self._dbc._get_collection(self._collection)

    def _dbc_to_id(self, id: str):
        self._dbc.to_oid(id)

    def _db_url_src_exists(self, url_src: Path | str | None) -> bool:
        if url_src is None:
            return False
        url_src = str(url_src)
        res = self._dbc.find_documents(
            SceneDef.COLLECTION_IMAGES, query={SceneDef.FIELD_URL_SRC: url_src}
        )
        if not res:
            return False
        return True

    def _db_insert_image(self, data: dict) -> str | None:
        url_src = data.get(SceneDef.FIELD_URL_SRC, None)
        if url_src is None:
            return None
        if not is_img_or_vid(url_src):
            return None

        set_data = data.copy()
        set_data.pop(SceneDef.FIELD_OID, None)
        set_data |= {SceneDef.FIELD_URL_PARENT: str(Path(url_src).parent)}
        id = self._dbc.insert_document(self._collection, set_data)

        self.image_move_src(id)

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

    def image_move_src(self, id: Any) -> None:
        oid = self._dbc.to_oid(id)
        if oid is None:
            return
        data = self.data_from_id(oid)
        if data is None:
            return
        url_src = data.get(SceneDef.FIELD_URL_SRC, None)
        if url_src is None:
            return
        url_parent = data.get(SceneDef.FIELD_URL_PARENT, None)
        if url_parent is None:
            return
        if not is_img_or_vid(url_src):
            return

        filename_orig = SceneDef.filename_orig_from_id(oid)
        if filename_orig is None:
            return
        url_move_to_new_parent(url_src, url_parent, filename_orig, delete_src=True, exist_ok=True)

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
        if self._verbose > 0:
            print(f'[im:{level}] {msg}')
