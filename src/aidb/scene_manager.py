import os
from pathlib import Path
from typing import Final, Generator
import json

from aidb.dbmanager import DBManager
from ait.tools.files import is_img_or_vid, subdir_inc, urls_to_dir, is_dir, imgs_from_url


class SceneManager:
    DOTFILE: Final = '.scenemanager'
    FIELD_DBID: Final = 'dbid'
    FIELD_URL: Final = 'url'
    SCENE_DB: Final = 'test_scenes'
    SCENE_COLLECTION: Final = 'scenes'

    def __init__(self, dbm: DBManager | None = None) -> None:
        config_file = Path(os.environ['CONF_AIT']) / 'aidb' / f'dbmanager_{self.SCENE_DB}.yaml'
        if dbm is None:
            self.dbm = DBManager(config_file=str(config_file))
        else:
            self.dbm = dbm

        # this is not necessary since mongo handles collection creation automatically
        # dbm.create_collection(self.SCENE_COLLECTION)

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
    def dbid_dotfile(cls, url: str | Path) -> None | str:
        data = cls._url_dotfile_load(url)
        if data is None:
            return None
        dbid = data.get(cls.FIELD_DBID, None)
        return dbid

    def dbid_db(self, url: str | Path) -> None | str:
        docs = self.dbm.find_documents(self.SCENE_COLLECTION, query={self.FIELD_URL: str(url)})
        size = len(docs)
        if size < 1:
            return None
        elif size == 1:
            dbid = docs[0]['_id']
        else:
            self._log(f'multiple db entries for {url}!', level='error')
            dbid = docs[0]['_id']
        return str(dbid)

    @property
    def dbids(self) -> Generator:
        """Returns a generator of scene dbid's for all scenes in the db"""

        docs = self.dbm.find_documents(self.SCENE_COLLECTION, query={})
        for doc in docs:
            yield str(doc['_id'])

    def url_update(self, url: str | Path) -> str | None:
        url = Path(url)
        if not url.exists():
            self._log(f'url does not exist: {url}')
            return
        elif not url.is_dir():
            self._log(f'url is not a dir: {url}')
            return

        dbid_dotfile = self.dbid_dotfile(url)
        self._log(f'{url} got dotfile dbid {dbid_dotfile}', level='debug')

        dbid = self.dbid_db(url)
        self._log(f'{url} got dbid {dbid}', level='debug')

        if dbid_dotfile is None:
            if dbid is None:
                # add new scene
                meta = self._meta_init_data(url=url)
                meta = self._scene_update(meta)
                if meta is not None:
                    dbid = meta.get(self.FIELD_DBID, None)
            data_dotfile = self._dotfile_init_data(dbid=dbid)
            self._dotfile_update(url, data_dotfile)
        else:
            if dbid is None:
                # update url in db with check of db url?
                self._log(f'DATABASE INCONSISTENCY: {url} has no dbidb, TODO fix!', level='error')
            elif dbid != dbid_dotfile:
                # update url in db with check of db url?
                self._log(
                    f'DATABASE INCONSISTENCY: {url} dotfile dbid does match to dbid, TODO fix!',
                    level='error',
                )
            else:
                # all good: scene db and dotfile consistent
                pass

        return dbid

    def _dotfile_init_data(self, dbid: str | None = None) -> dict:
        data = {}

        if not dbid:
            dbid = None
        if dbid is not None:
            data |= {self.FIELD_DBID: str(dbid)}

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
            data |= {self.FIELD_URL: str(url)}
        return data

    def _scene_update(self, meta: dict) -> dict | None:
        url = meta.get(self.FIELD_URL, '')
        if not url:
            self._log('no url found in meta!')
            return None

        # does scene url already exist?
        dbid = self.dbid_db(url)
        if dbid is None:
            dbid = self.dbm.insert_document(self.SCENE_COLLECTION, meta)
            self._log('scene added: {url}.', level='message')
        else:
            self._log(f'scene not added, already exists: {url} dbid={dbid}.', level='debug')

        if dbid:
            meta |= {self.FIELD_DBID: dbid}

        return meta

    def scene_new(self, _urls: list[str] | list[Path] | str | Path) -> list[str] | None:
        if not isinstance(_urls, list):
            urls = [_urls]
        else:
            urls = _urls
        urls_img = [Path(url) for url in urls if is_img_or_vid(url)]

        ret = []
        if urls_img:
            dbid = self._scene_new_imgs(urls_img)
            if dbid is not None:
                ret.append(dbid)

        dirs = [Path(url) for url in urls if is_dir(url)]
        for dir in dirs:
            dbid = self._scene_new_dir(dir)
            if dbid is not None:
                ret.append(dbid)

    def _scene_new_imgs(self, url_imgs: list[str] | list[Path]) -> None | str:
        """
        private: makes a new scene from a list of img urls.

        url_imgs should be completely valid (e.g. generated by is_img_or_vid(), they're not gonna be checked again.

        returns the new dbid:str
        """

        if not url_imgs:
            return None

        # physical files movement
        dir_scene = subdir_inc(self.dbm._root)
        urls_to_dir(url_imgs, dir_scene)

        # db entry
        dbid = self.url_update(dir_scene)

        return dbid

    def _scene_new_dir(self, dir: str | Path) -> None | str:
        return self._scene_new_imgs(imgs_from_url(dir))

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
        print(f'[scm:{level}] {msg}')
