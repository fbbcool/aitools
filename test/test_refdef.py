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
            assert sent == [('agent', 'prompt', tab_refdef.HERDR_AGENT, '/refdef')]


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
        'vision': [False, True, False],
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


def test_ten_slots_and_media_kind(tmp_path):
    from aidb.app.tab_refdef import N_SLOTS, RefdefTab, media_kind

    assert N_SLOTS == 10
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
    _, _, skipped = patch_iteration(_iteration(), 'main', [None] * 9 + ['/x.png'])
    assert skipped == ['slot 10 (main has one image)']
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
    assert [s['url'] for s in st['slots']] == [
        '/r/p1.png',
        None,
        None,
        '/r/v.wav',
        *[None] * 6,
    ]
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


def test_img_fsw_novis_swap_problems():
    from aidb.app.tab_refdef import VERB_VIEW, VERBS, missing_roles, swap_problems

    assert 'img-fsw-novis' in VERBS
    assert VERB_VIEW['img-fsw-novis'] == 'inp'
    tgt = {'url': '/target.png', 'id': None, 'role': ''}
    head = {'url': '/head.jpg', 'id': None, 'role': ''}
    assert swap_problems([tgt, head], 'img-fsw-novis') == []  # roles optional
    assert missing_roles([tgt, head], 'img-fsw-novis') == []
    assert swap_problems([tgt], 'img-fsw-novis') == ['slot 2 needs the reference head (image)']
    vid = dict(tgt, url='/clip.mp4')
    assert swap_problems([vid, head], 'img-fsw-novis') == ['slot 1 needs the target (image)']
    extra = [tgt, head, dict(head, url='/x.png')]
    assert swap_problems(extra, 'img-fsw-novis') == ['slot 3 must be empty (2 images only)']
    assert swap_problems([], 'ref') == []
    p = refdef_payload([tgt, head], 'img-fsw-novis', 'hint', 'keep the freckles')
    assert p['verb'] == 'img-fsw-novis'
    assert [r['media'] for r in p['refs'][:2]] == ['image', 'image']
    # empty roles deploy as the default swap semantics; own roles stay verbatim
    from aidb.app.tab_refdef import SWAP_DEFAULT_ROLES

    assert [r['role'] for r in p['refs'][:2]] == list(SWAP_DEFAULT_ROLES)
    own = refdef_payload([dict(tgt, role='the knight'), head], 'img-fsw-novis', 'hint', '')
    assert [r['role'] for r in own['refs'][:2]] == ['the knight', SWAP_DEFAULT_ROLES[1]]
    assert refdef_payload([tgt, head], 'ref', 'hint', '')['refs'][0]['role'] == ''


def test_hand_mask_roundtrip(tmp_path, monkeypatch):
    import os

    import aidb.app.tab_refdef as rd
    from PIL import Image, PngImagePlugin

    monkeypatch.setattr(rd, 'MASK_DIR', tmp_path / 'masks')
    src = tmp_path / 'target.png'
    info = PngImagePlugin.PngInfo()
    info.add_text('ait', '{"x": 1}')
    Image.new('RGB', (200, 100), (10, 20, 30)).save(src, pnginfo=info)
    url = str(src)
    assert rd.mask_of(url) is None
    # painted at half the editor size: left half masked
    painted = Image.new('L', (100, 50), 0)
    painted.paste(200, (0, 0, 50, 50))
    mask, masked = rd.write_mask(url, painted)
    assert rd.mask_of(url) == (mask, masked)
    m = Image.open(mask)
    assert m.size == (200, 100) and m.getpixel((10, 10)) == 255 and m.getpixel((190, 90)) == 0
    rgba = Image.open(masked)
    assert rgba.mode == 'RGBA' and rgba.getpixel((10, 10))[3] == 0
    assert rgba.getpixel((190, 90)) == (10, 20, 30, 255)
    assert rgba.info.get('ait') == '{"x": 1}'  # metadata chunks survive
    tinted = rd.tint_mask(Image.new('RGB', (200, 100), (0, 0, 0)), url)
    assert tinted.getpixel((10, 10))[0] > 0 and tinted.getpixel((190, 90)) == (0, 0, 0)
    # deploy carries the mask.v1 raster object on the masked ref only (task 175)
    obj = rd.mask_object(url)
    assert obj == {
        'schema_id': '1xlasm_enhancer.mask.v1',
        'type': 'raster',
        'url': mask,
        'w': 200,
        'h': 100,
        'sha': rd.file_sha(url),
    }
    assert len(obj['sha']) == 12
    slots = [{'url': url, 'id': None, 'role': '', 'mask': obj}, {'url': None}]
    refs = rd.refdef_payload(slots, 'inp-mask', 'hint', '')['refs']
    assert refs[0]['mask'] == obj and 'masked' not in refs[0]
    assert 'mask' not in refs[1]
    # empty paint = remove
    assert rd.write_mask(url, Image.new('L', (100, 50), 0)) is None
    assert rd.mask_of(url) is None and not os.path.exists(mask)
    assert rd.mask_of('/x/clip.mp4') is None


