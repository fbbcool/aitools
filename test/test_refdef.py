import json

from aidb.app.tab_refdef import (
    EDITED_BY,
    SCHEMA_REFDEF,
    available_views,
    default_view,
    parse_payload,
    patch_iteration,
    refdef_payload,
    update_payload,
    with_view,
)


def _iteration(**extra) -> dict:
    return {
        'schema_id': '1xlasm_enhancer.iteration.v6.5',
        'scene_id': 'abc',
        'url': '/x/0rig___a.png',
        'rev': 2,
        'prompts': {
            'type': 'story',
            'current': 1,
            'prompt_data': [
                {'prompt': 'p0', 'concepts': ['c0'], 'triggers': []},
                {'prompt': 'p1', 'concepts': ['c1'], 'triggers': ['xlasm']},
                {'prompt': 'p2', 'concepts': [], 'triggers': []},
            ],
        },
        'unknown_future_field': {'keep': True},
        **extra,
    }


def _inp(from_rev=2, refs=None) -> dict:
    return {
        'type': 'single',
        'current': 0,
        'prompt_data': [
            {
                'engine': 'qwen21',
                'prompt_qwen21': 'Replace the face with the face in image 2',
                'prompt': '',
                'src': {'url': '/c/src.png', 'w': 1056, 'h': 1584, 'desc': 'main'},
                'refs': refs
                if refs is not None
                else [{'url': '/c/face.png', 'w': 832, 'h': 1248, 'desc': 'new face'}],
                'mask': None,
                'mode': 'nomask',
                'from_rev': from_rev,
                'ts': '2026-10-26T09:10:00',
            }
        ],
    }


def _vid(from_rev=1) -> dict:
    return {
        'type': 'single',
        'current': 0,
        'prompt_data': [{'prompt': 'vid p', 'triggers': [], 'from_rev': from_rev, 'ts': 'x'}],
        'refs': {'first': {'url': '/f.png', 'at': 0.0, 'desc': 'dress'}, 'last': None},
    }


# -- parse / views ---------------------------------------------------------- #
def test_parse_main_view_uses_current_entry():
    st = parse_payload(json.dumps(_iteration()))
    assert st is not None and st['kind'] == 'iteration'
    assert st['view'] == 'main' and st['views'] == ['main']
    assert st['idx'] == 1 and st['text'] == 'p1'
    assert st['slots'][0]['url'] == '/x/0rig___a.png'
    assert st['slots'][1]['url'] is None and st['slots'][2]['url'] is None


def test_inp_view_is_default_when_fresh():
    st = parse_payload(json.dumps(_iteration(prompts_inp=_inp(), url_desc='main img')))
    assert st is not None
    assert st['views'] == ['main', 'inp'] and st['view'] == 'inp'
    assert [s['url'] for s in st['slots'][:3]] == ['/c/src.png', '/c/face.png', None]
    assert [s['role'] for s in st['slots'][:3]] == ['main', 'new face', '']
    assert st['text'] == 'Replace the face with the face in image 2'


def test_stale_section_falls_back_to_main():
    p = _iteration(prompts_inp=_inp(from_rev=1))  # a later steer moved rev on
    assert default_view(p) == 'main'
    assert available_views(p) == ['main', 'inp']


def test_with_view_switches_slots_and_text():
    st = parse_payload(json.dumps(_iteration(prompts_inp=_inp(), prompts_vid=_vid())))
    assert st is not None and st['view'] == 'inp'
    vid = with_view(st, 'vid')
    assert [s['url'] for s in vid['slots'][:3]] == ['/f.png', None, None]
    assert vid['slots'][0]['role'] == 'dress' and vid['text'] == 'vid p'
    main = with_view(st, 'main')
    assert main['slots'][0]['role'] == 'main img' and main['text'] == 'p1'


