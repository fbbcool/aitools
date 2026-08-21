"""Tests for the canonical img-membership API (board task 70): img_add /
img_delete / img_move and the timestamp contract — every real membership
change bumps ``timestamp_updated`` of every involved scene, no bump on no-op
or abort. Needs the reachable test MongoDB (conf/aidb/dbc_scenes_test.yaml);
scenes are created under a dedicated subdir of the test root and cleaned up
per test."""

import shutil
from pathlib import Path

import pytest
from PIL import Image

from aidb import SceneManager
from aidb.scene.scene_common import SceneDef

SUBDIR = 'test_member70'


def _png(path: Path, color: tuple[int, int, int] = (10, 20, 30)) -> Path:
    Image.new('RGB', (8, 8), color=color).save(path)
    return path


def _ts(scm, scene_id: str) -> float:
    return scm.data_from_id(scene_id).get(SceneDef.FIELD_TIMESTAMP_UPDATED, 0.0)


def _scene(scm, tmp_path, name: str = 'seed.png', color: tuple[int, int, int] = (1, 2, 3)) -> str:
    seed = _png(tmp_path / name, color=color)
    return scm.new_scene_from_urls([seed], subdir_scenes=SUBDIR)[0]


@pytest.fixture
def scm():
    scm = SceneManager(config='test', verbose=0)
    yield scm
    query = {SceneDef.FIELD_URL: {'$regex': f'/{SUBDIR}/'}}
    for sid in list(scm.ids_from_query(query)):
        scm._dbc.delete_document(
            SceneDef.COLLECTION_SCENES, {SceneDef.FIELD_OID: scm._dbc.to_oid(sid)}
        )
    scm._dbc.delete_document(
        SceneDef.COLLECTION_IMAGES, {SceneDef.FIELD_URL_PARENT: {'$regex': f'/{SUBDIR}/'}}
    )
    base = Path(scm.root) / SUBDIR
    if base.is_dir():
        shutil.rmtree(base)


