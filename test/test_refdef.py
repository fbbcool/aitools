import json

from aidb.app.tab_refdef import (
    EDITED_BY,
    SCHEMA_REFDEF,
    parse_payload,
    patch_iteration,
    refdef_payload,
)


def _iteration(**extra) -> dict:
    return {
        'schema_id': '1xlasm_enhancer.iteration.v6.4',
        'scene_id': 'abc',
        'url': '/x/0rig___a.png',
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


def test_parse_iteration_uses_current_entry():
    st = parse_payload(json.dumps(_iteration()))
    assert st is not None and st['kind'] == 'iteration'
    assert st['idx'] == 1 and st['text'] == 'p1'
    assert st['slots'][0]['url'] == '/x/0rig___a.png'
    assert st['slots'][1]['url'] is None and st['slots'][2]['url'] is None


def test_parse_iteration_vid_refs_fill_slots_2_3():
    p = _iteration(prompts_vid={'refs': {'first': {'url': '/f.png', 'at': 0.0}, 'last': None}})
    st = parse_payload(json.dumps(p))
    assert st is not None
    assert st['slots'][1]['url'] == '/f.png' and st['slots'][2]['url'] is None


def test_parse_iteration_roles_from_media_desc():
    p = _iteration(
        url_desc='main img',
        prompts_vid={'refs': {'first': {'url': '/f.png', 'desc': 'dress'}, 'last': None}},
    )
    st = parse_payload(json.dumps(p))
    assert st is not None
    assert [s['role'] for s in st['slots']] == ['main img', 'dress', '']


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


def test_patch_unchanged_is_verbatim():
    p = _iteration()
    out, changed, skipped = patch_iteration(p, ['/x/0rig___a.png', None, None])
    assert changed == [] and skipped == []
    assert out == p


def test_patch_url_keeps_everything_else():
    p = _iteration()
    out, changed, _ = patch_iteration(p, ['/y.png', None, None])
    assert changed == ['url']
    assert out['prompts'] == p['prompts']
    assert out['url'] == '/y.png'
    assert out['edited_by'] == EDITED_BY
    assert out['unknown_future_field'] == {'keep': True}
    assert out['schema_id'] == p['schema_id']
    # input untouched
    assert p['url'] == '/x/0rig___a.png' and 'edited_by' not in p


def test_patch_vid_refs():
    p = _iteration(prompts_vid={'refs': {'first': {'url': '/f.png', 'at': 0.0}, 'last': None}})
    out, changed, _ = patch_iteration(p, ['/x/0rig___a.png', '/g.png', '/l.png'])
    assert changed == ['prompts_vid.refs.first', 'prompts_vid.refs.last']
    assert out['prompts_vid']['refs']['first'] == {'url': '/g.png', 'at': 0.0}
    assert out['prompts_vid']['refs']['last'] == {'url': '/l.png'}


def test_patch_slot_without_vid_refs_is_skipped():
    out, changed, skipped = patch_iteration(_iteration(), ['/x/0rig___a.png', '/g.png', None])
    assert changed == [] and len(skipped) == 1
    assert 'prompts_vid' not in out and 'edited_by' not in out


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
