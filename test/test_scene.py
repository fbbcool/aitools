from aidb import SceneManager, HFDataset


class TestSceneManager:
    def test_instance(self):
        scm = SceneManager(config='test')

        assert isinstance(scm, SceneManager)
        assert isinstance(scm, int)

    def test_scenes_update(self):
        scm = SceneManager(config='test')
        scm.scenes_update()

        assert True


class TestHFDataset:
    def test_instance(self):
        repo_id = 'fbbcool/1tng-v1'
        hfd = HFDataset(repo_id)

        assert len(hfd) != 0
        assert True
