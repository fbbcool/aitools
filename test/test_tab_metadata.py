"""metadata tab (board FEATURE t214): view builder over synthetic v1 files."""

import json
import re
import subprocess
from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from aidb.app.tab_metadata import (
    MetadataView,
    collect_media,
    has_content,
    looks_like_media_ref,
    media_kind,
    metaless_copy,
    path_from_clipspace,
    read_metadata,
)


def _sections(page: str) -> list[str]:
    return [
        t.strip() for t in re.findall(r'<details class="md-sec"(?: open)?><summary>([^<]*)', page)
    ]


@pytest.fixture
def media(tmp_path: Path) -> dict[str, Path]:
    ref = tmp_path / 'ref.png'
    Image.new('RGB', (40, 30), 'red').save(ref)
    aud = tmp_path / 'voice.wav'
    aud.write_bytes(b'RIFF0000WAVE')
    missing = tmp_path / 'gone.png'
    entry = {
        'prompt': 'a red square',
        'concepts': ['holding'],
        'refs': [
            {'kind': 'image', 'slot': 1, 'url': str(ref), 'desc': 'woman'},
            {'kind': 'audio', 'slot': 2, 'url': str(aud), 'desc': 'voice'},
            {'kind': 'image', 'slot': 3, 'url': str(missing), 'desc': 'lost'},
            {'kind': 'image', 'slot': 4, 'url': 'https://example.com/x.jpg', 'desc': 'web'},
        ],
    }
    enh = {
        'schema_id': '1xlasm_enhancer.iteration.v6.15',
        'scene_id': 'abc',
        'prompts': {'type': 'single', 'current': 0, 'prompt_data': [entry]},
    }
    graph = {
        '1': {'class_type': 'UNETLoader', 'inputs': {'unet_name': 'x/model.safetensors'}},
        '2': {'class_type': 'LoadImage', 'inputs': {'image': str(ref)}},
    }
    info = PngInfo()
    info.add_text('prompt', json.dumps(graph))
    info.add_text('parent_metadata', json.dumps({'schema_id': 'p', 'enhancer': enh}))
    info.add_text('my_extra', 'hello extra')
    out = tmp_path / 'render.png'
    Image.new('RGB', (64, 32), 'blue').save(out, pnginfo=info)
    plain = tmp_path / 'plain.png'
    Image.new('RGB', (8, 8)).save(plain)
    return {'render': out, 'plain': plain, 'ref': ref, 'aud': aud, 'missing': missing}


def test_clipspace_paths_only(media):
    assert path_from_clipspace(f'junk\n"{media["render"]}"\n') == str(media['render'])
    assert path_from_clipspace(f'file://{media["ref"]}') == str(media['ref'])
    assert path_from_clipspace('6afaae2bb4f8fcc3c8bd1bcc') is None  # ids are not paths
    assert path_from_clipspace(str(media['missing'])) is None
    assert path_from_clipspace('') is None


def test_media_kind(media):
    assert media_kind(str(media['ref'])) == 'image'
    assert media_kind(str(media['aud'])) == 'audio'
    assert media_kind(str(media['missing'])) == 'missing'
    assert media_kind('https://example.com/x.jpg') == 'remote'
    assert looks_like_media_ref('/a/b.mkv') and not looks_like_media_ref('b.mkv')
    assert not looks_like_media_ref('/a/model.safetensors')


def test_collect_media_paths():
    found = collect_media({'a': {'url': '/x/1.png'}, 'b': ['/x/1.png', '/x/2.mp4', 'txt']})
    assert found == {'/x/1.png': ['a.url', 'b[0]'], '/x/2.mp4': ['b[1]']}


def test_render_sections_and_cards(media):
    page = MetadataView().render(str(media['render']))
    secs = _sections(page)
    for s in ('Media', 'Linked media', 'Generation', 'Enhancer', 'Parent', 'ComfyUI', 'Other'):
        assert s in secs, s
    # placeholders: audio tile, missing tile, remote tile; image thumb
    assert '🔊' in page and '⛔' in page and '🌐' in page
    assert 'data:image/jpeg;base64,' in page
    # local media are loadable cards, missing / remote are not
    assert f'data-url="{media["ref"]}"' in page and f'data-url="{media["aud"]}"' in page
    assert f'data-url="{media["missing"]}"' not in page
    assert 'data-url="https://example.com/x.jpg"' not in page
    # comfy models + media inputs, unknown chunk in Other
    assert 'x/model.safetensors' in page and 'node 2 · image' in page
    assert 'hello extra' in page


def test_render_without_metadata(media):
    view = MetadataView()
    page = view.render(str(media['plain']))
    assert _sections(page) == ['Media']
    assert 'no embedded metadata' in page and not view.has_md


def test_render_empty_and_missing(media):
    assert 'pull' in MetadataView().render(None)
    assert '⛔' in MetadataView().render(str(media['missing']))


def test_metaless_copy_image(media, tmp_path):
    out = metaless_copy(media['render'], tmp_path / 'archive')
    assert out == tmp_path / 'archive' / 'render-nometa.png'
    with Image.open(out) as im:
        assert im.size == (64, 32) and not im.info
    assert not has_content(read_metadata(str(out)))


def test_metaless_copy_next_to_original(media):
    out = metaless_copy(media['ref'])
    assert out == media['ref'].parent / 'ref-nometa.png' and out.is_file()


def test_metaless_copy_video(tmp_path):
    src = tmp_path / 'clip.mkv'
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=32x32:d=0.2',
         '-metadata', 'prompt={"1": {}}', '-metadata', 'title=secret', str(src)],
        check=True,
    )  # fmt: skip
    out = metaless_copy(src, tmp_path / 'archive')
    tags = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format_tags', '-of', 'json', str(out)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    assert 'secret' not in tags and 'prompt' not in tags.lower()
