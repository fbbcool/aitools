"""H3 clip-chain helpers (board task 172): link walk, clip resolution, join, refdef verbs."""

import subprocess
from pathlib import Path

import numpy as np
import pytest

from ait.tools import videos
from aidb.app.tab_refdef import (
    CONTINUE_VERBS,
    continue_problems,
    join_args,
    refdef_payload,
)


def _slots(*urls):
    s = [{'url': u, 'id': None, 'role': ''} for u in urls]
    return s + [{'url': None, 'id': None, 'role': ''} for _ in range(6 - len(s))]


# -- refdef verbs ------------------------------------------------------- #
def test_continue_verbs_validate_slots():
    assert continue_problems(_slots('/a/x.mkv', '/a/p.png', '/a/v.wav'), 'post-vid') == []
    assert continue_problems(_slots('/a/p.png'), 'pre-vid') == [
        'slot 1 needs the anchor clip (video)'
    ]
    assert continue_problems(_slots('/a/x.mkv', '/a/y.mkv'), 'post-vid') == [
        'slot 2 is a video (new refs: images / audio)'
    ]
    assert continue_problems(_slots('/a/p.png'), 'ref') == []  # other verbs unaffected


def test_continue_payload_carries_the_link():
    for verb, d in CONTINUE_VERBS.items():
        p = refdef_payload(_slots('/a/x.mkv', '/a/p.png'), verb, 'hint', 'beat')
        assert p['verb'] == verb
        assert p['continue'] == {'dir': d, 'url': '/a/x.mkv', 'pin': videos.CHAIN_PIN}
        assert p['refs'][0]['media'] == 'video'
    assert 'continue' not in refdef_payload(_slots('/a/p.png'), 'ref', 'hint', '')


def test_join_args():
    assert join_args(_slots('/a/last.mkv')) == ('/a/last.mkv', None)
    assert join_args(_slots('/a/last.mkv', '/a/first.mkv')) == ('/a/last.mkv', '/a/first.mkv')
    with pytest.raises(ValueError):
        join_args(_slots('/a/p.png'))
    with pytest.raises(ValueError):
        join_args(_slots('/a/last.mkv', '/a/p.png'))


# -- link resolution / walk --------------------------------------------- #
def test_resolve_clip_by_temp_id(tmp_path):
    moved = tmp_path / 'chain2_post_jrfjs.mkv'
    moved.write_bytes(b'x')
    gone = '/nowhere/comfy3/temp/fbbcool_temp_jrfjs_00001_.mkv'
    assert videos.resolve_clip(gone, (tmp_path,)) == moved
    exact = tmp_path / 'fbbcool_temp_jrfjs_00001_.mkv'
    exact.write_bytes(b'x')
    assert videos.resolve_clip(gone, (tmp_path,)) == exact  # exact name wins
    with pytest.raises(FileNotFoundError):
        videos.resolve_clip('/nowhere/fbbcool_temp_zzzzz_00001_.mkv', (tmp_path,))


def test_anchor_master_maps_merge_to_master(tmp_path, monkeypatch):
    master = tmp_path / 'fbbcool_temp_tgbxm_00001_.mkv'
    merge = tmp_path / 'vid_merge_tgbxm_okhiy.mp4'
    other = tmp_path / 'vid_merge_8babdf8a_9640d6e7.mp4'
    for f in (master, merge, other):
        f.write_bytes(b'x')
    monkeypatch.setattr(videos, 'has_ref_payload', lambda p: Path(p) == master)
    assert videos.anchor_master(master, (tmp_path,)) == master  # payload: itself
    assert videos.anchor_master(merge, (tmp_path,)) == master  # merge -> master by id
    merge.unlink()  # a deleted merge still maps by its name
    assert videos.anchor_master(merge, (tmp_path,)) == master
    assert videos.anchor_master(other, (tmp_path,)) is None  # no master -> refuse


def test_rendered_ref_entry_matches_generation_prompt():
    md = {
        'enhancer': {'prompts_ref': {'current': 0, 'prompt_data': [
            {'prompt': 'a'}, {'prompt': 'b', 'continue': {'dir': 'post'}}]}},
        'generation': {'prompt': 'b'},
    }  # fmt: skip
    assert videos._rendered_ref_entry(md)['prompt'] == 'b'
    md['generation'] = {}
    assert videos._rendered_ref_entry(md)['prompt'] == 'a'


def test_chain_clips_walk(tmp_path, monkeypatch):
    names = ['pre2', 'pre1', 'root', 'post1', 'post2']
    files = {n: tmp_path / f'fbbcool_temp_{n[:3]}{n[-1]}0_00001_.mkv' for n in names}
    for f in files.values():
        f.write_bytes(b'x')
    links = {
        files['post2']: {'dir': 'post', 'url': str(files['post1']), 'pin': 22},
        files['post1']: {'dir': 'post', 'url': str(files['root']), 'pin': 21},
        files['pre1']: {'dir': 'pre', 'url': str(files['root']), 'pin': 20},
        files['pre2']: {'dir': 'pre', 'url': str(files['pre1']), 'pin': 19},
    }
    monkeypatch.setattr(videos, 'chain_link', lambda p: links.get(Path(p)))
    clips, root, pins = videos.chain_clips(files['post2'], files['pre2'], (tmp_path,))
    assert clips == [files[n] for n in names]
    assert root == 2
    assert pins == [19, 20, 21, 22]
    # root alone; wrong direction fails loudly
    assert videos.chain_clips(files['root'])[0] == [files['root']]
    with pytest.raises(ValueError):
        videos.chain_clips(files['pre1'])


# -- join on synthetic clips -------------------------------------------- #
def _clip(path: Path, base: int, n: int = 30, w: int = 64, h: int = 48) -> None:
    """n frames of a moving gradient at brightness `base`, 24 fps + a 440 Hz tone."""
    frames = []
    for i in range(n):
        x = (np.arange(w)[None, :, None] + i) % 64
        frames.append(np.clip(base + x + np.zeros((h, w, 3)), 0, 255).astype(np.uint8))
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}',
         '-r', '24', '-i', '-', '-f', 'lavfi', '-i', 'sine=f=440:r=48000',
         '-map', '0:v', '-map', '1:a', '-shortest', '-c:v', 'libx264', '-crf', '0',
         '-pix_fmt', 'yuv444p', '-c:a', 'pcm_s16le', str(path)],
        input=np.stack(frames).tobytes(), check=True,
    )  # fmt: skip


def test_join_clips_lengths_and_root_untouched(tmp_path):
    a, b, c = tmp_path / 'a.mkv', tmp_path / 'b.mkv', tmp_path / 'c.mkv'
    _clip(a, 60)
    _clip(b, 80)
    _clip(c, 100)
    out = tmp_path / 'out.mkv'
    rep = videos.join_clips([a, b, c], root=1, out=out, pin=6, ramp=8, verbose=0)
    # same total length for every cut offset: n_a - pin + n_b - pin + n_c
    assert rep['frames'] == 30 * 3 - 2 * 6
    assert [s['left'] for s in rep['seams']] == ['pre1', 'root']
    assert {c['clip'] for c in rep['corrections']} == {'pre1', 'post1'}
    assert out.is_file()
    info = videos._probe_av(out)
    assert (info['w'], info['h'], info['sr']) == (64, 48, 48000)
