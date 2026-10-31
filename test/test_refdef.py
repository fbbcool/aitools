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
    assert [s['url'] for s in st['slots']] == ['/c/src.png', '/c/face.png', None]
    assert [s['role'] for s in st['slots']] == ['main', 'new face', '']
    assert st['text'] == 'Replace the face with the face in image 2'


def test_stale_section_falls_back_to_main():
    p = _iteration(prompts_inp=_inp(from_rev=1))  # a later steer moved rev on
    assert default_view(p) == 'main'
    assert available_views(p) == ['main', 'inp']


def test_with_view_switches_slots_and_text():
    st = parse_payload(json.dumps(_iteration(prompts_inp=_inp(), prompts_vid=_vid())))
    assert st is not None and st['view'] == 'inp'
    vid = with_view(st, 'vid')
    assert [s['url'] for s in vid['slots']] == ['/f.png', None, None]
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


def test_update_iteration_uses_given_view_else_default():
    p = _iteration(prompts_inp=_inp())
    text = json.dumps(p)
    out, view, changed, _ = update_payload(text, [_slot(), _slot('/c/new.png'), _slot()])
    assert view == default_view(p) == 'inp'
    assert changed == ['prompts_inp.refs[0]']
    out, view, changed, _ = update_payload(text, [_slot('/m.png'), _slot(), _slot()], 'main')
    assert view == 'main' and changed == ['url']
    _, view, _, _ = update_payload(text, [_slot()] * 3, 'vid')  # absent view → default
    assert view == 'inp'


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
    assert out['refs'][0] == {'slot': 1, 'url': '/b.png', 'id': 'i2', 'role': 'main img'}
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
    out, view, changed, skipped = update_payload(json.dumps(p), slots)
    assert view == 'inp' and changed == ['prompts_inp.refs[0]'] and skipped == []
    # tab view main, slot 2 filled → still inp
    _, view, _, _ = update_payload(json.dumps(p), slots, 'main')
    assert view == 'inp'


def test_update_reports_skips_when_no_view_fits():
    p = _iteration()  # main only
    out, view, changed, skipped = update_payload(
        json.dumps(p), [_slot(), _slot('/c/new.png'), _slot()]
    )
    assert view == 'main' and changed == [] and skipped