def test_parse_rejects_non_enhancer():
    assert parse_payload('free text') is None
    assert parse_payload(json.dumps({'schema_id': 'other'})) is None
    assert parse_payload(json.dumps([1, 2])) is None


def test_refdef_roundtrip():
    slots = [
        {'url': '/a.png', 'id': 'i1', 'role': ' identity '},
        {'url': None, 'id': None, 'role': ''},
        {'url': 'https://h/c.png', 'id': None, 'role': 'light'},
    ]
    payload = refdef_payload(slots, 'inp-mask', 'prompt', 'txt', 'scn')
    assert payload['schema_id'] == SCHEMA_REFDEF
    assert payload['verb'] == 'inp-mask'
    assert [r['slot'] for r in payload['refs']] == [1, 2, 3]
    assert payload['refs'][0]['role'] == 'identity'
    assert payload['origin'] == {'scene_id': 'scn'}
    st = parse_payload(json.dumps(payload))
    assert st is not None and st['kind'] == 'refdef'
    assert st['prompt_kind'] == 'prompt' and st['text'] == 'txt'
    assert st['verb'] == 'inp-mask'
    assert st['slots'][2]['url'] == 'https://h/c.png'


def test_refdef_sketch_without_images():
    empty = [{'url': None, 'id': None, 'role': ''}] * 3
    payload = refdef_payload(empty, 'sketch', 'hint', 'xlgts, beach, low angle')
    assert payload['verb'] == 'sketch'
    assert all(r['url'] is None and r['id'] is None for r in payload['refs'])
    st = parse_payload(json.dumps(payload))
    assert st is not None and st['verb'] == 'sketch'
    assert st['text'] == 'xlgts, beach, low angle'


# -- patch ------------------------------------------------------------------ #
def test_patch_unchanged_is_verbatim():
    p = _iteration(prompts_inp=_inp())
    out, changed, skipped = patch_iteration(p, 'inp', ['/c/src.png', '/c/face.png', None])
    assert changed == [] and skipped == [] and out == p


def test_patch_main_url_keeps_everything_else():
    p = _iteration()
    out, changed, _ = patch_iteration(p, 'main', ['/y.png', None, None])
    assert changed == ['url'] and out['url'] == '/y.png'
    assert out['prompts'] == p['prompts']
    assert out['edited_by'] == EDITED_BY
    assert out['unknown_future_field'] == {'keep': True}
    assert out['schema_id'] == p['schema_id']
    assert p['url'] == '/x/0rig___a.png' and 'edited_by' not in p  # input untouched


def test_patch_inp_replace_ref_keeps_desc_and_prompt():
    p = _iteration(prompts_inp=_inp())
    out, changed, skipped = patch_iteration(p, 'inp', ['/c/src.png', '/c/other.png', None])
    assert changed == ['prompts_inp.refs[0]'] and skipped == []
    entry = out['prompts_inp']['prompt_data'][0]
    assert entry['refs'][0]['url'] == '/c/other.png' and entry['refs'][0]['desc'] == 'new face'
    assert entry['prompt_qwen21'] == p['prompts_inp']['prompt_data'][0]['prompt_qwen21']


def test_patch_inp_structural_changes_are_skipped():
    p = _iteration(prompts_inp=_inp())
    # remove ref 1 and add a ref 2 -> both would renumber the instruction
    out, changed, skipped = patch_iteration(p, 'inp', ['/c/src.png', None, '/c/new.png'])
    assert changed == [] and len(skipped) == 2
    assert out == p
    # clearing the src is structural too
    _, changed, skipped = patch_iteration(p, 'inp', [None, '/c/face.png', None])
    assert changed == [] and len(skipped) == 1


def test_patch_vid_refs():
    p = _iteration(prompts_vid=_vid())
    out, changed, _ = patch_iteration(p, 'vid', ['/g.png', '/l.png', None])
    assert changed == ['prompts_vid.refs.first', 'prompts_vid.refs.last']
    assert out['prompts_vid']['refs']['first'] == {'url': '/g.png', 'at': 0.0, 'desc': 'dress'}
    assert out['prompts_vid']['refs']['last'] == {'url': '/l.png'}


