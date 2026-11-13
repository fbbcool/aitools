"""H3 clip-chain helpers (board task 172): link walk, clip resolution, join, refdef verbs."""

import subprocess
from pathlib import Path

import numpy as np
import pytest

from ait.tools import videos
from aidb.app.tab_refdef import (
    CONTINUE_VERBS,
    refdef_payload,
)


def _slots(*urls):
    s = [{'url': u, 'id': None, 'role': ''} for u in urls]
    return s + [{'url': None, 'id': None, 'role': ''} for _ in range(6 - len(s))]


# -- refdef verbs ------------------------------------------------------- #
def test_continue_payload_carries_the_link():
    for verb, d in CONTINUE_VERBS.items():
        p = refdef_payload(_slots('/a/x.mkv', '/a/p.png'), verb, 'hint', 'beat')
        assert p['verb'] == verb
        assert p['continue'] == {'dir': d, 'url': '/a/x.mkv', 'pin': videos.CHAIN_PIN}
        assert p['refs'][0]['media'] == 'video'
    assert 'continue' not in refdef_payload(_slots('/a/p.png'), 'ref', 'hint', '')


# -- link resolution / walk --------------------------------------------- #
def test_resolve_clip_by_temp_id(tmp_path, monkeypatch):
    monkeypatch.setattr(videos, '_has_metadata', lambda p: True)
    moved = tmp_path / 'chain2_post_jrfjs.mkv'
    moved.write_bytes(b'x')
    gone = '/nowhere/comfy3/temp/fbbcool_temp_jrfjs_00001_.mkv'
    assert videos.resolve_clip(gone, (tmp_path,)) == moved
    exact = tmp_path / 'fbbcool_temp_jrfjs_00001_.mkv'
    exact.write_bytes(b'x')
    assert videos.resolve_clip(gone, (tmp_path,)) == exact  # exact name wins
    with pytest.raises(FileNotFoundError):
        videos.resolve_clip('/nowhere/fbbcool_temp_zzzzz_00001_.mkv', (tmp_path,))


def test_resolve_clip_never_picks_merge_outputs(tmp_path, monkeypatch):
    """Board task 184: a renamed master beats newer vid_merge_* / chain_* outputs."""
    import os

    master = tmp_path / '001-fbbcool_temp_tgbxm_00001_.mkv'
    derived = [tmp_path / n for n in ('vid_merge_tgbxm_rjjow.mp4', 'chain_tgbxm_oigin.mkv')]
    for i, f in enumerate([master, *derived]):
        f.write_bytes(b'x')
        os.utime(f, (1000 + i, 1000 + i))  # derived outputs are newer
    monkeypatch.setattr(videos, '_has_metadata', lambda p: True)  # even with metadata
    gone = tmp_path / 'fbbcool_temp_tgbxm_00001_.mkv'
    assert videos.resolve_clip(gone, (tmp_path,)) == master
    copy = tmp_path / 'sub'
    copy.mkdir()
    (copy / 'fbbcool_temp_tgbxm_00001_.mkv').write_bytes(b'x')  # same size = same master
    assert videos.resolve_clip('/nowhere/fbbcool_temp_tgbxm_00001_.mkv', (tmp_path,)) == master
    (tmp_path / 'fbbcool_temp_tgbxm_00002_.mkv').write_bytes(b'xy')  # a distinct master
    with pytest.raises(ValueError, match='ambiguous'):
        videos.resolve_clip('/nowhere/fbbcool_temp_tgbxm_00001_.mkv', (tmp_path,))


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
    renamed = tmp_path / '001-fbbcool_temp_tgbxm_00001_.mkv'
    master.rename(renamed)
    monkeypatch.setattr(videos, 'has_ref_payload', lambda p: Path(p) in (renamed, post))
    post = tmp_path / 'fbbcool_temp_oigin_00001_.mkv'
    post.write_bytes(b'x')
    assert videos.anchor_master(merge, (tmp_path,)) == renamed  # renamed master found
    with pytest.raises(ValueError, match='several masters'):  # merge of anchor + post
        videos.anchor_master(tmp_path / 'vid_merge_tgbxm_oigin.mkv', (tmp_path,))


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


