"""Tests for aidb.avatar (board FEATURE t218): CRUD on the ``avatars`` collection,
media copy / remove / role / reorder, rename moves the dir, to_refdef.

Needs the reachable test MongoDB (conf/aidb/dbc_scenes_test.yaml). The media
root is a tmp dir; avatars are named ``t218-test-*`` and removed per test."""

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from aidb.avatar import (
    SCHEMA,
    AvatarError,
    AvatarManager,
    free_name,
    media_kind,
    norm_lora,
    refdef_urls,
    slugify,
    to_refdef,
)
from ait.tools import role as ait_role

PREFIX = 't218-test-'
A = PREFIX + 'alice'
B = PREFIX + 'bob'


def _png(path: Path, color=(10, 20, 30)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (8, 8), color=color).save(path)
    return path


def _jpg(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (8, 8)).save(path, format='JPEG')
    return path


def _mp4(path: Path) -> Path | None:
    if shutil.which('ffmpeg') is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=16x16:d=0.2',
         '-pix_fmt', 'yuv420p', str(path)],
        check=True,
    )  # fmt: skip
    return path


@pytest.fixture
def am(tmp_path):
    am = AvatarManager(config='test', root=tmp_path / 'avatars', verbose=0)
    yield am
    am._col.delete_many({'name': {'$regex': f'^{PREFIX}'}})


@pytest.fixture
def src(tmp_path):
    return tmp_path / 'src'


class TestPure:
    def test_media_kind(self):
        assert media_kind('/x/a.PNG') == 'image'
        assert media_kind('/x/a.mp4') == 'video'
        assert media_kind('/x/a.wav') == 'audio'
        assert media_kind('/x/a.txt') is None
        assert media_kind(None) is None

    def test_slugify(self):
        assert slugify('  Alice Wonder! ') == 'alice-wonder'
        assert slugify('***') == ''

    def test_free_name(self, tmp_path):
        assert free_name(tmp_path, 'a.png') == tmp_path / 'a.png'
        (tmp_path / 'a.png').touch()
        (tmp_path / 'a_1.png').touch()
        assert free_name(tmp_path, 'a.png') == tmp_path / 'a_2.png'

    def test_norm_lora_fills_t90_fields(self):
        lo = norm_lora({'trigger': 'xa', 'lora_weight': {'solo': 1.0}, 'custom': 1})
        assert lo['family'] is None and lo['negative'] is None
        assert lo['lora_weight'] == {'solo': 1.0, 'stacked': None, 'text': None}
        assert lo['custom'] == 1

    def test_to_refdef(self):
        av = {
            'name': 'x',
            'media': [
                {'mid': 'm1', 'url': '/a.png', 'role': 'head'},
                {'mid': 'm2', 'url': '/b.png', 'role': ''},
            ],
        }
        assert to_refdef(av, ['m2', 'm1']) == [
            {'slot': 1, 'url': '/b.png', 'id': 'm2', 'role': ''},
            {'slot': 2, 'url': '/a.png', 'id': 'm1', 'role': 'head'},
        ]
        assert refdef_urls(av) == ['/a.png', '/b.png']
        with pytest.raises(AvatarError):
            refdef_urls(av, ['nope'])


class TestCrud:
    def test_create_get_list(self, am):
        doc = am.create(A, 'Alice', triggers=['xalice', ' xalice ', ''], tags=['f'])
        assert doc['schema'] == SCHEMA and doc['name'] == A
        assert doc['display_name'] == 'Alice' and doc['triggers'] == ['xalice']
        assert doc['media'] == [] and doc['extra'] == {}
        got = am.get(A)
        assert got is not None and isinstance(got['_id'], str) and got['tags'] == ['f']
        assert A in am.names()
        assert any(d['name'] == A for d in am.list())
        assert am.get(PREFIX + 'missing') is None

    def test_create_rejects_dupe_and_bad_slug(self, am):
        am.create(A)
        with pytest.raises(AvatarError):
            am.create(A)
        with pytest.raises(AvatarError):
            am.create('Bad Name')
        with pytest.raises(AvatarError):
            am.create(PREFIX + 'x', foo=1)

    def test_update(self, am):
        am.create(A)
        doc = am.update(
            A,
            description='d',
            loras=[{'trigger': 'xa', 'family': 'qwen21'}],
            prompt_guides=[{'engine': 'h3', 'text': 't'}],
            extra={'k': [1]},
        )
        assert doc['description'] == 'd' and doc['loras'][0]['family'] == 'qwen21'
        assert doc['prompt_guides'] == [{'engine': 'h3', 'text': 't'}]
        assert am.get(A)['extra'] == {'k': [1]}
        with pytest.raises(AvatarError):
            am.update(A, schema='x')
        with pytest.raises(AvatarError):
            am.update(A, extra=[1])
        with pytest.raises(AvatarError):
            am.update(PREFIX + 'missing', description='x')

    def test_delete_removes_dir(self, am, src):
        am.create(A)
        am.add_media(A, _png(src / 'a.png'))
        assert am.dir_of(A).is_dir()
        assert am.delete(A) is True
        assert am.get(A) is None and not am.dir_of(A).exists()
        assert am.delete(A) is False