def test_patch_main_extra_slots_are_skipped():
    out, changed, skipped = patch_iteration(
        _iteration(), 'main', ['/x/0rig___a.png', '/g.png', None]
    )
    assert changed == [] and len(skipped) == 1
    assert 'edited_by' not in out


# -- tab helpers ------------------------------------------------------------ #
def test_place_images_adds_to_free_slots_only():
    from aidb.app.tab_refdef import RefdefTab

    assert RefdefTab.place_images(1, ['a', '', '']) == [1]
    assert RefdefTab.place_images(2, ['a', '', '']) == [1, 2]
    assert RefdefTab.place_images(1, ['', 'b', '']) == [0]
    # second pull adds; overflow is dropped, never overwrites
    assert RefdefTab.place_images(2, ['a', 'b', '']) == [2]
    assert RefdefTab.place_images(1, ['a', 'b', 'c']) == []
    assert RefdefTab.place_images(5, ['', '', '']) == [0, 1, 2]


def _fake_herdr(status, sent, fail_get=False):
    def fake(*args):
        if args[:2] == ('agent', 'get'):
            if fail_get:
                raise RuntimeError('herdr: no session')
            return {'result': {'agent': {'agent_status': status}}}
        sent.append(args)
        return {}

    return fake


def test_trigger_enhancer_sends_only_when_idle(monkeypatch):
    from aidb.app import tab_refdef

    for status, expect_sent in (
        ('idle', True),
        ('done', True),
        ('working', False),
        ('blocked', False),
        (None, False),
    ):
        sent: list = []
        monkeypatch.setattr(tab_refdef, '_herdr', _fake_herdr(status, sent))
        note = tab_refdef.trigger_enhancer()
        assert bool(sent) == expect_sent, (status, note)
        if expect_sent:
            assert sent == [('agent', 'prompt', 'enhancer', '/refdef')]


def test_trigger_enhancer_unreachable(monkeypatch):
    from aidb.app import tab_refdef

    sent: list = []
    monkeypatch.setattr(tab_refdef, '_herdr', _fake_herdr('idle', sent, fail_get=True))
    assert 'not reachable' in tab_refdef.trigger_enhancer() and sent == []


def test_patches_across_views_accumulate_in_working_copy():
    p = _iteration(prompts_inp=_inp(), prompts_vid=_vid())
    work, ch1, _ = patch_iteration(p, 'main', ['/main2.png', None, None])
    work, ch2, _ = patch_iteration(work, 'inp', ['/c/src.png', '/c/face2.png', None])
    assert ch1 == ['url'] and ch2 == ['prompts_inp.refs[0]']
    assert work['url'] == '/main2.png'
    assert work['prompts_inp']['prompt_data'][0]['refs'][0]['url'] == '/c/face2.png'
    assert work['prompts_vid'] == p['prompts_vid'] and work['edited_by'] == EDITED_BY


# -- update (clipspace refs ← slots) ---------------------------------------- #
def _slot(url=None, id_=None):
    return {'url': url, 'id': id_, 'role': 'ignored'}


def test_update_iteration_main_keeps_empty_slots():
    p = _iteration()
    res = update_payload(json.dumps(p), [_slot(), _slot(), _slot()])
    out, view, changed, _ = res
    assert view == 'main' and changed == [] and out['url'] == p['url']
    out, _, changed, _ = update_payload(json.dumps(p), [_slot('/n.png'), _slot(), _slot()])
    assert changed == ['url'] and out['url'] == '/n.png'
    assert out['edited_by'] == EDITED_BY
    assert out['unknown_future_field'] == {'keep': True}


