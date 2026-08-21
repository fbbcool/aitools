"""Tests for scene_adopt_img enhancer-payload routing (board task 66) and the
task-65 parent-chain regression. Needs the reachable test MongoDB
(conf/aidb/dbc_scenes_test.yaml); scenes are created under a dedicated subdir
of the test root and cleaned up per test."""

import json
import os
import shutil
import uuid
from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from aidb import SceneManager
from aidb.scene.scene_common import SceneDef

SUBDIR = 'test_adopt66'


def _png(path: Path, color: tuple[int, int, int], chunks: dict[str, dict] | None = None) -> Path:
    img = Image.new('RGB', (8, 8), color=color)
    info = PngInfo()
    for key, obj in (chunks or {}).items():
        info.add_text(key, json.dumps(obj))
    img.save(path, pnginfo=info)
    return path


def _payload_png(
    path: Path,
    id_enh: str,
    color: tuple[int, int, int] = (10, 20, 30),
    url_origin: str = '/nonexistent/source.png',
) -> Path:
    """A render whose parent envelope embeds an enhancer iteration payload —
    the inheritance path of `metadata()` (non-metadata-schema envelope).
    `url_origin` is the payload's canonical enhancer-scene image path, the
    only bridge to the origin DB scene."""
    payload = {
        'schema_id': '1xlasm_enhancer.iteration.v4',
        'scene_id': id_enh,
        'url': url_origin,
        'prompts': {'current': 0, 'entries': ['test prompt']},
    }
    return _png(path, color, chunks={'parent_metadata': {'input_data': payload}})


def _linked(scm, scene_id: str) -> dict:
    return SceneDef.scenes_linked_from_data(scm.data_from_id(scene_id))


def _sourced(scm, scene_id: str) -> list[str]:
    return _linked(scm, scene_id)[SceneDef.FIELD_IDS_SCENE_DB][SceneDef.FIELD_LINKED_SOURCED]


@pytest.fixture
def scm():
    scm = SceneManager(config='test', verbose=0)
    yield scm
    query = {SceneDef.FIELD_URL: {'$regex': f'/{SUBDIR}/'}}
    for sid in list(scm.ids_from_query(query)):
        scm._dbc.delete_document(
            SceneDef.COLLECTION_SCENES, {SceneDef.FIELD_OID: scm._dbc.to_oid(sid)}
        )
    base = Path(scm.root) / SUBDIR
    if base.is_dir():
        shutil.rmtree(base)


