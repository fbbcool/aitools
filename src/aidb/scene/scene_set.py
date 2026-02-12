import pprint
from typing import Final, Generator

from jsonlines import jsonlines

from ait.tools.files import url_clean
from ait.tools.images import train_from_image


from .scene_common import SceneDef
from .scene_set_manager import SceneSetManager


class SceneSet:
    QUERY_IMG_DEFAULT: Final = {SceneDef.FIELD_RATING: {'$gte': SceneDef.RATING_INIT}}

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
    def query_img(self) -> dict:
        return self._data.get(SceneDef.FIELD_QUERY_IMG, self.QUERY_IMG_DEFAULT)

    @property
    def id(self) -> str:
        return str(self._data.get(SceneDef.FIELD_OID, ''))

    def update(self) -> None:
        self._ssm._db_update_set(self.data)
        return

    @property
    def ids_scene(self) -> Generator:
        scm = self._ssm.scene_manager()
        for id_scene in scm.ids_from_query(self.query):
            yield id_scene

    @property
    def scenes(self) -> Generator:
        scm = self._ssm.scene_manager()
        for id_scene in scm.ids_from_query(self.query):
            scene = scm.scene_from_id_or_url(id_scene)
            if scene is None:
                continue
            yield scene

    @property
    def ids_img(self) -> Generator:
        from .scene import Scene

        scene: Scene
        for scene in self.scenes:
            for id_img in scene.ids_img_from_query(self.query_img):
                yield id_img

    @property
    def imgs(self) -> Generator:
        from .scene import Scene

        scene: Scene
        for scene in self.scenes:
            for img in scene.imgs_from_query(self.query_img):
                yield img

    def compile(self) -> None:
        from .scene_image import SceneImage

        # first, make a clean saving location
        root_train = self._ssm.config.train_url / self.name
        url_clean(root_train)
        metadata = []
        ratios = self.data.get(SceneDef.FIELD_RATIOS, SceneDef.DEFAULT_RATIOS)
        ratios = [float(ratio) for ratio in ratios]
        resolutions = self.data.get(SceneDef.FIELD_RESOLUTIONS, SceneDef.DEFAULT_RESOLUTIONS)

        for img in self.imgs:
            img: SceneImage
            pil = img.pil
            if pil is None:
                continue
            metadata.append(img.train_metadata_jsonl)
            pil_train = train_from_image(pil, ratios=ratios, resolutions=resolutions)
            if pil_train is None:
                continue
            url_trainfile = root_train / img.filename_train_from_data
            url_trainfile.parent.mkdir(parents=True, exist_ok=True)
            pil_train.save(url_trainfile)

        url_metafile = root_train / 'metadata.jsonl'
        with jsonlines.open(url_metafile, mode='w') as writer:
            writer.write_all(metadata)

    def __str__(self) -> str:
        ret = 'data: ' + pprint.pformat(self.data)
        return ret
