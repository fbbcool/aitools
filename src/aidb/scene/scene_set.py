import pprint

from .scene_common import SceneDef
from .scene_set_manager import SceneSetManager


class SceneSet:
    def __init__(
        self,
        ssm: SceneSetManager,
        name_or_id: str,
    ) -> None:
        """
        Set of Scenes.

        :return: None
        """
        self._ssm: SceneSetManager = ssm

        data = self._ssm.data_from_name(name_or_id)
        if data is None:
            data = self._ssm.data_from_id(name_or_id)
        if data is None:
            raise (ValueError('Scene Set: name not found!'))
        self._data: dict = data

    @property
    def data(self) -> dict:
        return self._data

    @property
    def name(self) -> str:
        name = self._data.get(SceneDef.FIELD_NAME, None)
        if name is None:
            raise ValueError('nameless set!')
        return name

    @property
    def description(self) -> str:
        return self._data.get(SceneDef.FIELD_DESCRIPTION, '')

    @property
    def query(self) -> dict:
        return self._data.get(SceneDef.FIELD_QUERY, {})

    @property
    def id(self) -> str:
        return str(self._data.get(SceneDef.FIELD_OID, ''))

    def update(self) -> None:
        self._ssm._db_update_set(self.data)
        return

    def compile(self) -> None:
        pass

    def __str__(self) -> str:
        ret = 'data: ' + pprint.pformat(self.data)
        return ret