def test_painted_from_editor_value():
    from aidb.app.tab_refdef import RefdefTab
    from PIL import Image

    bg = Image.new('RGB', (40, 20))
    layer = Image.new('RGBA', (40, 20), (0, 0, 0, 0))
    layer.paste((255, 0, 0, 128), (0, 0, 10, 10))
    m = RefdefTab._painted({'background': bg, 'layers': [layer], 'composite': None})
    assert m.getpixel((5, 5)) == 255 and m.getpixel((30, 15)) == 0
    assert RefdefTab._painted({'background': bg, 'layers': []}).getbbox() is None
    assert RefdefTab._painted(None) is None


def test_rasterize_json_mask():
    from aidb.app.tab_refdef import rasterize_mask

    m = {
        'schema_id': '1xlasm_enhancer.mask.v1',
        'type': 'json',
        'shapes': [
            {'kind': 'rect', 'coords': [0.0, 0.0, 0.5, 1.0]},
            {'kind': 'rect', 'op': 'sub', 'coords': [0.0, 0.0, 0.5, 0.5]},
            {'kind': 'circle', 'coords': [0.75, 0.5, 0.1]},
        ],
    }
    im = rasterize_mask(m, (100, 100))
    assert im.getpixel((10, 80)) == 255  # rect minus top half
    assert im.getpixel((10, 10)) == 0  # subtracted
    assert im.getpixel((75, 50)) == 255 and im.getpixel((95, 95)) == 0  # circle
    inv = rasterize_mask(dict(m, invert=True), (100, 100))
    assert inv.getpixel((10, 10)) == 255
    # time-only (audio) / unknown schema / no mask -> no spatial preview
    assert rasterize_mask({'type': 'json', 'ranges': [[0, 1]]}, (10, 10)) is None
    assert rasterize_mask({'schema_id': 'x.mask.v1', 'type': 'json', 'shapes': []}, (9, 9)) is None
    assert rasterize_mask(None, (10, 10)) is None


def test_patch_masks_bound_to_media():
    from aidb.app.tab_refdef import view_slots

    tab = {'schema_id': '1xlasm_enhancer.mask.v1', 'type': 'raster', 'url': '/m/a.png', 'sha': 's1'}
    enh = {'schema_id': '1xlasm_enhancer.mask.v1', 'type': 'json', 'shapes': []}
    p = _iteration(prompts_inp=_inp(), url_mask=enh)
    p['prompts_inp']['prompt_data'][0]['refs'][0]['mask'] = enh
    # the view exposes payload masks; main = url_mask
    assert view_slots(p, 'inp')[1]['mask'] == enh
    assert view_slots(p, 'main')[0]['mask'] == enh
    # same url, no tab mask -> payload mask kept, verbatim
    out, changed, _ = patch_iteration(p, 'inp', ['/c/src.png', '/c/face.png'], [None, None])
    assert changed == [] and out == p
    # tab mask on an unchanged url -> set
    out, changed, _ = patch_iteration(p, 'inp', ['/c/src.png', '/c/face.png'], [tab, None])
    assert changed == ['prompts_inp.src.mask']
    assert out['prompts_inp']['prompt_data'][0]['src']['mask'] == tab
    # the same tab mask again -> no change
    _, changed, _ = patch_iteration(out, 'inp', ['/c/src.png', '/c/face.png'], [tab, None])
    assert changed == []
    # replaced url without a tab mask -> the old media's mask is dropped
    out, changed, _ = patch_iteration(p, 'inp', ['/c/src.png', '/c/face2.png'])
    assert changed == ['prompts_inp.refs[0]']
    assert 'mask' not in out['prompts_inp']['prompt_data'][0]['refs'][0]
    # main: new url drops url_mask; a tab mask sets it
    out, changed, _ = patch_iteration(p, 'main', ['/y.png'])
    assert 'url_mask' not in out and changed == ['url']
    out, changed, _ = patch_iteration(p, 'main', ['/y.png'], [tab])
    assert out['url_mask'] == tab and changed == ['url', 'url_mask']


def test_mask_off_drops_payload_masks():
    """🟥/⬜ off: patching / ⇄ update drop the slot media's mask, on keeps it."""
    m = {'schema_id': '1xlasm_enhancer.mask.v1', 'type': 'json', 'shapes': [{'k': 1}]}
    p = _iteration(url_mask=m)
    out, changed, _ = patch_iteration(p, 'main', [p['url']], [False])
    assert changed == ['url_mask'] and 'url_mask' not in out
    out, changed, _ = patch_iteration(p, 'main', [p['url']], [None])
    assert changed == [] and out['url_mask'] == m
    inp = _inp(refs=[{'url': '/c/face.png', 'w': 832, 'h': 1248, 'desc': 'f', 'mask': m}])
    p = _iteration(prompts_inp=inp)
    off = dict(_slot('/c/face.png'), mask_off=True)
    out, view, changed, _ = update_payload(
        json.dumps(p), [_slot('/c/src.png'), off], 'inp', 'inp-mask'
    )
    assert view == 'inp' and changed == ['prompts_inp.refs[0].mask']
    assert 'mask' not in out['prompts_inp']['prompt_data'][0]['refs'][0]
    # refdef.v1: off drops the ref's mask
    instr = refdef_payload([{'url': '/a.png', 'role': 'r', 'mask': m}], 'enh', 'hint', '')
    out, _, changed, _ = update_payload(json.dumps(instr), [dict(_slot('/a.png'), mask_off=True)])
    assert changed == ['refs[slot 1]'] and 'mask' not in out['refs'][0]


