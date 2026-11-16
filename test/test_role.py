"""media role metadata (board FEATURE t215): carrier round-trips + tab / refdef wiring."""

import json
import subprocess
from pathlib import Path

import av
import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from ait.tools import images, videos
from ait.tools import role as R


def _png(path: Path) -> Path:
    info = PngInfo()
    info.add_text('prompt', json.dumps({'1': {'class_type': 'X', 'inputs': {}}}))
    Image.new('RGB', (16, 12), 'red').save(path, pnginfo=info)
    return path


def _vid(path: Path) -> Path:
    """Main stream + an anchor stream + a prompt tag (mkv) — like a master."""
    cmd = ['ffmpeg', '-v', 'error', '-y',
           '-f', 'lavfi', '-i', 'testsrc=d=0.5:s=32x32',
           '-f', 'lavfi', '-i', 'testsrc=d=0.04:s=32x32',
           '-map', '0', '-map', '1', '-c:v:0', 'mpeg4', '-c:v:1', 'ffv1',
           '-metadata:s:v:1', f'title={videos.ANCHOR_TITLE_PREFIX}first',
           '-metadata', 'prompt={"1": {}}']  # fmt: skip
    if path.suffix == '.mp4':
        cmd += ['-movflags', 'use_metadata_tags']
    subprocess.run([*cmd, str(path)], check=True, capture_output=True)
    return path


def _packets(path: Path) -> list[tuple[int, bytes]]:
    with av.open(str(path)) as c:
        return [(p.stream.index, bytes(p)) for p in c.demux() if p.size]


def _titles(path: Path) -> list[str]:
    with av.open(str(path)) as c:
        return [str((s.metadata or {}).get('title', '')) for s in c.streams]


def test_png_roundtrip_keeps_pixels_and_chunks(tmp_path):
    p = _png(tmp_path / 'a.png')
    before = Image.open(p).tobytes()
    assert R.role(p) is None and images.metadata(p)['role'] is None

    stored = R.role_set(p, {'descr': 'face ref ü'})
    assert stored == {'schema': R.ROLE_SCHEMA, 'descr': 'face ref ü'}
    assert R.role(p) == stored
    assert images.metadata(p)['role'] == stored
    im = Image.open(p)
    assert im.tobytes() == before and 'prompt' in im.info

    # edit keeps unknown keys, remove drops the chunk
    R.role_set(p, {**stored, 'extra': 1})
    assert R.role_set(p, {'descr': 'body ref'})['extra'] == 1
    assert R.role_set(p, None) is None
    assert R.role(p) is None and R.ROLE_CHUNK not in Image.open(p).info
    assert 'prompt' in Image.open(p).info


@pytest.mark.parametrize('suffix', ['.mkv', '.mp4'])
def test_video_roundtrip_is_lossless(tmp_path, suffix):
    v = _vid(tmp_path / f'a{suffix}')
    pk, titles = _packets(v), _titles(v)

    assert R.role_set(v, {'descr': 'clip intro'})['descr'] == 'clip intro'
    assert videos.metadata(v)['role']['descr'] == 'clip intro'
    assert videos.metadata(v)['comfy']['prompt_graph'] == {'1': {}}
    R.role_set(v, {'descr': 'clip outro'})
    assert R.descr(R.role(v)) == 'clip outro'
    assert _packets(v) == pk and _titles(v) == titles

    R.role_set(v, {'descr': '  '})  # empty descr removes
    assert R.role(v) is None
    assert videos.metadata(v)['comfy']['prompt_graph'] == {'1': {}}
    assert _packets(v) == pk


def test_unsupported_and_missing(tmp_path):
    jpg = tmp_path / 'a.jpg'
    Image.new('RGB', (8, 8)).save(jpg)
    assert R.role(jpg) is None
    with pytest.raises(R.RoleUnsupported):
        R.role_set(jpg, {'descr': 'x'})
    with pytest.raises(FileNotFoundError):
        R.role_set(tmp_path / 'gone.png', {'descr': 'x'})
    # removing a role that is not there leaves the file untouched
    p = _png(tmp_path / 'b.png')
    raw = p.read_bytes()
    assert R.role_set(p, None) is None and p.read_bytes() == raw


def test_metadata_tab_role_row(tmp_path):
    from aidb.app.tab_metadata import MetadataTab, metaless_copy

    p = _png(tmp_path / 'a.png')
    tab = MetadataTab()
    assert tab._load(str(p), None, [])[-1] == ''
    page, text = tab._on_role(str(p), 'hand ref')
    assert text == 'hand ref' and 'ait_role' not in page  # not repeated under Other
    assert tab._load(str(p), None, [])[-1] == 'hand ref'
    assert R.role(metaless_copy(p)) is None  # Q3: *-nometa drops the role
    assert tab._on_role(str(p), None, remove=True)[1] == ''
    assert R.role(p) is None


def test_refdef_pull_role(tmp_path):
    import gradio as gr

    from aidb.app.tab_refdef import RefdefTab

    p = _png(tmp_path / 'a.png')
    bare = _png(tmp_path / 'b.png')
    R.role_set(p, {'descr': 'the face'})
    enh = {'kind': 'iteration'}
    keep = gr.update()
    assert RefdefTab._pulled_role(None, str(p)) == 'the face'
    assert RefdefTab._pulled_role(None, str(p), keep=True) == 'the face'
    assert RefdefTab._pulled_role(None, str(bare)) == ''  # tab pull: blank as before
    assert RefdefTab._pulled_role(None, str(bare), keep=True) == keep  # slot pull: untouched
    assert RefdefTab._pulled_role(enh, str(p)) == keep  # Q2: enhancer mode keeps payload role
    assert RefdefTab._pulled_role(None, 'https://example.com/x.png') == ''
