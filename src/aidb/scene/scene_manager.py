from pathlib import Path
from typing import Any, Final, Generator
import json

from aidb.scene.db_connect import DBConnection
from ait.tools.files import (
    imgs_and_vids_from_url,
    is_img_or_vid,
    subdir_inc,
    urls_to_dir,
    is_dir,
)

from .scene_common import SceneDef, SceneConfig


class SceneManager:
    DOTFILE: Final = '.scenemanager'

    def __init__(
        self,
        dbc: DBConnection | None = None,
        config: SceneConfig = 'default',
        subdir_scenes: str | None = None,
        verbose: int = 1,
    ) -> None:
        if dbc is None:
            self._verbose = verbose
            self._dbc = DBConnection(config=config, verbose=self._verbose)
        else:
            self._dbc = dbc
            self._verbose = self._dbc._verbose
        self._subdir_scenes = subdir_scenes
        self._collection = SceneDef.COLLECTION_SCENES

    @property
    def config(self):
        return self._dbc.config

    @property
    def root(self) -> Path:
        return self._dbc.config.root

    @property
    def url_scenes(self) -> Path:
        url = self.root
        if self._subdir_scenes is not None:
            url = url / self._subdir_scenes
        return url

    @property
    def url_thumbs(self) -> Path:
        return self._dbc.config.thumbs_url

    @classmethod
    def _url_dotfile_path(cls, url: str | Path) -> Path:
        url = Path(url)
        return url / cls.DOTFILE

    @classmethod
    def _url_dotfile_load(cls, url: str | Path) -> None | dict:
        dotfile = cls._url_dotfile_path(url)
        data = cls._json_read(dotfile)
        if not data:
            return None
        return data

    @classmethod
    def id_from_dotfile(cls, url: str | Path) -> None | str:
        data = cls._url_dotfile_load(url)
        if data is None:
            return None
        id = data.get(SceneDef.FIELD_OID, None)
        return id

    def id_from_url(self, url: str | Path) -> None | str:
        data = self.data_from_url_db(url)
        if data is None:
            return None
        return str(data.get(SceneDef.FIELD_OID, ''))

    @property
    def ids(self) -> Generator:
        """Returns a generator of scene oid's for all scenes in the db"""

        docs = self._dbc.find_documents(self._collection, query={})
        for doc in docs:
            yield str(doc['_id'])

    def ids_from_query(self, query: dict) -> Generator:
        docs = self._dbc.find_documents(self._collection, query)
        for doc in docs:
            yield str(doc['_id'])

    def ids_from_rating(self, min: int, max: int, labels: list[str] | None = None) -> Generator:
        query: dict[str, Any] = {SceneDef.FIELD_RATING: {'$gte': min, '$lte': max}}
        if labels is not None:
            if not labels:
                query |= {SceneDef.FIELD_LABELS: {'$size': 0}}
            else:
                query |= {SceneDef.FIELD_LABELS: {'$in': labels}}

        print(f'query: [{query}]')
        return self.ids_from_query(query)

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

    def data_from_url_db(self, url: str | Path) -> dict | None:
        docs = self._dbc.find_documents(self._collection, query={SceneDef.FIELD_URL: str(url)})
        if len(docs) == 0:
            return None
        elif len(docs) == 1:
            return docs[0]

        self._log(f'DATABASE INCONSISTENCY: id {id} is multiple', level='error')
        return None

    def data_from_url_dotfile(self, url: str | Path) -> dict | None:
        id = self.id_from_dotfile(url)
        data = self.data_from_id(id)
        return data

    def url_from_id(self, id: Any) -> Path | None:
        data = self.data_from_id(id)
        if data is None:
            return None
        return data.get(SceneDef.FIELD_URL, None)

    def is_id(self, id: str) -> bool:
        if self.data_from_id(id) is not None:
            return True
        return False

    def update_from_url(self, url: str | Path) -> str | None:
        url = Path(url)
        if not url.exists():
            self._log(f'url does not exist: {url}')
            return
        elif not url.is_dir():
            self._log(f'url is not a dir: {url}')
            return

        oid = self.id_from_dotfile(url)
        self._log(f'{url} got dotfile oid {oid}', level='debug')

        oid = self.id_from_url(url)
        self._log(f'{url} got oid {oid}', level='debug')

        if oid is None:
            if oid is None:
                # add new scene
                meta = self._meta_init_data(url=url)
                meta = self._scene_update(meta)
                if meta is not None:
                    oid = meta.get(SceneDef.FIELD_OID, None)
            data_dotfile = self._dotfile_init_data(oid=oid)
            self._dotfile_update(url, data_dotfile)
        else:
            if oid is None:
                # update url in db with check of db url?
                self._log(f'DATABASE INCONSISTENCY: {url} has no oid, TODO fix!', level='error')
            elif oid != oid:
                # update url in db with check of db url?
                self._log(
                    f'DATABASE INCONSISTENCY: {url} dotfile oid does match to oid, TODO fix!',
                    level='error',
                )
            else:
                # all good: scene db and dotfile consistent
                pass

        return oid

    def _dotfile_init_data(self, oid: str | None = None) -> dict:
        data = {}

        if not oid:
            oid = None
        if oid is not None:
            data |= {SceneDef.FIELD_OID: str(oid)}

        return data

    def _dotfile_update(self, url: Path | str, up_data: dict) -> dict | None:
        url = Path(url)

        if not url.exists():
            self._log(f'url {url} not exists for dotfile: {up_data}', level='warning')
            return None

        dotfile = url / self.DOTFILE
        data = self._json_read(dotfile)
        data |= up_data
        self._json_write(dotfile, data)

    def _meta_init_data(self, url: Path | str | None = None) -> dict:
        data = {}

        if not url:
            url = None
        if url is not None:
            data |= {SceneDef.FIELD_URL: str(url)}
        return data

    def _scene_update(self, meta: dict) -> dict | None:
        url = meta.get(SceneDef.FIELD_URL, '')
        if not url:
            self._log('no url found in meta!')
            return None

        # does scene url already exist?
        oid = self.id_from_url(url)
        if oid is None:
            oid = self._dbc.insert_document(self._collection, meta)
            self._log('scene added: {url}.', level='message')
        else:
            self._log(f'scene not added, already exists: {url} oid={oid}.', level='debug')

        if oid:
            meta |= {SceneDef.FIELD_OID: oid}

        return meta

    def new_scene_from_urls(self, _urls: list[str] | list[Path] | str | Path) -> list[str] | None:
        if not isinstance(_urls, list):
            urls = [_urls]
        else:
            urls = _urls
        urls_img = [Path(url) for url in urls if is_img_or_vid(url)]

        ret = []
        if urls_img:
            oid = self._scene_new_imgs(urls_img)
            if oid is not None:
                ret.append(oid)

        dirs = [Path(url) for url in urls if is_dir(url)]
        for dir in dirs:
            oid = self._scene_new_dir(dir)
            if oid is not None:
                ret.append(oid)

    def _scene_new_imgs(self, url_imgs: list[str] | list[Path]) -> None | str:
        """
        private: makes a new scene from a list of img urls.

        url_imgs should be completely valid (e.g. generated by is_img_or_vid(), they're not gonna be checked again.

        returns the new oid:str
        """

        if not url_imgs:
            return None

        # physical files movement
        self.url_scenes.mkdir(parents=True, exist_ok=True)
        dir_scene = subdir_inc(self.url_scenes)
        urls_to_dir(url_imgs, dir_scene)

        # db entry
        oid = self.update_from_url(dir_scene)

        return oid

    def _scene_new_dir(self, dir: str | Path) -> None | str:
        return self._scene_new_imgs(imgs_and_vids_from_url(dir))

    @property
    def _dbc_scenes(self):
        return self._dbc._get_collection(self._collection)

    def _dbc_to_id(self, id: str):
        self._dbc.to_oid(id)

    def _db_update_scene(self, data: dict) -> bool:
        dbc = self._dbc_scenes
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

    def url_from_registered_file(self, reg_file: str | Path) -> Path | None:
        res = SceneDef.id_and_prefix_from_filename(reg_file)
        if res is None:
            return None
        return self.url_from_id(res[0])

    def scene_from_id_or_url(self, id_or_url: str | Path) -> Any:
        from .scene import Scene

        return Scene(self, id_or_url)

    def scenes_update(self) -> None:
        from .scene import Scene

        for id in self.ids:
            try:
                scene = Scene(self, id)
            except FileNotFoundError as e:
                self._log(str(e), level='warning')
                continue
            except ValueError as e:
                self._log(str(e), level='warning')
                continue
            scene.update()

    def scene_image_manager(self) -> Any:
        from .scene_image_manager import SceneImageManager

        return SceneImageManager(dbc=self._dbc)

    def scene_set_manager(self) -> Any:
        from .scene_set_manager import SceneSetManager

        return SceneSetManager(dbc=self._dbc)

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

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[scm:{level}] {msg}')