def test_update_iteration_verb_owns_its_view():
    p = _iteration(prompts_inp=_inp())
    text = json.dumps(p)
    assert default_view(p) == 'inp'
    slots = [_slot(), _slot('/c/new.png'), _slot()]
    out, view, changed, _ = update_payload(text, slots, verb='inp-nomask')
    assert view == 'inp' and changed == ['prompts_inp.refs[0]']
    # a verb owning no view never touches inp/ref, even when inp is the default
    out, view, changed, _ = update_payload(text, [_slot('/m.png'), _slot(), _slot()], 'inp')
    assert view == 'main' and changed == ['url']
    assert out['prompts_inp'] == p['prompts_inp']
    # verb whose section is absent → nothing changes
    out, view, changed, skipped = update_payload(text, slots, verb='ref')
    assert view == 'ref' and changed == [] and skipped and out == p


def test_update_refdef_replaces_url_and_id_only():
    slots = [_slot('/a.png', 'i1'), _slot(), _slot()]
    instr = refdef_payload(
        [{'url': '/a.png', 'id': 'i1', 'role': 'main img'}, _slot(), _slot('/c.png')],
        'enh',
        'hint',
        'txt',
    )
    out, view, changed, _ = update_payload(
        json.dumps(instr), [_slot('/b.png', 'i2'), _slot('/x.png'), _slot()]
    )
    assert view == '' and changed == ['refs[slot 1]', 'refs[slot 2]']
    assert out['refs'][0] == {
        'slot': 1,
        'url': '/b.png',
        'id': 'i2',
        'role': 'main img',
        'media': 'image',
    }
    assert out['refs'][1]['url'] == '/x.png' and out['refs'][1]['id'] is None
    assert out['refs'][2]['url'] == '/c.png'  # empty slot keeps the clipspace ref
    assert out['verb'] == 'enh' and out['text'] == 'txt'
    _, _, changed, _ = update_payload(json.dumps(instr), slots)
    assert changed == []


def test_update_rejects_foreign_clipspace():
    assert update_payload('free text', [_slot('/a.png')] * 3) is None


def test_update_picks_view_that_takes_the_filled_slots():
    # default view is main (inp entry is stale: from_rev != rev), slot 2 filled
    p = _iteration(prompts_inp=_inp(from_rev=0))
    assert default_view(p) == 'main'
    slots = [_slot('/c/src.png'), _slot('/c/new.png'), _slot()]
    out, view, changed, skipped = update_payload(json.dumps(p), slots, verb='inp-mask')
    assert view == 'inp' and changed == ['prompts_inp.refs[0]'] and skipped == []
    # tab view main, slot 2 filled → still inp (the verb decides)
    _, view, _, _ = update_payload(json.dumps(p), slots, 'main', 'inp-mask')
    assert view == 'inp'


def test_update_reports_skips_when_no_view_fits():
    p = _iteration()  # main only
    out, view, changed, skipped = update_payload(
        json.dumps(p), [_slot(), _slot('/c/new.png'), _slot()]
    )
    assert view == 'main' and changed == [] and skipped


# -- ref verb / prompts_ref view (board task 159) ---------------------------- #
def test_refdef_ref_verb():
    slots = [
        {'url': '/a.png', 'id': 'i1', 'role': 'woman'},
        {'url': '/b.png', 'id': None, 'role': 'beach'},
        {'url': None, 'id': None, 'role': ''},
    ]
    payload = refdef_payload(slots, 'ref', 'hint', 'walks into the sea')
    assert payload['schema_id'] == SCHEMA_REFDEF and payload['verb'] == 'ref'
    st = parse_payload(json.dumps(payload))
    assert st is not None and st['verb'] == 'ref'
    assert [s['url'] for s in st['slots'][:3]] == ['/a.png', '/b.png', None]