class TestSceneAdoptEnh:
    def test_unmatched_no_subdir_is_distinct_noop(self, scm, tmp_path):
        id_enh = uuid.uuid4().hex
        src = _payload_png(tmp_path / 'render.png', id_enh)

        res = scm.scene_adopt_img(src)

        assert res is None  # distinct from plain False (unresolvable)
        assert src.is_file()  # zero side effects
        assert scm.scene_ids_from_enh_id(id_enh) == []

    def test_unmatched_with_subdir_creates_seeded_scene(self, scm, tmp_path):
        id_enh = uuid.uuid4().hex
        src = _payload_png(tmp_path / 'render.png', id_enh)

        res = scm.scene_adopt_img(src, subdir_new=SUBDIR)

        assert isinstance(res, str)
        assert not src.is_file()  # moved
        url_scene = Path(scm.url_from_id(res))
        assert url_scene.is_dir() and (url_scene / 'render.png').is_file()
        assert url_scene.parent == Path(scm.root) / SUBDIR
        linked = _linked(scm, res)
        assert linked[SceneDef.FIELD_IDS_SCENE_ENH] == [id_enh]
        assert scm.scene_ids_from_enh_id(id_enh) == [res]
        # unresolvable origin: adoption proceeds, no sourced entry, miss
        # visible in the result instead of silent
        assert _sourced(scm, res) == []
        assert res.origin_unresolved is True
        assert res.id_origin is None

    def test_create_path_seeds_sourced_no_backlink(self, scm, tmp_path):
        origin_img = _png(tmp_path / 'origin.png', color=(3, 3, 3))
        id_origin = scm.new_scene_from_urls([origin_img], subdir_scenes=SUBDIR)[0]
        url_origin = str(Path(scm.url_from_id(id_origin)) / 'origin.png')

        id_enh = uuid.uuid4().hex
        src = _payload_png(tmp_path / 'render.png', id_enh, url_origin=url_origin)
        res = scm.scene_adopt_img(src, subdir_new=SUBDIR)

        assert isinstance(res, str) and res != id_origin
        assert res.origin_unresolved is False
        assert res.id_origin == id_origin
        assert _sourced(scm, res) == [id_origin]
        # ONE-WAY: the origin scene gets no backlink of any kind
        origin_linked = _linked(scm, id_origin)
        assert origin_linked[SceneDef.FIELD_IDS_SCENE_DB] == {
            SceneDef.FIELD_LINKED_NEIGHBORS: [],
            SceneDef.FIELD_LINKED_SOURCED: [],
        }

    def test_match_path_appends_sourced_dedup(self, scm, tmp_path):
        origin_a_img = _png(tmp_path / 'oa.png', color=(1, 1, 1))
        origin_a = scm.new_scene_from_urls([origin_a_img], subdir_scenes=SUBDIR)[0]
        url_a = str(Path(scm.url_from_id(origin_a)) / 'oa.png')
        origin_b_img = _png(tmp_path / 'ob.png', color=(2, 2, 2))
        origin_b = scm.new_scene_from_urls([origin_b_img], subdir_scenes=SUBDIR)[0]
        url_b = str(Path(scm.url_from_id(origin_b)) / 'ob.png')

        id_enh = uuid.uuid4().hex
        first = _payload_png(tmp_path / 'a.png', id_enh, url_origin=url_a)
        scene_id = scm.scene_adopt_img(first, subdir_new=SUBDIR)
        # second render of the same enhancer scene, different origin url
        second = _payload_png(tmp_path / 'b.png', id_enh, color=(9, 9, 9), url_origin=url_b)
        res = scm.scene_adopt_img(second)
        # third: origin_a again — must not duplicate
        third = _payload_png(tmp_path / 'c.png', id_enh, color=(8, 8, 8), url_origin=url_a)
        scm.scene_adopt_img(third)

        assert res == scene_id
        assert res.id_origin == origin_b
        assert _sourced(scm, scene_id) == [origin_a, origin_b]

    def test_match_routes_to_linked_scene_not_parent(self, scm, tmp_path):
        id_enh = uuid.uuid4().hex
        first = _payload_png(tmp_path / 'a.png', id_enh)
        scene_id = scm.scene_adopt_img(first, subdir_new=SUBDIR)

        second = _payload_png(tmp_path / 'b.png', id_enh, color=(99, 99, 99))
        res = scm.scene_adopt_img(second)  # no subdir_new needed anymore

        assert res == scene_id
        assert (Path(scm.url_from_id(scene_id)) / 'b.png').is_file()

    def test_byte_identical_readopt_is_idempotent(self, scm, tmp_path):
        id_enh = uuid.uuid4().hex
        src = _payload_png(tmp_path / 'a.png', id_enh)
        copy = tmp_path / 'copy' / 'a.png'
        copy.parent.mkdir()
        shutil.copy2(src, copy)
        scene_id = scm.scene_adopt_img(src, subdir_new=SUBDIR)

        res = scm.scene_adopt_img(copy)

        assert res == scene_id
        assert not copy.is_file()  # move=True removed the re-adopted source

    def test_multi_match_tiebreak_newest_mtime(self, scm, tmp_path):
        id_enh = uuid.uuid4().hex
        old = _payload_png(tmp_path / 'a.png', id_enh)
        scene_old = scm.scene_adopt_img(old, subdir_new=SUBDIR)
        plain = _png(tmp_path / 'plain.png', color=(1, 2, 3))
        scene_new = scm.new_scene_from_urls([plain], subdir_scenes=SUBDIR)[0]
        scm.link_scene_enh(scene_new, id_enh)

        for f in Path(scm.url_from_id(scene_old)).iterdir():
            os.utime(f, (0, 0))  # make the first scene's content old

        third = _payload_png(tmp_path / 'c.png', id_enh, color=(7, 7, 7))
        res = scm.scene_adopt_img(third)

        assert res == scene_new
        assert (Path(scm.url_from_id(scene_new)) / 'c.png').is_file()

    def test_new_scene_from_urls_seeds_links(self, scm, tmp_path):
        origin_img = _png(tmp_path / 'origin.png', color=(3, 3, 3))
        id_origin = scm.new_scene_from_urls([origin_img], subdir_scenes=SUBDIR)[0]
        url_origin = str(Path(scm.url_from_id(id_origin)) / 'origin.png')

        id_enh = uuid.uuid4().hex
        src = _payload_png(tmp_path / 'seeded.png', id_enh, url_origin=url_origin)
        scene_id = scm.new_scene_from_urls([src], subdir_scenes=SUBDIR)[0]

        linked = _linked(scm, scene_id)
        assert linked[SceneDef.FIELD_IDS_SCENE_ENH] == [id_enh]
        assert _sourced(scm, scene_id) == [id_origin]

    def test_seed_skips_self_link(self, scm, tmp_path):
        # historic case: a payload render already sits in its own origin scene
        # (pre-feature adoption) — seeding must not link the scene to itself
        placeholder = _png(tmp_path / 'x.png', color=(5, 5, 5))
        scene_id = scm.new_scene_from_urls([placeholder], subdir_scenes=SUBDIR)[0]
        url_scene = Path(scm.url_from_id(scene_id))
        id_enh = uuid.uuid4().hex
        _payload_png(url_scene / 'render.png', id_enh, url_origin=str(url_scene / 'x.png'))

        found = scm.scene_seed_enh_links(scene_id)

        assert found[SceneDef.FIELD_IDS_SCENE_ENH] == [id_enh]
        assert found[SceneDef.FIELD_LINKED_SOURCED] == []
        assert _sourced(scm, scene_id) == []

    def test_payloadless_parent_chain_unchanged(self, scm, tmp_path):
        # task-65 regression: no payload, parent envelope url resolves the scene
        plain = _png(tmp_path / 'orig.png', color=(4, 5, 6))
        scene_id = scm.new_scene_from_urls([plain], subdir_scenes=SUBDIR)[0]
        img_in_scene = Path(scm.url_from_id(scene_id)) / 'orig.png'

        loose = _png(
            tmp_path / 'derived.png',
            color=(6, 5, 4),
            chunks={'parent_metadata': {'url': str(img_in_scene)}},
        )
        res = scm.scene_adopt_img(loose)

        assert res == scene_id
        assert (Path(scm.url_from_id(scene_id)) / 'derived.png').is_file()

    def test_unresolvable_returns_false(self, scm, tmp_path):
        loose = _png(tmp_path / 'orphan.png', color=(9, 9, 9))

        res = scm.scene_adopt_img(loose)

        assert res is False
        assert loose.is_file()