def _png(path, size=(64, 96)):
    from PIL import Image

    Image.new('RGB', size, (10, 20, 30)).save(path)
    return str(path)


def test_qfix_problems():
    """inp-qfix (FEATURE 180): slot 1 image, 0-2 still refs, non-empty text."""
    from aidb.app.tab_refdef import qfix_problems

    ok = [_slot('/a.png'), _slot('/b.png'), _slot('/c.png')]
    assert qfix_problems(ok, 'inp-qfix') == []  # _slot role = 'ignored' = the instruction
    assert qfix_problems([], 'enh') == []  # other verbs: no say
    assert qfix_problems([_slot('/a.mp4')], 'inp-qfix') == ['slot 1 needs the edit target (image)']
    assert qfix_problems([dict(_slot('/a.png'), role='  ')], 'inp-qfix') == [
        'slot 1 role (the qwen21 edit instruction) is empty'
    ]
    four = [*ok, _slot('/d.png')]
    assert qfix_problems(four, 'inp-qfix') == ['max 2 refs (image 2 / image 3), got 3']
    assert qfix_problems([_slot('/a.png'), _slot('/v.mp4')], 'inp-qfix') == [
        'slot 2 must be a still image'
    ]


def test_qfix_payload_mask_and_nomask(tmp_path):
    """qfix_payload = enhancer data a SmartInput reads: prompts_inp entry with
    src(+mask) / refs / prompt_qwen21; pulls back on the inp view."""
    from aidb.app.tab_refdef import SCHEMA_MASK, qfix_payload

    a, b = _png(tmp_path / 'a.png'), _png(tmp_path / 'b.png', (32, 32))
    m = {'schema_id': SCHEMA_MASK, 'type': 'raster', 'url': '/m.png', 'w': 64, 'h': 96, 'sha': 's'}
    role = ' make the hand five-fingered '
    slots = [dict(_slot(a), role=role, mask=m), _slot(None), dict(_slot(b), role='')]
    p = qfix_payload(slots, ' a hint ', 'sid1')
    assert p['schema_id'].startswith('1xlasm_enhancer.iteration.')
    assert p['url'] == a and p['url_mask'] == m and p['edited_by'] == EDITED_BY
    assert p['scene_id'] == 'sid1' and p['rev'] == 0
    e = p['prompts_inp']['prompt_data'][0]
    assert e['prompt_qwen21'] == 'make the hand five-fingered' and e['engine'] == 'qwen21'
    assert e['mode'] == 'mask' and e['mask'] is None and e['from_rev'] == 0
    assert e['hints'] == 'a hint'
    assert e['src'] == {'url': a, 'w': 64, 'h': 96, 'desc': 'edit target', 'mask': m}
    assert e['refs'] == [{'url': b, 'w': 32, 'h': 32, 'desc': 'image 2'}]  # slot 3 → image 2
    st = parse_payload(json.dumps(p))
    assert st['view'] == 'inp' and st['slots'][0]['url'] == a and st['slots'][1]['url'] == b
    assert st['text'] == 'make the hand five-fingered'
    assert st['slots'][0]['role'] == 'make the hand five-fingered'  # pulled back into slot 1
    assert parse_payload(json.dumps(dict(p, made_by=None)))['slots'][0]['role'] == 'edit target'
    # nomask: no painted mask, or masking switched off
    for s1 in (_slot(a), dict(_slot(a), mask=m, mask_off=True)):
        p = qfix_payload([s1])
        e = p['prompts_inp']['prompt_data'][0]
        assert e['mode'] == 'nomask' and 'mask' not in e['src'] and 'refs' not in e
        assert e['prompt_qwen21'] == 'ignored' and e['hints'] is None
        assert 'url_mask' not in p and p['scene_id'] is None


def test_qfix_update_patches_inp_only(tmp_path):
    """⇄ update with inp-qfix patches the inp view (VERB_VIEW)."""
    from aidb.app.tab_refdef import qfix_payload

    a, c = _png(tmp_path / 'a.png'), _png(tmp_path / 'c.png')
    p = qfix_payload([_slot(a)])
    out, view, changed, _ = update_payload(json.dumps(p), [_slot(c)], None, 'inp-qfix')
    assert view == 'inp' and changed == ['prompts_inp.src']
    assert out['prompts_inp']['prompt_data'][0]['src']['url'] == c