def _ref(from_rev=2) -> dict:
    return {
        'current': 0,
        'prompt_data': [
            {
                'prompt': '<Picture 1> walks along <Picture 2>',
                'from_rev': from_rev,
                'ts': '2026-11-02T18:00:00Z',
                'refs': [
                    {'url': '/r/p1.png', 'w': 832, 'h': 1248, 'desc': 'woman'},
                    {'url': '/r/p2.png', 'desc': 'beach'},
                ],
            }
        ],
    }


def test_ref_view_slots_and_patch():
    p = _iteration(schema_id='1xlasm_enhancer.iteration.v6.6', prompts_ref=_ref())
    assert 'ref' in available_views(p) and default_view(p) == 'ref'
    st = parse_payload(json.dumps(p))
    assert st is not None and st['view'] == 'ref'
    assert [s['url'] for s in st['slots'][:3]] == ['/r/p1.png', '/r/p2.png', None]
    assert [s['role'] for s in st['slots']][:2] == ['woman', 'beach']
    assert st['text'] == '<Picture 1> walks along <Picture 2>'
    # replacing a picture is allowed; adding picture 3 would renumber -> skipped
    out, changed, skipped = patch_iteration(p, 'ref', ['/r/p1.png', '/n/p2.png', '/n/p3.png'])
    assert changed == ['prompts_ref.refs[1]'] and len(skipped) == 1
    refs = out['prompts_ref']['prompt_data'][0]['refs']
    assert refs[1]['url'] == '/n/p2.png' and len(refs) == 2
    assert out['edited_by'] == 'refdef'


# -- clips in pull / preview (pull loads vids too) --------------------------- #
def _clip(path, w=64, h=48, n=3) -> str:
    import av
    import numpy as np

    with av.open(str(path), 'w') as out:
        st = out.add_stream('mpeg4', rate=8)
        st.width, st.height, st.pix_fmt = w, h, 'yuv420p'
        for i in range(n):
            arr = np.full((h, w, 3), 40 * i, dtype=np.uint8)
            for pkt in st.encode(av.VideoFrame.from_ndarray(arr, format='rgb24')):
                out.mux(pkt)
        for pkt in st.encode():
            out.mux(pkt)
    return str(path)


def test_clip_is_usable_and_previews(tmp_path):
    from aidb.app.tab_refdef import RefdefTab, _img_dims

    clip = _clip(tmp_path / 'c.mp4')
    assert RefdefTab._is_usable(clip)
    assert not RefdefTab._is_usable(str(tmp_path / 'missing.mp4'))
    im = RefdefTab._preview(clip)
    assert im is not None and im.size == (64, 48)
    assert _img_dims(clip) == (64, 48)


def test_patch_clip_dims(tmp_path):
    clip = _clip(tmp_path / 'c.mp4', w=80, h=40)
    old = {'kind': 'video', 'slot': 1, 'url': '/r/old.mp4', 'vid': 1, 'w': 1, 'h': 1}
    p = _iteration(prompts_ref=_ref_section([old]))
    out, changed, _ = patch_iteration(p, 'ref', [clip])
    ref = out['prompts_ref']['prompt_data'][0]['refs'][0]
    assert changed == ['prompts_ref.refs[0]'] and (ref['w'], ref['h']) == (80, 40)
    # a clip never lands in a qwen21 still slot (board task 162)
    p = _iteration(prompts_inp=_inp())
    out, changed, skipped = patch_iteration(p, 'inp', [clip, '/c/face.png'])
    assert changed == [] and skipped == ['slot 1 (video in a qwen21 still slot)']
    assert out['prompts_inp'] == p['prompts_inp']


# --- 💾 save history ---------------------------------------------------- #
def test_hist_step():
    from aidb.app.tab_refdef import hist_step

    assert hist_step(None, 3, -1) == 2  # current → newest save
    assert hist_step(2, 3, 1) is None  # newest save → current
    assert hist_step(None, 3, 1) is None  # current is the last stop
    assert hist_step(0, 3, -1) == 0  # oldest is the first stop
    assert hist_step(None, 0, -1) is None  # no saves: stays current
    assert hist_step(5, 3, -1) == 2  # stale pointer clamps


