"""Tests for the scene self-scan framework (board task 69): Scene.scan /
SceneManager.scan_all, the pure DB-timestamp skip rule against the task-70
timestamp contract, and the first property (scene embedding — mean +
component-wise 3·sigma over ALL folder images). Needs the reachable test
MongoDB (conf/aidb/dbc_scenes_test.yaml) and the dinov2:small model (same
dependency as test_images_embed.py); scenes are created under a dedicated
subdir of the test root and cleaned up per test."""

import shutil
from pathlib import Path

import pytest
from PIL import Image

from aidb import SceneManager
from aidb.scene.scene_common import SceneDef
from ait.tools.images import EMBED_MODEL_DEFAULT

SUBDIR = 'test_scan69'
DIM = 384  # dinov2:small


def _png(path: Path, color: tuple[int, int, int] = (10, 20, 30)) -> Path:
    Image.new('RGB', (32, 32), color=color).save(path)
    return path


def _ts_updated(scm, scene_id: str) -> float:
    return scm.data_from_id(scene_id).get(SceneDef.FIELD_TIMESTAMP_UPDATED, 0.0)


def _scan_embedding(scm, scene_id: str) -> dict | None:
    scan = scm.data_from_id(scene_id).get(SceneDef.FIELD_SCAN) or {}
    return scan.get(SceneDef.SCAN_PROP_EMBEDDING)


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


def _scene_two_imgs(scm, tmp_path) -> str:
    """The acceptance setup: a scene with two images, one registered, one
    unregistered."""
    a = _png(tmp_path / 'a.png', color=(200, 30, 30))
    b = _png(tmp_path / 'b.png', color=(30, 30, 200))
    sid = scm.new_scene_from_urls([a, b], subdir_scenes=SUBDIR)[0]
    sim = scm.scene_image_manager()
    assert sim.register_from_url(Path(scm.url_from_id(sid)) / 'a.png') is not None
    return sid