def test_qfix_deploy_toasts(tmp_path, monkeypatch):
    """inp-qfix deploy (FEATURE 180): success toast 0.5 s after a clipspace
    read-back, failure → error toast 2 s and nothing claimed deployed."""
    from aidb.app import tab_refdef

    clip = {}
    toasts = []
    monkeypatch.setattr(tab_refdef, 'clip_copy', lambda t: clip.update(v=t))
    monkeypatch.setattr(tab_refdef.pyperclip, 'paste', lambda: clip.get('v'))
    for kind in ('Success', 'Error'):
        monkeypatch.setattr(
            tab_refdef.gr, kind, lambda m, duration=None, k=kind: toasts.append((k, m, duration))
        )
    deploy = tab_refdef.RefdefTab._deploy_qfix
    a = _png(tmp_path / 'a.png')
    msg = deploy([dict(_slot(a), role='fix it'), _slot(a)], '', None)
    assert toasts == [('Success', 'inp-qfix deployed: nomask, 1 refs', 0.5)]
    assert msg.startswith('inp-qfix deployed') and json.loads(clip['v'])['url'] == a
    toasts.clear()
    monkeypatch.setattr(tab_refdef.pyperclip, 'paste', lambda: 'stale')
    msg = deploy([dict(_slot(a), role='fix it')], '', None)
    assert (
        toasts[0][0] == 'Error' and toasts[0][2] == 2 and 'clipspace write failed' in toasts[0][1]
    )
    assert msg.startswith('NOT deployed')


def test_disable_slots():
    from aidb.app.tab_refdef import disable_slots

    rr = ['/a.png', 'role a', '/b.png', 'role b', '', '']
    assert disable_slots(rr, [True, False, True]) == ['/a.png', 'role a', '', '', '', '']
    assert disable_slots(rr, [True] * 3) == rr
    assert disable_slots(rr, None) == rr
    assert rr[2] == '/b.png'  # input untouched


def test_h3_ref_budget():
    """FEATURE t181: 6 pictures / 2 clips / 2 audio files, 12 refs with soundtracks."""
    from aidb.app.tab_refdef import ref_budget_problems

    def sl(*urls, audio=()):
        return [
            {'url': u, 'id': None, 'role': '', **({'audio': True} if u in audio else {})}
            for u in urls
        ]

    pics = [f'/p{i}.png' for i in range(1, 7)]
    full = sl(*pics, '/v1.mp4', '/v2.mp4', '/a1.wav', '/a2.wav', audio=('/v1.mp4', '/v2.mp4'))
    for verb in ('ref', 'ref-novis', 'pre-vid', 'post-vid'):
        assert ref_budget_problems(full, verb) == []  # exactly 12
    assert ref_budget_problems(sl(*pics[:4]), 'ref') == []
    assert ref_budget_problems(sl(*pics, '/p7.png'), 'ref') == ['max 6 pictures, got 7']
    assert ref_budget_problems(sl('/v1.mp4', '/v2.mp4', '/v3.mp4'), 'ref') == ['max 2 clips, got 3']
    assert ref_budget_problems(sl('/p.png', '/a.wav', '/b.wav', '/c.mp3'), 'ref-novis') == [
        'max 2 audios, got 3'
    ]
    # 7 + 2 + 2 + 2 soundtracks = 13: per-kind cap and total both fire
    over = sl(
        *pics, '/p7.png', '/v1.mp4', '/v2.mp4', '/a1.wav', '/a2.wav', audio=('/v1.mp4', '/v2.mp4')
    )
    assert ref_budget_problems(over, 'ref') == [
        'max 6 pictures, got 7',
        'max 12 refs in total (soundtracks counted), got 13',
    ]
    # a clip without audio: true does not count its soundtrack
    assert ref_budget_problems(sl(*pics, '/v1.mp4', '/v2.mp4', '/a1.wav', '/a2.wav'), 'ref') == []
    # the other verbs have their own rules
    assert ref_budget_problems(sl(*pics, '/p7.png'), 'enh') == []


def test_ref_view_ten_slots_skip_and_kind_labels():
    from aidb.app.tab_refdef import N_SLOTS, _ref_slots, view_slots

    refs = [
        {'kind': 'image', 'slot': 1, 'url': '/p1.png'},
        {'kind': 'video', 'slot': 7, 'url': '/v1.mp4', 'audio': True},
        {'kind': 'image', 'slot': 10, 'url': '/p6.png'},
        {'kind': 'audio', 'slot': 11, 'url': '/a.wav'},  # out of range: skipped
        {'kind': 'audio', 'slot': 0, 'url': '/b.wav'},  # out of range: skipped
    ]
    out = _ref_slots({'refs': refs})
    assert len(out) == N_SLOTS
    assert [r and r['url'] for r in out] == [
        '/p1.png',
        *[None] * 5,
        '/v1.mp4',
        None,
        None,
        '/p6.png',
    ]
    p = _iteration(
        prompts_ref={
            'type': 'single',
            'current': 0,
            'prompt_data': [{'prompt': 'x', 'refs': refs, 'ts': 't'}],
        }
    )
    roles = [s['role'] for s in view_slots(p, 'ref') if s['url']]
    assert roles == ['picture 1', 'clip 1', 'picture 2']


# -- slot 1 carried refs (refdef.v1 `inherit`) -------------------------- #
def test_carry_tag():
    from aidb.app.tab_refdef import carry_tag

    assert carry_tag({'kind': 'image', 'pic': 2}) == 'pic 2'
    assert carry_tag({'kind': 'video', 'vid': 1}) == 'vid 1'
    assert carry_tag({'kind': 'audio'}) == 'aud'
    assert carry_tag({}) == '?'