class TestSceneTimestamps:
    def test_new_scene_born_with_timestamps(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        data = scm.data_from_id(sid)
        assert data.get(SceneDef.FIELD_TIMESTAMP_CREATED, 0.0) > 0.0
        assert data.get(SceneDef.FIELD_TIMESTAMP_UPDATED, 0.0) > 0.0

    def test_scene_touch_bumps_only_the_timestamp(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        before = scm.data_from_id(sid)
        assert scm.scene_touch(sid) is True
        after = scm.data_from_id(sid)
        assert after[SceneDef.FIELD_TIMESTAMP_UPDATED] > before[SceneDef.FIELD_TIMESTAMP_UPDATED]
        before.pop(SceneDef.FIELD_TIMESTAMP_UPDATED)
        after.pop(SceneDef.FIELD_TIMESTAMP_UPDATED)
        assert before == after

    def test_scene_touch_unknown_scene_is_false(self, scm):
        assert scm.scene_touch('0' * 24) is False


class TestImgAdd:
    def test_add_lands_and_bumps(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        ts0 = _ts(scm, sid)
        src = _png(tmp_path / 'new.png', color=(4, 4, 4))

        res = scm.img_add(src, sid)

        assert res == sid
        assert not src.is_file()  # move=True default
        assert (Path(scm.url_from_id(sid)) / 'new.png').is_file()
        assert _ts(scm, sid) > ts0

    def test_add_copy_keeps_source(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        src = _png(tmp_path / 'copy.png', color=(5, 5, 5))

        res = scm.img_add(src, sid, move=False)

        assert res == sid
        assert src.is_file()
        assert (Path(scm.url_from_id(sid)) / 'copy.png').is_file()

    def test_byte_identical_readd_is_noop_no_bump(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        src = _png(tmp_path / 'dup.png', color=(6, 6, 6))
        copy = tmp_path / 'copydir' / 'dup.png'
        copy.parent.mkdir()
        shutil.copy2(src, copy)
        assert scm.img_add(src, sid) == sid
        ts0 = _ts(scm, sid)

        res = scm.img_add(copy, sid)

        assert res == sid
        assert not copy.is_file()  # move=True removed the re-added source
        assert _ts(scm, sid) == ts0  # membership unchanged: no bump

    def test_collision_aborts_no_bump(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        other = _png(tmp_path / 'seed.png', color=(9, 9, 9))  # same name, other content
        ts0 = _ts(scm, sid)

        res = scm.img_add(other, sid)

        assert res is False
        assert other.is_file()  # source untouched
        assert _ts(scm, sid) == ts0


class TestImgDelete:
    def test_delete_unregistered_bumps(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        target = Path(scm.url_from_id(sid)) / 'seed.png'
        ts0 = _ts(scm, sid)

        assert scm.img_delete(target) is True

        assert not target.is_file()
        assert _ts(scm, sid) > ts0

    def test_delete_registered_removes_doc_and_file(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        sim = scm.scene_image_manager()
        oid = sim.register_from_url(Path(scm.url_from_id(sid)) / 'seed.png')
        assert oid is not None
        reg_file = Path(scm.url_from_id(sid)) / f'0rig{SceneDef.SEPERATOR_ID}{oid}.png'
        assert reg_file.is_file()
        ts0 = _ts(scm, sid)

        assert scm.img_delete(reg_file) is True

        assert not reg_file.is_file()
        assert sim.is_id(oid) is False  # hard delete, documented semantics
        assert _ts(scm, sid) > ts0

    def test_delete_registered_by_id_with_missing_file(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        sim = scm.scene_image_manager()
        oid = sim.register_from_url(Path(scm.url_from_id(sid)) / 'seed.png')
        reg_file = Path(scm.url_from_id(sid)) / f'0rig{SceneDef.SEPERATOR_ID}{oid}.png'
        reg_file.unlink()
        ts0 = _ts(scm, sid)

        assert scm.img_delete(oid) is True

        assert sim.is_id(oid) is False
        assert _ts(scm, sid) > ts0

    def test_delete_outside_scene_refused(self, scm, tmp_path):
        loose = _png(tmp_path / 'loose.png')

        assert scm.img_delete(loose) is False
        assert loose.is_file()


class TestImgMove:
    def test_move_unregistered_bumps_both(self, scm, tmp_path):
        src_sid = _scene(scm, tmp_path, name='a.png', color=(1, 1, 1))
        dst_sid = _scene(scm, tmp_path, name='b.png', color=(2, 2, 2))
        moving = Path(scm.url_from_id(src_sid)) / 'a.png'
        ts_src = _ts(scm, src_sid)
        ts_dst = _ts(scm, dst_sid)

        res = scm.img_move(moving, dst_sid)

        assert res == dst_sid
        assert not moving.is_file()
        assert (Path(scm.url_from_id(dst_sid)) / 'a.png').is_file()
        assert _ts(scm, src_sid) > ts_src
        assert _ts(scm, dst_sid) > ts_dst

    def test_move_registered_keeps_doc_consistent(self, scm, tmp_path):
        src_sid = _scene(scm, tmp_path, name='a.png', color=(1, 1, 1))
        dst_sid = _scene(scm, tmp_path, name='b.png', color=(2, 2, 2))
        sim = scm.scene_image_manager()
        oid = sim.register_from_url(Path(scm.url_from_id(src_sid)) / 'a.png')
        assert oid is not None
        ts_src = _ts(scm, src_sid)
        ts_dst = _ts(scm, dst_sid)

        res = scm.img_move(oid, dst_sid)

        assert res == dst_sid
        img = sim.img_from_id(oid)
        assert img.scene_id == dst_sid  # doc resolves to the target scene
        assert img.url_from_data.is_file()  # doc ↔ file consistent
        assert img.url_from_data.parent == Path(scm.url_from_id(dst_sid))
        assert _ts(scm, src_sid) > ts_src
        assert _ts(scm, dst_sid) > ts_dst

    def test_move_same_scene_is_noop_no_bump(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        target = Path(scm.url_from_id(sid)) / 'seed.png'
        ts0 = _ts(scm, sid)

        res = scm.img_move(target, sid)

        assert res == sid
        assert target.is_file()
        assert _ts(scm, sid) == ts0

    def test_move_from_outside_acts_as_add(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        loose = _png(tmp_path / 'loose.png', color=(7, 7, 7))
        ts0 = _ts(scm, sid)

        res = scm.img_move(loose, sid)

        assert res == sid
        assert not loose.is_file()
        assert (Path(scm.url_from_id(sid)) / 'loose.png').is_file()
        assert _ts(scm, sid) > ts0

    def test_move_collision_aborts_no_bump(self, scm, tmp_path):
        src_sid = _scene(scm, tmp_path, name='a.png', color=(1, 1, 1))
        dst_sid = _scene(scm, tmp_path, name='b.png', color=(2, 2, 2))
        # same name, different content already in the target
        clash = _png(tmp_path / 'clash.png', color=(3, 3, 3))
        assert scm.img_add(clash, dst_sid) == dst_sid
        moving = _png(Path(scm.url_from_id(src_sid)) / 'clash.png', color=(4, 4, 4))
        scm.scene_touch(src_sid)  # settle a fresh baseline after the manual drop
        ts_src = _ts(scm, src_sid)
        ts_dst = _ts(scm, dst_sid)

        res = scm.img_move(moving, dst_sid)

        assert res is False
        assert moving.is_file()  # source untouched
        assert _ts(scm, src_sid) == ts_src
        assert _ts(scm, dst_sid) == ts_dst


class TestAdoptBumps:
    """Acceptance line of board task 70: a successful adoption (any
    resolution path) advances the adopting scene's timestamp_updated."""

    def test_payloadless_adopt_bumps(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        img_in_scene = Path(scm.url_from_id(sid)) / 'seed.png'
        ts0 = _ts(scm, sid)

        loose = _png(tmp_path / 'derived.png', color=(6, 5, 4))
        import json

        from PIL.PngImagePlugin import PngInfo

        info = PngInfo()
        info.add_text('parent_metadata', json.dumps({'url': str(img_in_scene)}))
        Image.new('RGB', (8, 8), color=(6, 5, 4)).save(loose, pnginfo=info)

        res = scm.scene_adopt_img(loose)

        assert res == sid
        assert _ts(scm, sid) > ts0

    def test_payloadless_adopt_collision_no_bump(self, scm, tmp_path):
        sid = _scene(scm, tmp_path)
        img_in_scene = Path(scm.url_from_id(sid)) / 'seed.png'
        ts0 = _ts(scm, sid)

        import json

        from PIL.PngImagePlugin import PngInfo

        info = PngInfo()
        info.add_text('parent_metadata', json.dumps({'url': str(img_in_scene)}))
        clash = tmp_path / 'seed.png'  # collides with the scene's own file
        Image.new('RGB', (8, 8), color=(9, 8, 7)).save(clash, pnginfo=info)

        res = scm.scene_adopt_img(clash)

        assert res is False
        assert _ts(scm, sid) == ts0