def test_snap_doc_roundtrip():
    from aidb.app.tab_refdef import doc_to_snap, snap_to_doc

    st = parse_payload(json.dumps(_iteration()))
    st['payload']['$odd.key'] = 1  # Mongo-hostile key survives as JSON
    snap = {
        'state': st,
        'idx': 1,
        'refs': ['/a.png', '', 'abc'],
        'roles': ['r1', '', ''],
        'verb': 'enh',
        'kind': 'prompt',
        'text': 't',
        'clip': json.dumps(_iteration()),
    }
    doc = snap_to_doc(snap)
    assert doc['has_clip'] and isinstance(doc['clip_json'], str)
    assert doc['mode'] == 'enhancer' and doc['scene_id'] == 'abc'
    assert isinstance(doc['state_json'], str)
    assert doc_to_snap(doc) == snap
    assert snap_to_doc(dict(snap, state=None))['mode'] == 'instruction'


def test_norm_cat():
    from aidb.app.tab_refdef import CAT_ALL, norm_cat

    assert norm_cat(CAT_ALL) is None and norm_cat('  ') is None and norm_cat(None) is None
    assert norm_cat(' faces ') == 'faces'


def test_six_slots_and_media_kind(tmp_path):
    from aidb.app.tab_refdef import N_SLOTS, RefdefTab, media_kind

    assert N_SLOTS == 6
    assert [media_kind(u) for u in ('/a.PNG', '/b.mp4', '/c.wav', '/d.txt', None)] == [
        'image',
        'video',
        'audio',
        None,
        None,
    ]
    slots = [{'url': f'/s{i}.mp3', 'id': None, 'role': ''} for i in range(N_SLOTS)]
    p = refdef_payload(slots, 'enh', 'hint', '')
    assert [r['slot'] for r in p['refs']] == list(range(1, N_SLOTS + 1))
    assert {r['media'] for r in p['refs']} == {'audio'}
    # extra slots on a 1-image view are skipped, not deployed
    _, _, skipped = patch_iteration(_iteration(), 'main', [None] * 5 + ['/x.png'])
    assert skipped == ['slot 6 (main has one image)']
    # an audio file is pullable and previews as a waveform
    import av
    import numpy as np

    wav = tmp_path / 'tone.wav'
    with av.open(str(wav), 'w') as out:
        st = out.add_stream('pcm_s16le', rate=8000, layout='mono')
        sig = (np.sin(np.arange(8000) / 5) * 8000).astype('int16').reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(sig, format='s16', layout='mono')
        frame.sample_rate = 8000
        for pkt in st.encode(frame):
            out.mux(pkt)
        for pkt in st.encode(None):
            out.mux(pkt)
    assert RefdefTab._is_usable(str(wav))
    im = RefdefTab._preview(str(wav))
    assert im is not None and im.size[0] > im.size[1]


def test_ref_novis_needs_roles():
    from aidb.app.tab_refdef import VERBS, missing_roles

    assert 'ref-novis' in VERBS
    slots = [
        {'url': '/a.png', 'id': None, 'role': 'red dress'},
        {'url': '/b.wav', 'id': None, 'role': '  '},
        {'url': None, 'id': None, 'role': ''},
    ]
    assert missing_roles(slots, 'ref-novis') == []  # only slot 1 needs a role
    assert missing_roles([dict(slots[0], role=' '), *slots[1:]], 'ref-novis') == [1]
    assert missing_roles([dict(slots[0], url=None), *slots[1:]], 'ref-novis') == [1]
    assert missing_roles([dict(slots[0], role='')], 'ref') == []
    assert refdef_payload(slots, 'ref-novis', 'hint', '')['verb'] == 'ref-novis'