def test_carry_of_non_clip():
    from aidb.app.tab_refdef import carry_of

    for url in (None, '', '/x/a.png', '/x/a.wav'):
        assert carry_of(url) == {'anchor': None, 'refs': [], 'on': [], 'error': None}


def test_inherit_list_and_payload():
    from aidb.app.tab_refdef import inherit_list

    carry = {
        'anchor': '/c/fbbcool_temp_kiwny_00001_.mkv',
        'refs': [
            {'kind': 'video', 'vid': 1, 'url': '/r/doll.mov', 'desc': 'doll'},
            {'kind': 'image', 'pic': 1, 'url': '/r/man.png'},
        ],
        'on': [False, True],
        'error': None,
    }
    inh = inherit_list(carry, carry['anchor'])
    assert [(r['n'], r['tag'], r['use']) for r in inh] == [(1, 'vid 1', False), (2, 'pic 1', True)]
    assert inh[0]['url'] == '/r/doll.mov' and inh[1]['desc'] == ''
    assert inherit_list(carry, '/c/other.mkv') is None  # stale panel
    assert inherit_list(None, carry['anchor']) is None

    slots = [{'url': carry['anchor'], 'role': ''}]
    p = refdef_payload(slots, 'post-vid', 'hint', 'go', inherit=inh)
    assert p['inherit'] == inh and p['continue']['dir'] == 'post'
    assert 'inherit' not in refdef_payload(slots, 'post-vid', 'hint', 'go')
    assert 'inherit' not in refdef_payload(slots, 'ref', 'hint', 'go', inherit=inh)


# -- ref-img: qwen21 reference-to-image, novis (FEATURE t187) ------------ #
def test_ref_img_problems():
    from aidb.app.tab_refdef import VERB_VIEW, VERBS, img_ref_problems, missing_roles

    assert 'ref-img' in VERBS and 'ref-img' not in VERB_VIEW  # no enhancer view (yet)
    im = {'url': '/a.png', 'id': None, 'role': ''}
    e = {'url': '', 'id': None, 'role': ''}
    for n in (1, 2, 3, 4, 5):
        assert img_ref_problems([im] * n, 'ref-img') == []
    assert img_ref_problems([e, e, im], 'ref-img') == []  # gaps ok: compacted downstream
    assert missing_roles([im], 'ref-img') == []  # roles optional
    assert img_ref_problems([], 'ref-img') == ['needs 1-5 🖼 images']
    assert img_ref_problems([dict(im, url='/c.mp4'), im], 'ref-img') == [
        'slot 1 is video (🖼 images only)'
    ]
    assert img_ref_problems([im, dict(im, url='/v.wav')], 'ref-img') == [
        'slot 2 is audio (🖼 images only)'
    ]
    assert img_ref_problems([im] * 6, 'ref-img') == [
        '6 🖼 pixel images (max 5) — switch some to 👁 or empty them'
    ]
    assert img_ref_problems([e, e, e, e, im], 'ref-img') == []
    assert img_ref_problems([im] * 6, 'ref') == []  # other verbs unaffected


def test_ref_img_payload_ships_masks_keeps_roles():
    mask = {'schema_id': '1xlasm_enhancer.mask.v1', 'type': 'raster', 'url': '/m.png'}
    slots = [
        {'url': '/face1.png', 'id': None, 'role': 'the face', 'mask': mask},
        {'url': '/face2.png', 'id': None, 'role': ''},
    ]
    p = refdef_payload(slots, 'ref-img', 'prompt', 'a face sheet, 6 panels')
    assert p['schema_id'] == SCHEMA_REFDEF and p['verb'] == 'ref-img'
    assert p['kind'] == 'prompt' and p['text'] == 'a face sheet, 6 panels'
    assert [(r['slot'], r['role'], r['media']) for r in p['refs'][:2]] == [
        (1, 'the face', 'image'),
        (2, '', 'image'),
    ]  # no default roles
    assert p['refs'][0]['mask'] == mask and 'mask' not in p['refs'][1]  # t195: shipped
    assert 'continue' not in p and 'inherit' not in p
    assert refdef_payload(slots, 'ref', 'hint', '')['refs'][0]['mask'] == mask


class _FakeCol:
    """Just enough of a pymongo collection for the predefined-prompt helpers."""

    def __init__(self):
        self.docs = []

    def find(self, flt=None, proj=None):
        return [{k: v for k, v in d.items() if k != '_id'} for d in self.docs]

    def find_one(self, flt):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in flt.items())), None)

    def replace_one(self, flt, doc, upsert=False):
        self.docs = [d for d in self.docs if d.get('name') != flt['name']] + [dict(doc)]

    def delete_one(self, flt):
        n = len(self.docs)
        self.docs = [d for d in self.docs if d.get('name') != flt['name']]

        class R:
            deleted_count = n - len(self.docs)

        return R()