class TestScanEmbedding:
    def test_scan_writes_embedding(self, scm, tmp_path):
        sid = _scene_two_imgs(scm, tmp_path)
        ts_before = _ts_updated(scm, sid)

        res = scm.scene_from_id_or_url(sid).scan()

        assert res == {SceneDef.SCAN_PROP_EMBEDDING: 'computed'}
        emb = _scan_embedding(scm, sid)
        assert emb is not None
        assert emb[SceneDef.FIELD_SCAN_MODEL] == EMBED_MODEL_DEFAULT
        assert emb[SceneDef.FIELD_SCAN_N_IMGS] == 2  # counts the unregistered file
        assert len(emb[SceneDef.FIELD_SCAN_MEAN]) == DIM
        assert len(emb[SceneDef.FIELD_SCAN_SIGMA3]) == DIM
        assert emb[SceneDef.FIELD_SCAN_TS] > 0.0
        # the scan write itself must NOT bump timestamp_updated (it would
        # mark the scene stale for its own skip rule)
        assert _ts_updated(scm, sid) == ts_before
        # and the property ts is not older than the scene ts → fresh
        assert emb[SceneDef.FIELD_SCAN_TS] >= ts_before

    def test_second_scan_skips(self, scm, tmp_path):
        sid = _scene_two_imgs(scm, tmp_path)
        assert scm.scene_from_id_or_url(sid).scan() == {SceneDef.SCAN_PROP_EMBEDDING: 'computed'}
        ts0 = _scan_embedding(scm, sid)[SceneDef.FIELD_SCAN_TS]

        res = scm.scene_from_id_or_url(sid).scan()

        assert res == {SceneDef.SCAN_PROP_EMBEDDING: 'skipped'}
        assert _scan_embedding(scm, sid)[SceneDef.FIELD_SCAN_TS] == ts0

    def test_doc_write_triggers_recompute(self, scm, tmp_path):
        sid = _scene_two_imgs(scm, tmp_path)
        scm.scene_from_id_or_url(sid).scan()
        ts0 = _scan_embedding(scm, sid)[SceneDef.FIELD_SCAN_TS]

        scene = scm.scene_from_id_or_url(sid)
        scene.db_store()  # full-doc store bumps timestamp_updated

        res = scm.scene_from_id_or_url(sid).scan()

        assert res == {SceneDef.SCAN_PROP_EMBEDDING: 'computed'}
        assert _scan_embedding(scm, sid)[SceneDef.FIELD_SCAN_TS] > ts0

    def test_force_recomputes(self, scm, tmp_path):
        sid = _scene_two_imgs(scm, tmp_path)
        scm.scene_from_id_or_url(sid).scan()
        ts0 = _scan_embedding(scm, sid)[SceneDef.FIELD_SCAN_TS]

        res = scm.scene_from_id_or_url(sid).scan(force=True)

        assert res == {SceneDef.SCAN_PROP_EMBEDDING: 'computed'}
        assert _scan_embedding(scm, sid)[SceneDef.FIELD_SCAN_TS] > ts0

    def test_model_mismatch_triggers_recompute(self, scm, tmp_path):
        sid = _scene_two_imgs(scm, tmp_path)
        scm.scene_from_id_or_url(sid).scan()
        # rewrite the stored model directly — no timestamp change involved
        field = f'{SceneDef.FIELD_SCAN}.{SceneDef.SCAN_PROP_EMBEDDING}.{SceneDef.FIELD_SCAN_MODEL}'
        scm._dbc_scenes.update_one(
            {SceneDef.FIELD_OID: scm._dbc.to_oid(sid)}, {'$set': {field: 'dinov2:other'}}
        )

        res = scm.scene_from_id_or_url(sid).scan()

        assert res == {SceneDef.SCAN_PROP_EMBEDDING: 'computed'}
        assert _scan_embedding(scm, sid)[SceneDef.FIELD_SCAN_MODEL] == EMBED_MODEL_DEFAULT

    def test_membership_add_triggers_recompute(self, scm, tmp_path):
        # integration with the task-70 contract: img_add bumps → next scan
        # recomputes and sees the new file
        sid = _scene_two_imgs(scm, tmp_path)
        scm.scene_from_id_or_url(sid).scan()

        third = _png(tmp_path / 'c.png', color=(30, 200, 30))
        assert scm.img_add(third, sid) == sid

        res = scm.scene_from_id_or_url(sid).scan()

        assert res == {SceneDef.SCAN_PROP_EMBEDDING: 'computed'}
        assert _scan_embedding(scm, sid)[SceneDef.FIELD_SCAN_N_IMGS] == 3

    def test_empty_scene_fails_property(self, scm, tmp_path):
        sid = _scene_two_imgs(scm, tmp_path)
        scene_dir = Path(scm.url_from_id(sid))
        assert scm.img_delete(scene_dir / 'b.png') is True
        for f in list(scene_dir.iterdir()):
            if f.is_file() and f.suffix == '.png':
                scm.img_delete(f)

        res = scm.scene_from_id_or_url(sid).scan()

        assert res == {SceneDef.SCAN_PROP_EMBEDDING: 'failed'}
        assert _scan_embedding(scm, sid) is None

    def test_unknown_property(self, scm, tmp_path):
        sid = _scene_two_imgs(scm, tmp_path)
        res = scm.scene_from_id_or_url(sid).scan(props=['no_such_prop'])
        assert res == {'no_such_prop': 'unknown'}


class TestScanAll:
    def test_sweep_query_restricted_then_free(self, scm, tmp_path):
        sid_a = _scene_two_imgs(scm, tmp_path)
        b = _png(tmp_path / 'solo.png', color=(120, 120, 40))
        sid_b = scm.new_scene_from_urls([b], subdir_scenes=SUBDIR)[0]
        query = {SceneDef.FIELD_URL: {'$regex': f'/{SUBDIR}/'}}

        first = scm.scan_all(query=query)

        assert set(first) == {sid_a, sid_b}
        assert first[sid_a] == {SceneDef.SCAN_PROP_EMBEDDING: 'computed'}
        assert first[sid_b] == {SceneDef.SCAN_PROP_EMBEDDING: 'computed'}

        second = scm.scan_all(query=query)

        assert second[sid_a] == {SceneDef.SCAN_PROP_EMBEDDING: 'skipped'}
        assert second[sid_b] == {SceneDef.SCAN_PROP_EMBEDDING: 'skipped'}