def test_ref_view_v68_slots_and_kinds():
    """v6.8: compacted refs carry their slot; kinds are never swapped."""
    p = _iteration(
        rev=3,
        prompts_ref={
            'type': 'single',
            'current': 0,
            'prompt_data': [
                {
                    'prompt': '<Picture 1> … <Audio 1>',
                    'from_rev': 3,
                    'ts': '2026-11-03T08:00:00',
                    'refs': [
                        {'kind': 'image', 'slot': 1, 'url': '/r/p1.png', 'pic': 1, 'desc': 'red'},
                        {'kind': 'audio', 'slot': 4, 'url': '/r/v.wav', 'aud': 1, 'desc': 'voice'},
                    ],
                }
            ],
        },
    )
    st = with_view(parse_payload(json.dumps(p)), 'ref')
    assert [s['url'] for s in st['slots']] == ['/r/p1.png', None, None, '/r/v.wav', None, None]
    assert st['slots'][3]['role'] == 'voice'
    urls = ['/r/p9.png', None, None, '/r/x.png', None, None]
    out, changed, skipped = patch_iteration(p, 'ref', urls)
    assert changed == ['prompts_ref.refs[0]']
    assert skipped == ['slot 4 (audio → image would renumber the prompt)']
    refs = out['prompts_ref']['prompt_data'][0]['refs']
    assert refs[0]['url'] == '/r/p9.png' and refs[1]['url'] == '/r/v.wav'
    _, changed, skipped = patch_iteration(p, 'ref', ['/r/p1.png', None, None, '/r/w.mp3'])
    assert changed == ['prompts_ref.refs[1]'] and not skipped
    _, _, skipped = patch_iteration(p, 'ref', ['/r/p1.png', '/r/n.png', None, '/r/v.wav'])
    assert skipped == ['slot 2 (adding a ref would renumber the prompt)']


def test_enh_clip():
    from aidb.app.tab_refdef import enh_clip

    assert json.loads(enh_clip(json.dumps(_iteration())))['scene_id'] == 'abc'
    assert enh_clip(json.dumps({'schema_id': SCHEMA_REFDEF, 'refs': []})) is None
    assert enh_clip('/x/a.png') is None and enh_clip(None) is None


def _ref_section(refs) -> dict:
    return {
        'type': 'single',
        'current': 0,
        'prompt_data': [{'prompt': 'p', 'refs': refs, 'from_rev': 2, 'ts': '2026-11-03T09:40'}],
    }


def test_update_task162_ref_and_inp_sections():
    """Board task 162: both sections present; the verb decides which is patched."""
    ref_refs = [
        {'kind': 'video', 'slot': 1, 'url': '/r/clip.mkv', 'vid': 1},
        {'kind': 'image', 'slot': 2, 'url': '/r/woman.png', 'pic': 1},
    ]
    p = _iteration(prompts_ref=_ref_section(ref_refs), prompts_inp=_inp())
    text = json.dumps(p)
    slots = [_slot('/r/clip.mkv'), _slot('/r/new.png')]
    for verb in ('ref', 'ref-novis'):
        out, view, changed, skipped = update_payload(text, slots, 'inp', verb)
        assert view == 'ref' and changed == ['prompts_ref.refs[1]'] and not skipped
        assert out['prompts_ref']['prompt_data'][0]['refs'][1]['url'] == '/r/new.png'
        assert json.dumps(out['prompts_inp']) == json.dumps(p['prompts_inp'])
    for verb in ('inp-mask', 'inp-nomask'):
        out, view, changed, skipped = update_payload(text, slots, 'ref', verb)
        assert view == 'inp' and json.dumps(out['prompts_ref']) == json.dumps(p['prompts_ref'])
        assert out['prompts_inp']['prompt_data'][0]['src']['url'] == '/c/src.png'  # no .mkv
        assert 'slot 1 (video in a qwen21 still slot)' in skipped
        assert changed == ['prompts_inp.refs[0]']
