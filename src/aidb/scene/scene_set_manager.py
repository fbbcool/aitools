from pathlib import Path
from typing import Any, Generator, Optional
import json

from bson import ObjectId

from .db_connect import DBConnection
from .scene_common import SceneDef, SceneConfig
from .scene_manager import SceneManager


class SceneSetManager:
    def __init__(
        self,
        dbc: DBConnection | None = None,
        config: SceneConfig = 'default',
        verbose: int = 1,
    ) -> None:
        if dbc is None:
            self._verbose = verbose
            self._dbc = DBConnection(config=config, verbose=self._verbose)
        else:
            self._dbc = dbc
            self._verbose = self._dbc._verbose

        self._collection = SceneDef.COLLECTION_SETS

    @property
    def config(self):
        return self._dbc.config

    @property
    def root(self) -> Path:
        return self._dbc.config.root

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
        """Returns a generator of oids for all sets in the db"""

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

    def data_from_name(self, name: str) -> dict | None:
        docs = self._dbc.find_documents(self._collection, query={SceneDef.FIELD_NAME: name})
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
        return self._dbc._get_collection(self._collection)

    def make_new(
        self,
        name: str,
        descr: Optional[str] = None,
        query: Optional[dict] = None,
        trigger: Optional[str] = None,
    ) -> Optional[str]:
        data = {SceneDef.FIELD_NAME: name}
        if descr is not None:
            data |= {SceneDef.FIELD_DESCRIPTION: descr}
        if query is not None:
            data |= {SceneDef.FIELD_QUERY: query}
        if trigger is not None:
            data |= {SceneDef.FIELD_TRIGGER: trigger}

        id = self._db_insert_set(data)

        return id

    def _dbc_to_id(self, id: str):
        self._dbc.to_oid(id)

    def _db_insert_set(self, data: dict) -> str | None:
        name = data.get(SceneDef.FIELD_NAME, None)
        if name is None:
            return None

        set_data = data.copy()
        set_data.pop(SceneDef.FIELD_OID, None)
        id = self._dbc.insert_document(self._collection, set_data)

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

    def scene_manager(self) -> SceneManager:
        return SceneManager(self._dbc, verbose=self._verbose)

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
            print(f'[ssm:{level}] {msg}')
