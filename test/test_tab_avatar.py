"""Pure helpers of the scene app avatar tab (board FEATURE t218)."""

import json

import pytest

from aidb.app.tab_avatar import (
    deploy_text,
    fields_from_ui,
    moved,
    parse_json,
    parse_list,
    selected_in_order,
    ui_fields,
)
from aidb.avatar import AvatarError

AV = {
    'name': 'x',
    'display_name': 'X',
    'triggers': ['xa', 'xb'],
    'tags': ['f'],
    'loras': [{'trigger': 'xa'}],
    'prompt_guides': [],
    'extra': {'k': 1},
    'media': [
        {'mid': 'm1', 'url': '/a.png'},
        {'mid': 'm2', 'url': '/b.mp4'},
        {'mid': 'm3', 'url': '/c.wav'},
    ],
}


def test_parse_list():
    assert parse_list(' a, b\nc,, a ') == ['a', 'b', 'c']
    assert parse_list(None) == []


def test_parse_json():
    assert parse_json('', 'x', list) == []
    assert parse_json('{"a": 1}', 'x', dict) == {'a': 1}
    with pytest.raises(AvatarError):
        parse_json('{', 'x', dict)
    with pytest.raises(AvatarError):
        parse_json('[]', 'x', dict)


def test_ui_roundtrip():
    f = fields_from_ui(*ui_fields(AV))
    assert f['triggers'] == ['xa', 'xb'] and f['tags'] == ['f']
    assert f['loras'] == AV['loras'] and f['extra'] == {'k': 1}
    assert ui_fields(None)[4] == '[]'


def test_deploy_text_avatar_order():
    assert selected_in_order(AV, ['m3', 'gone', 'm1']) == ['m1', 'm3']
    assert deploy_text(AV, ['m3', 'm1']) == '/a.png\n/c.wav'
    assert deploy_text(AV, []) == ''


def test_moved():
    assert moved(['a', 'b', 'c'], 'b', -1) == ['b', 'a', 'c']
    assert moved(['a', 'b', 'c'], 'c', 1) == ['a', 'b', 'c']
    assert moved(['a', 'b'], 'z', 1) == ['a', 'b']


class _FakeAM:
    def list(self):
        return []

    def media(self, name, mid):
        return None


def _tab():
    from aidb.app.tab_avatar import AvatarTab

    t = AvatarTab.__new__(AvatarTab)
    t._am = _FakeAM()
    t._refdef = None
    t._verbose = 0
    t._thumbs = {}
    return t


def test_every_button_has_a_tip():
    """Every gr.Button of the tab and of a media-grid cell carries a known tooltip
    class, and the head script ships the TIPS map (t218 follow-up)."""
    import gradio as gr

    from aidb.app.tab_avatar import AVATAR_HEAD, INNER_TIPS, TIPS

    t = _tab()
    with gr.Blocks() as demo:
        t.build()
        sel, rev, status = gr.State([]), gr.State(0), gr.Markdown()
        m = {'mid': 'm1', 'kind': 'image', 'url': '/nope/a.png', 'role': ''}
        with gr.Row():
            t._cell('x', m, ['m1'], [], sel, rev, status)
    buttons = [b for b in demo.blocks.values() if isinstance(b, gr.Button)]
    assert len(buttons) == 10
    used = set()
    for b in buttons:
        keys = [c.removeprefix('av-tip-') for c in b.elem_classes or [] if c != 'av-tip']
        assert len(keys) == 1 and keys[0] in TIPS and TIPS[keys[0]], b.value
        used.add(keys[0])
    assert used == set(TIPS)  # no tip without a button
    for text in TIPS.values():
        assert json.dumps(text, ensure_ascii=False)[1:-1] in AVATAR_HEAD
    # components with built-in (gradio) buttons carry an inner-tip class
    inner = [b for b in demo.blocks.values() if isinstance(b, (gr.Code, gr.Image))]
    assert len(inner) == 4  # 3 JSON editors + 1 cell preview
    for b in inner:
        keys = [c.removeprefix('av-tipin-') for c in b.elem_classes or []]
        assert len(keys) == 1 and keys[0] in INNER_TIPS, b.label
    for tips in INNER_TIPS.values():
        for text in tips:
            assert json.dumps(text, ensure_ascii=False)[1:-1] in AVATAR_HEAD
