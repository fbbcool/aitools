from typing import Final, Optional, cast

from aidb import SceneDef, SceneConfig, SceneManager, SceneImageManager, SceneImage, Scene
from ait.tools.scenes import scene_id_from_url
from .joy import Joy


class JoySceneDB:
    TRIGGER_DEFAULT: Final = '1xlasm'

    def __init__(
        self, config: SceneConfig, trigger: str = '', verbose: int = 0, force: bool = False
    ):
        self._dbconfig: SceneConfig = config
        self._verbose = verbose
        self._force = force
        self._scm: SceneManager = SceneManager(config=self._dbconfig, verbose=self._verbose)
        self._sim: SceneImageManager = self._scm.scene_image_manager()
        self._trigger: str = trigger
        if not self._trigger:
            self._trigger = self.TRIGGER_DEFAULT
            self._log(f'trigger not set, set to default [{self._trigger}].')

        self.__joy: Optional[Joy] = None

    def _ids_caption(self, ids: list[str]) -> dict[str, str]:
        """
        returns a dict of {id: caption}.
        """
        ret = {}
        for id in ids:
            prompt, caption = self._id_caption(id)
            if caption is None:
                continue
            ret |= {id: {SceneDef.FIELD_PROMPT: prompt, SceneDef.FIELD_CAPTION: caption}}
        return ret

    def _id_caption(self, id: str) -> tuple[Optional[str], Optional[str]]:
        try:
            simg = cast(SceneImage, self._sim.img_from_id(id))
        except Exception as e:
            self._log(f'id [{id}]: {e}')
            return None, None

        img = simg.pil
        if img is None:
            return None, None

        caption_joy_current = simg.data.get(SceneDef.FIELD_CAPTION_JOY, None)
        if (caption_joy_current is not None) and (not self._force):
            return None, None

        url = simg.url_from_data
        if url is None:
            return None, None
        id_scene = scene_id_from_url(url)
        if id_scene is None:
            return None, None

        scene: Scene = self._scm.scene_from_id_or_url(id_scene)

        labels = scene.data.get(SceneDef.FIELD_LABELS, [])
        hint = ''

        prompt, caption = self._joy.img_caption(img, labels=labels, hint=hint)
        return prompt, caption

    @property
    def _joy(self) -> Joy:
        if self.__joy is None:
            self.__joy = Joy(trigger=self._trigger)
        return self.__joy

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[JoySceneDB:{level}] {msg}')