def test_predefined_prompts():
    import pytest

    from aidb.app.tab_refdef import (
        delete_prompt,
        list_prompts,
        parse_models,
        prompt_label,
        save_prompt,
        seed_prompts,
    )

    assert parse_models('') == ['generic'] and parse_models(None) == ['generic']
    assert parse_models(' qwen21, h3 ,qwen21') == ['qwen21', 'h3']
    col = _FakeCol()
    assert list_prompts(None) == [] and seed_prompts(None) == 0
    assert seed_prompts(col) == 1 and seed_prompts(col) == 0  # idempotent
    (fs,) = list_prompts(col)
    assert fs['name'] == 'facesheet' and fs['models'] == ['qwen21']
    assert fs['prompt'].startswith('face reference sheet, 3×2 grid')
    assert prompt_label(fs) == 'character-gen / facesheet [qwen21]'
    save_prompt(col, 'b', '', '', 'x')
    assert prompt_label(list_prompts(col)[0]) == '- / b [generic]'  # uncategorized first
    save_prompt(col, 'b', 'a-cat', 'h3', 'y')  # same name → overwrite
    assert [d['name'] for d in list_prompts(col)] == ['b', 'facesheet']
    assert list_prompts(col)[0]['prompt'] == 'y' and len(col.docs) == 2
    for bad in (('', 'c', '', 'x'), ('n', 'c', '', '  ')):
        with pytest.raises(ValueError):
            save_prompt(col, *bad)
    assert delete_prompt(col, 'b') and not delete_prompt(col, 'b') and not delete_prompt(col, '')
    assert [d['name'] for d in list_prompts(col)] == ['facesheet']


# ---------------------------------------------------------------------- #
# 🖼 pixel / 👁 vision switch (FEATURE t189)
# ---------------------------------------------------------------------- #
def _vslots(*urls, vision=()):
    from aidb.app.tab_refdef import N_SLOTS

    slots = [{'url': u, 'id': None, 'role': f'r{i + 1}'} for i, u in enumerate(urls)]
    slots += [{'url': None, 'id': None, 'role': ''}] * (N_SLOTS - len(slots))
    for n in vision:
        slots[n - 1] = {**slots[n - 1], 'vision': True}
    return slots


def test_vision_payload_use_field_and_default_unchanged():
    from aidb.app.tab_refdef import refdef_payload

    plain = _vslots('/a/x.png', '/a/y.png')
    base = refdef_payload(plain, 'ref', 'hint', 't')
    assert all('use' not in r for r in base['refs'])
    vis = refdef_payload(_vslots('/a/x.png', '/a/y.png', vision=(2,)), 'ref-novis', 'hint', 't')
    assert vis['refs'][1]['use'] == 'vision' and 'use' not in vis['refs'][0]
    # all 🖼 → byte-identical to a payload built without the switch
    assert json.dumps(refdef_payload(plain, 'ref', 'hint', 't')) == json.dumps(base)


def test_vision_locks_audio_and_qfix():
    from aidb.app.tab_refdef import vision_ignored, vision_locked, vision_slots

    assert vision_locked(0, 'img-fsw-novis') and vision_locked(1, 'img-fsw-novis')
    assert not vision_locked(2, 'img-fsw-novis')
    for verb in ('pre-vid', 'post-vid', 'inp-mask', 'inp-nomask', 'pickup'):
        assert vision_locked(0, verb) and not vision_locked(1, verb)
    assert not vision_locked(0, 'ref')
    s = _vslots('/a/x.png', '/a/y.png', '/a/z.wav', vision=(1, 2, 3))
    assert vision_slots(s, 'img-fsw-novis') == []
    assert vision_ignored(s, 'img-fsw-novis') == [1, 2, 3]
    assert vision_slots(s, 'ref') == [1, 2]  # audio has no 👁
    assert vision_slots(s, 'inp-qfix') == []


def test_vision_outside_budget_and_mask_shipped():
    from aidb.app.tab_refdef import ref_budget_problems, refdef_payload

    imgs = [f'/a/{i}.png' for i in range(7)]
    assert ref_budget_problems(_vslots(*imgs), 'ref')
    assert ref_budget_problems(_vslots(*imgs, vision=(7,)), 'ref') == []
    s = _vslots('/a/x.png', '/a/y.png', vision=(2,))
    s[1]['mask'] = {'schema_id': 'm'}
    r2 = refdef_payload(s, 'ref', 'hint', '')['refs'][1]
    assert r2['use'] == 'vision' and r2['mask'] == {'schema_id': 'm'}  # t195: where to look


def test_vision_ref_img_needs_a_pixel_image():
    from aidb.app.tab_refdef import img_ref_problems

    assert img_ref_problems(_vslots('/a/x.png', vision=(1,)), 'ref-img')
    assert img_ref_problems(_vslots('/a/x.png', '/a/y.png', vision=(1,)), 'ref-img') == []


