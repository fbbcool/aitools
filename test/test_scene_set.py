from aidb import SceneSet


class TestSceneSet:
    def test_instance(self):
        from aidb import SceneSetManager

        ssm = SceneSetManager(config='test')

        set_id = '698dd237952c3779c62de2bf'
        sset = ssm.set_from_id_or_name(set_id)

        imgs = [img for img in sset.ids_img]

        assert sset is not None
        assert sset
        assert imgs is not None
        assert imgs
