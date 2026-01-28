from aidb.scene_manager import SceneManager
from aidb.scene_common import SceneDef


class TestSceneManager:
    def test_instance(self):
        scm = SceneManager(config=SceneDef.CONFIG_TEST)

        assert isinstance(scm, SceneManager)
        assert isinstance(scm, int)

    def test_scenes_update(self):
        scm = SceneManager(config=SceneDef.CONFIG_TEST)
        scm.scenes_update()

        assert True
