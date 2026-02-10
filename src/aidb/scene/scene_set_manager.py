import os
from pathlib import Path
from typing import Any, Generator, Literal, Optional
import json

from bson import ObjectId

from aidb.dbmanager import DBManager
from .scene_common import SceneDef


class SceneSetManager:
    def __init__(
        self,
        dbm: DBManager | None = None,
        config: Literal['test', 'prod', 'default'] = 'default',
        verbose: int = 1,
    ) -> None:
        self._verbose = verbose
        if config == 'prod':
            self.config = SceneDef.CONFIG_PROD
        elif config == 'test':
            self.config = SceneDef.CONFIG_TEST
        else:
            self.config = SceneDef.CONFIG_DEFAULT
        self.config_file = Path(os.environ['CONF_AIT']) / 'aidb' / f'dbmanager_{self.config}.yaml'
        if dbm is None:
            self._dbm = DBManager(config_file=str(self.config_file), verbose=self._verbose)
        else:
            self._dbm = dbm

        self._collection = SceneDef.COLLECTION_SETS

    def _oid_from_name(self, name: str) -> Optional[ObjectId]:
        data = self.data_from_name(name)
        if data is None:
            return None
        id = data.get(SceneDef.FIELD_OID, None)
        if id is None:
            return None
        return id

    def id_from_name(self, name: str) -> Optional[str]:
        oid = self._oid_from_name(name)
        if oid is None:
            return None
        return str(oid)

    @property
    def ids(self) -> Generator:
        """Returns a generator of image oid's for all images in the db"""

        docs = self._dbm.find_documents(self._collection, query={})
        for doc in docs:
            yield str(doc['_id'])

    def data_from_id(self, id: Any) -> dict | None:
        oid = self._dbm.to_oid(id)
        if oid is None:
            return None
        docs = self._dbm.documents_from_oid(self._collection, oid)
        if len(docs) == 0:
            return None
        elif len(docs) == 1:
            return docs[0]

        self._log(f'DATABASE INCONSISTENCY: id {id} is multiple', level='error')
        return None

    def data_from_name(self, name: str) -> dict | None:
        docs = self._dbm.find_documents(self._collection, query={SceneDef.FIELD_NAME: name})
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

    @property
    def _dbc_sets(self):
        return self._dbm._get_collection(self._collection)

    def make_new_set(
        self, name: str, descr: Optional[str] = None, query: Optional[dict] = None
    ) -> Optional[str]:
        data = {SceneDef.FIELD_NAME: name}
        if descr is not None:
            data |= {SceneDef.FIELD_DESCRIPTION: descr}
        if query is not None:
            data |= {SceneDef.FIELD_QUERY: query}

        id = self._db_insert_set(data)

        return id

    def _dbc_to_id(self, id: str):
        self._dbm.to_oid(id)

    def _db_insert_set(self, data: dict) -> str | None:
        name = data.get(SceneDef.FIELD_NAME, None)
        if name is None:
            return None

        set_data = data.copy()
        set_data.pop(SceneDef.FIELD_OID, None)
        id = self._dbm.insert_document(self._collection, set_data)

        return id

    def _db_update_set(self, data: dict) -> bool:
        dbc = self._dbc_sets
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

    def set_from_id_or_name(self, id_or_name: str) -> Any:
        from .scene_set import SceneSet

        self._log(f'make scene set from: [{str(id_or_name)}]', 'debug')
        return SceneSet(self, id_or_name)

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