def test_ref_img_counts_pixel_slots_t194():
    from aidb.app.tab_refdef import img_ref_problems, refdef_payload

    x = '/a/x.png'
    # 1-4 pixel + 👁 image in slot 6 -> ok, slot 6 ships as vision
    s = _vslots(x, x, x, x, None, x, vision=(6,))
    assert img_ref_problems(s, 'ref-img') == []
    assert refdef_payload(s, 'ref-img', 'hint', '')['refs'][5]['use'] == 'vision'
    # gaps: pixel in 2 / 6 / 9 -> ok (compacted downstream)
    assert img_ref_problems(_vslots(None, x, None, None, None, x, None, None, x), 'ref-img') == []
    # 6 pixel anywhere -> count-based rejection; 👁 on one of them fixes it
    six = (x, None, x, x, None, x, None, x, None, x)
    assert img_ref_problems(_vslots(*six), 'ref-img') == [
        '6 🖼 pixel images (max 5) — switch some to 👁 or empty them'
    ]
    assert img_ref_problems(_vslots(*six, vision=(10,)), 'ref-img') == []
    # 👁 slots are uncapped
    assert img_ref_problems(_vslots(x, *[x] * 9, vision=range(2, 11)), 'ref-img') == []
    # vision-only -> still rejected
    assert img_ref_problems(_vslots(None, None, None, None, None, x, vision=(6,)), 'ref-img') == [
        'needs at least one 🖼 pixel image (all filled slots are 👁)'
    ]
    # non-image in a pixel slot (any position) -> rejected; 👁 video ok, 👁 audio is pixel
    assert img_ref_problems(_vslots(x, *[None] * 6, '/c.mp4'), 'ref-img') == [
        'slot 8 is video (🖼 images only)'
    ]
    assert img_ref_problems(_vslots(x, '/c.mp4', vision=(2,)), 'ref-img') == []
    assert img_ref_problems(_vslots(x, '/v.wav', vision=(2,)), 'ref-img') == [
        'slot 2 is audio (🖼 images only)'
    ]


def test_vision_parse_roundtrip():
    from aidb.app.tab_refdef import parse_payload, refdef_payload

    p = refdef_payload(_vslots('/a/x.png', '/a/y.png', vision=(2,)), 'ref', 'hint', '')
    st = parse_payload(json.dumps(p))
    assert st['slots'][1].get('vision') is True and not st['slots'][0].get('vision')


# -- t191: clip refs under pre-/post-vid + inherited budget; t190 tab pins -- #
def _cslots(*specs):
    """Slots from ``url`` or ``(url, role)`` specs."""
    return [
        {'url': s, 'id': None, 'role': ''}
        if isinstance(s, str)
        else {'url': s[0], 'id': None, 'role': s[1]}
        for s in specs
    ]


def test_continue_allows_clips():
    from aidb.app.tab_refdef import continue_problems

    for verb in ('post-vid', 'pre-vid'):
        assert continue_problems(_cslots('/a.mkv', '/cut.mp4', '/p.png', '/v.mov'), verb) == []
        assert continue_problems(_cslots('/a.png', '/cut.mp4'), verb) == [
            'slot 1 needs the anchor clip (video)'
        ]
    assert continue_problems(_cslots('/a.png'), 'ref') == []


def test_budget_continue_anchor_and_inherit():
    from aidb.app.tab_refdef import ref_budget_problems

    # the anchor is pinned frames, not a ref: anchor + 2 new clips is within the cap
    assert ref_budget_problems(_cslots('/a.mkv', '/v1.mp4', '/v2.mp4'), 'post-vid') == []
    # ... but under ref slot 1 is an ordinary clip ref
    assert ref_budget_problems(_cslots('/a.mkv', '/v1.mp4', '/v2.mp4'), 'ref') == [
        'max 2 clips, got 3'
    ]
    inh = [
        {'n': 1, 'kind': 'video', 'url': '/r/c1.mov', 'use': True},
        {'n': 2, 'kind': 'video', 'url': '/r/c2.mov', 'use': True},
        {'n': 3, 'kind': 'image', 'url': '/r/man.png', 'use': True},
    ]
    slots = _cslots('/a.mkv', '/v1.mp4')
    for verb in ('post-vid', 'pre-vid'):
        assert ref_budget_problems(slots, verb, inh) == ['max 2 clips, got 3']
        assert ref_budget_problems(slots, verb) == []  # no carry → slots only
    # a switched-off carried ref frees its place
    inh_off = [dict(inh[0], use=False), *inh[1:]]
    assert ref_budget_problems(slots, 'post-vid', inh_off) == []
    # the same file carried and in a slot counts once (t191 D; path normalised)
    assert ref_budget_problems(_cslots('/a.mkv', '/r/./c1.mov'), 'post-vid', inh) == []
    # every kind counts: 2 carried audio + 1 new = 3
    aud = [{'kind': 'audio', 'url': f'/r/a{i}.wav', 'use': True} for i in (1, 2)]
    assert ref_budget_problems(_cslots('/a.mkv', '/n.wav'), 'post-vid', aud) == [
        'max 2 audios, got 3'
    ]
    # a carried clip's soundtrack (audio: true) counts in the total
    pics = [f'/p{i}.png' for i in range(1, 7)]
    full = _cslots('/a.mkv', *pics, '/a1.wav', '/a2.wav')
    clips = [{'kind': 'video', 'url': f'/r/c{i}.mov', 'use': True, 'audio': True} for i in (1, 2)]
    assert ref_budget_problems(full, 'post-vid', clips) == []  # 6 + 2 + 2 + 2 = 12
    full.append({'url': '/r/c3.mov', 'id': None, 'role': ''})
    assert ref_budget_problems(full, 'post-vid', clips[:1] + [dict(clips[1], url='/r/x.mov')]) == [
        'max 2 clips, got 3',
        'max 12 refs in total (soundtracks counted), got 13',  # 6 + 2 + 3 + 2
    ]
    # inherit is ignored outside pre-/post-vid
    assert ref_budget_problems(_cslots('/v1.mp4'), 'ref', inh) == []