class TestMedia:
    def test_add_copies_into_kind_dir(self, am, src):
        am.create(A)
        p = _png(src / 'a.png')
        item = am.add_media(A, p, role='head shot')
        url = Path(item['url'])
        assert url == am.dir_of(A) / 'img' / 'a.png' and url.is_file()
        assert item['src'] == str(p) and p.is_file()
        assert item['kind'] == 'image' and item['role'] == 'head shot' and item['mid']
        assert ait_role.descr(ait_role.role(url)) == 'head shot'
        assert am.get(A)['media'] == [item]

    def test_add_collision_suffix(self, am, src):
        am.create(A)
        u1 = am.add_media(A, _png(src / 'a.png'))['url']
        u2 = am.add_media(A, _png(src / 'x' / 'a.png'))['url']
        assert Path(u1).name == 'a.png' and Path(u2).name == 'a_1.png'

    def test_add_kinds_and_file_url(self, am, src):
        am.create(A)
        aud = src / 'v.wav'
        aud.parent.mkdir(parents=True, exist_ok=True)
        aud.write_bytes(b'RIFF0000WAVE')
        item = am.add_media(A, f'file://{aud}', role='voice')
        assert item['kind'] == 'audio' and Path(item['url']).parent.name == 'aud'
        jpg = am.add_media(A, _jpg(src / 'j.jpg'), role='body')  # no carrier: DB role only
        assert jpg['role'] == 'body' and ait_role.role(jpg['url']) is None

    def test_add_video_role(self, am, src):
        p = _mp4(src / 'c.mp4')
        if p is None:
            pytest.skip('ffmpeg missing')
        am.create(A)
        item = am.add_media(A, p, role='walk cycle')
        assert Path(item['url']).parent.name == 'vid'
        assert ait_role.descr(ait_role.role(item['url'])) == 'walk cycle'

    def test_add_rejects(self, am, src):
        am.create(A)
        with pytest.raises(AvatarError):
            am.add_media(A, src / 'missing.png')
        txt = src / 'a.txt'
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text('x')
        with pytest.raises(AvatarError):
            am.add_media(A, txt)
        with pytest.raises(AvatarError):
            am.add_media(A, 'https://example.com/a.png')
        with pytest.raises(AvatarError):
            am.add_media(PREFIX + 'missing', _png(src / 'a.png'))

    def test_remove_deletes_copy_only(self, am, src):
        am.create(A)
        p = _png(src / 'a.png')
        item = am.add_media(A, p)
        assert am.remove_media(A, item['mid']) is True
        assert not Path(item['url']).exists() and p.is_file()
        assert am.get(A)['media'] == []
        assert am.remove_media(A, item['mid']) is False

    def test_set_role(self, am, src):
        am.create(A)
        item = am.add_media(A, _png(src / 'a.png'), role='old')
        new = am.set_role(A, item['mid'], ' new role ')
        assert new['role'] == 'new role' and am.media(A, item['mid'])['role'] == 'new role'
        assert ait_role.descr(ait_role.role(item['url'])) == 'new role'
        am.set_role(A, item['mid'], '')
        assert ait_role.role(item['url']) is None
        with pytest.raises(AvatarError):
            am.set_role(A, 'nope', 'x')

    def test_reorder(self, am, src):
        am.create(A)
        m = [am.add_media(A, _png(src / f'{i}.png'))['mid'] for i in range(3)]
        doc = am.reorder(A, [m[2], m[0]])
        assert [x['mid'] for x in doc['media']] == [m[2], m[0], m[1]]
        assert [r['id'] for r in to_refdef(am.get(A))] == [m[2], m[0], m[1]]
        with pytest.raises(AvatarError):
            am.reorder(A, ['nope'])


class TestRename:
    def test_rename_moves_dir_and_urls(self, am, src):
        am.create(A, 'Alice')
        item = am.add_media(A, _png(src / 'a.png'), role='head')
        old_dir = am.dir_of(A)
        doc = am.rename(A, B)
        assert doc['name'] == B and am.get(A) is None
        assert not old_dir.exists() and am.dir_of(B).is_dir()
        url = Path(doc['media'][0]['url'])
        assert url == am.dir_of(B) / 'img' / 'a.png' and url.is_file()
        assert doc['media'][0]['mid'] == item['mid'] and doc['display_name'] == 'Alice'

    def test_rename_without_media_dir(self, am):
        am.create(A)
        assert am.rename(A, B)['name'] == B

    def test_rename_rejects(self, am):
        am.create(A)
        am.create(B)
        with pytest.raises(AvatarError):
            am.rename(A, B)
        with pytest.raises(AvatarError):
            am.rename(A, 'Bad Name')
        with pytest.raises(AvatarError):
            am.rename(PREFIX + 'missing', PREFIX + 'x')