class TestScenesLinkedSchema:
    EMPTY = {
        SceneDef.FIELD_IDS_SCENE_ENH: [],
        SceneDef.FIELD_IDS_SCENE_DB: {
            SceneDef.FIELD_LINKED_NEIGHBORS: [],
            SceneDef.FIELD_LINKED_SOURCED: [],
        },
    }

    def test_absent_field_reads_as_empty_structure(self):
        for data in (None, {}, {SceneDef.FIELD_SCENES_LINKED: None}):
            assert SceneDef.scenes_linked_from_data(data) == self.EMPTY

    def test_partial_and_malformed_ids_scene_db_reads_safe(self):
        # v1 docs (no ids_scene_db) and malformed values (flat list, str)
        # normalize to the empty two-list object — no crash, no garbage
        for ids_db in (None, [], ['legacy-flat-id'], 'junk', 42):
            data = {
                SceneDef.FIELD_SCENES_LINKED: {
                    SceneDef.FIELD_IDS_SCENE_DB: ids_db,
                }
            }
            assert SceneDef.scenes_linked_from_data(data) == self.EMPTY

    def test_sourced_and_neighbors_pass_through(self):
        data = {
            SceneDef.FIELD_SCENES_LINKED: {
                SceneDef.FIELD_IDS_SCENE_ENH: ['e1'],
                SceneDef.FIELD_IDS_SCENE_DB: {
                    SceneDef.FIELD_LINKED_SOURCED: ['s1', 's2'],
                    SceneDef.FIELD_LINKED_NEIGHBORS: ['n1'],
                },
            }
        }
        linked = SceneDef.scenes_linked_from_data(data)
        assert linked[SceneDef.FIELD_IDS_SCENE_ENH] == ['e1']
        assert linked[SceneDef.FIELD_IDS_SCENE_DB] == {
            SceneDef.FIELD_LINKED_NEIGHBORS: ['n1'],
            SceneDef.FIELD_LINKED_SOURCED: ['s1', 's2'],
        }