def test_inherit_list_soundtrack():
    from aidb.app.tab_refdef import inherit_list

    carry = {
        'anchor': '/c/a.mkv',
        'refs': [{'kind': 'video', 'vid': 1, 'url': '/r/c.mov', 'audio': True}, {'kind': 'image'}],
        'on': [True, True],
    }
    inh = inherit_list(carry, '/c/a.mkv')
    assert inh[0]['audio'] is True and 'audio' not in inh[1]


def test_pins_outside_budget_and_conflicts():
    from aidb.app.tab_refdef import pin_of, pin_problems, ref_budget_problems

    s = _cslots(
        ('/p.png', 'Last frame to land on'), ('/q.png', '  first_frame'), ('/v.mp4', 'last frame')
    )
    assert [pin_of(x, 'ref') for x in s] == ['last', 'first', None]  # video: no pin
    assert pin_of(s[0], 'enh') is None  # other verbs: ordinary role text
    assert pin_of({'url': '/p.png', 'role': 'the last frame'}, 'ref') is None  # starts-with only
    pics = [f'/p{i}.png' for i in range(1, 7)]
    # 6 pictures + a pinned 7th still fits
    assert ref_budget_problems(_cslots(*pics, ('/p7.png', 'last frame')), 'ref') == []
    assert ref_budget_problems(_cslots(*pics, '/p7.png'), 'ref') == ['max 6 pictures, got 7']
    # conflicts: first + post-vid, last + pre-vid; the other pairs are fine
    assert pin_problems(_cslots('/a.mkv', ('/p.png', 'first frame')), 'post-vid') == [
        "slot 2 pins the first frame — post-vid already pins the anchor's tail at frame 0"
    ]
    assert pin_problems(_cslots('/a.mkv', ('/p.png', 'last frame x')), 'pre-vid') == [
        "slot 2 pins the last frame — pre-vid already pins the anchor's head at the end"
    ]
    assert pin_problems(_cslots('/a.mkv', ('/p.png', 'last frame')), 'post-vid') == []
    assert pin_problems(_cslots('/a.mkv', ('/p.png', 'first frame')), 'pre-vid') == []
    assert pin_problems(_cslots(('/p.png', 'first frame')), 'ref') == []


def test_continue_deploy_counts_carry(monkeypatch):
    """deploy (t191): inherit is built ahead of the guards, so a carried clip
    pair + a new clip is refused with the budget toast, nothing deployed."""
    from pathlib import Path

    from aidb.app import tab_refdef

    toasts, clip = [], {}
    for kind in ('Warning', 'Info', 'Success'):
        monkeypatch.setattr(
            tab_refdef.gr, kind, lambda m, duration=None, k=kind: toasts.append((k, m))
        )
    monkeypatch.setattr(tab_refdef, 'anchor_master', lambda u: Path(u))
    monkeypatch.setattr(tab_refdef, 'clip_copy', lambda t: clip.update(v=t))
    monkeypatch.setattr(tab_refdef, 'trigger_enhancer', lambda: 'triggered')
    tab = tab_refdef.RefdefTab.__new__(tab_refdef.RefdefTab)
    slots = _cslots('/c/a.mkv', ('/n/cut.mp4', 'cut to this'))
    monkeypatch.setattr(tab, '_slots_from_ui', lambda *a: [dict(s) for s in slots])
    monkeypatch.setattr(tab, '_is_enh', lambda st: False)
    carry = {
        'anchor': '/c/a.mkv',
        'refs': [{'kind': 'video', 'vid': i, 'url': f'/r/c{i}.mov'} for i in (1, 2)],
        'on': [True, True],
    }
    msg = tab._on_deploy(None, 'post-vid', 'hint', False, '', [], [], carry)
    assert msg == 'NOT deployed: `post-vid` — max 2 clips, got 3' and 'v' not in clip
    assert toasts == [('Warning', 'post-vid: max 2 clips, got 3')]
    carry['on'] = [False, True]  # 🚫 one carried clip → deploys
    toasts.clear()
    msg = tab._on_deploy(None, 'post-vid', 'hint', False, '', [], [], carry)
    assert msg.startswith('deployed instruction `post-vid`') and 'inherit 1/2' in msg
    p = json.loads(clip['v'])
    assert [r['media'] for r in p['refs'][:2]] == ['video', 'video']
    assert p['continue']['dir'] == 'post' and len(p['inherit']) == 2