# -- per-seam joins (board task 183) ------------------------------------ #
def test_seam_plan_legacy_and_groups():
    plan, groups = videos._seam_plan(3, 1, 6, None)
    assert [s['dir'] for s in plan] == ['pre', 'post'] and groups == [(0, 2, 1)]
    chain_post = {'kind': 'chain', 'pin': 22, 'dir': 'post'}
    plan, groups = videos._seam_plan(3, 0, 22, [{'kind': 'plain'}, chain_post])
    assert [s['kind'] for s in plan] == ['plain', 'chain'] and groups == [(0, 0, 0), (1, 2, 1)]
    pre = {'kind': 'chain', 'pin': 5, 'dir': 'pre'}
    seams = [chain_post, {'kind': 'plain'}, pre, chain_post]  # R→post | pre→R→post
    assert videos._seam_plan(5, 0, 22, seams)[1] == [(0, 1, 0), (2, 4, 3)]
    assert videos._clip_names([(0, 0, 0), (1, 2, 1)]) == ['g1', 'g2.root', 'g2.post1']
    with pytest.raises(ValueError, match='pre… → root → post'):
        videos._seam_plan(3, 0, 22, [chain_post, pre])
    with pytest.raises(ValueError, match='need 2 seams'):
        videos._seam_plan(3, 0, 22, [chain_post])
    with pytest.raises(ValueError, match='kind must be'):
        videos._seam_plan(2, 0, 22, [{'kind': 'cut'}])


def _audio_seconds(path: Path) -> float:
    out = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return float(out.strip())


def test_join_clips_mixed_plain_and_chain(tmp_path):
    p, r, q = tmp_path / 'p.mkv', tmp_path / 'r.mkv', tmp_path / 'q.mkv'
    _clip(p, 40)
    _clip(r, 80)
    _clip(q, 110)
    out = tmp_path / 'out.mkv'
    seams = [{'kind': 'plain'}, {'kind': 'chain', 'pin': 6, 'dir': 'post'}]
    rep = videos.join_clips([p, r, q], out=out, ramp=8, verbose=0, seams=seams)
    assert rep['frames'] == 29 + 30 + 30 - 6  # plain drops 1, the chain overlaps pin
    assert [s['kind'] for s in rep['seams']] == ['plain', 'chain']
    assert rep['seams'][0]['cut'] == 0 and rep['seams'][0]['frame'] == 29
    assert rep['roots'] == [0, 1] and rep['root'] == 0
    # only the post clip is corrected (toward its own root); g1 + g2.root untouched
    assert [c['clip'] for c in rep['corrections']] == ['g2.post1']
    assert rep['corrections'][0]['offset'][0] < 0  # 110 → toward 80
    assert abs(_audio_seconds(out) - rep['seconds']) < 0.05
    assert '|' in videos.seam_summary(rep) and '→g2.post1' in videos.seam_summary(rep)


def test_join_clips_two_chain_groups_no_cross_correction(tmp_path):
    r1, q1, r2, q2 = (tmp_path / f'{n}.mkv' for n in ('r1', 'q1', 'r2', 'q2'))
    _clip(r1, 40)
    _clip(q1, 90)  # brighter than its root → negative offset
    _clip(r2, 150)
    _clip(q2, 100)  # darker than its root → positive offset (would be negative toward g1)
    post = {'kind': 'chain', 'pin': 6, 'dir': 'post'}
    rep = videos.join_clips(
        [r1, q1, r2, q2], out=tmp_path / 'o.mkv', ramp=8, verbose=0,
        seams=[post, {'kind': 'plain'}, post],
    )  # fmt: skip
    assert rep['frames'] == (30 + 30 - 6) - 1 + (30 + 30 - 6)
    assert rep['roots'] == [0, 2]
    off = {c['clip']: c['offset'][0] for c in rep['corrections']}
    assert set(off) == {'g1.post1', 'g2.post1'}
    assert off['g1.post1'] < 0 < off['g2.post1']


def test_join_clips_legacy_report_has_kind(tmp_path):
    a, b = tmp_path / 'a.mkv', tmp_path / 'b.mkv'
    _clip(a, 60)
    _clip(b, 70)
    rep = videos.join_clips([a, b], out=tmp_path / 'o.mkv', pin=6, ramp=8, verbose=0)
    assert [s['kind'] for s in rep['seams']] == ['chain'] and rep['roots'] == [0]
    assert [s['left'] for s in rep['seams']] == ['root']


def test_join_clips_short_soundtrack_keeps_every_frame(tmp_path):
    a, b, bs = tmp_path / 'a.mkv', tmp_path / 'b.mkv', tmp_path / 'bs.mkv'
    _clip(a, 60)
    _clip(b, 70)
    subprocess.run(  # b with its audio cut to 1.0 s of its 1.25 s video
        ['ffmpeg', '-v', 'error', '-y', '-i', str(b), '-c:v', 'copy', '-af', 'atrim=0:1',
         '-c:a', 'pcm_s16le', str(bs)],
        check=True,
    )  # fmt: skip
    out = tmp_path / 'o.mkv'
    rep = videos.join_clips([a, bs], out=out, pin=6, ramp=8, verbose=0)
    written = sum(1 for _ in videos._iter_frames(out, 64, 48))
    assert written == rep['frames'] == 30 + 30 - 6
