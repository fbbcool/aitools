"""review_imgs lists (board task 102) — validation + manager round trip on the test DB."""

import pytest

from aidb.review_imgs import ReviewImgs, is_answered, validate

LIST_ID = 'pytest-review-imgs'


def _doc(**over) -> dict:
    doc = {
        'schema_id': 'aitools.review_imgs.v1',
        'list_id': LIST_ID,
        'title': 'pytest list',
        'form': [
            {'key': 'accept', 'type': 'choice', 'options': ['accept', 'reject']},
            {'key': 'why', 'type': 'multi', 'options': ['head', 'ratio']},
            {'key': 'ok', 'type': 'bool'},
            {'key': 'note', 'type': 'text'},
        ],
        'items': [
            {'id': 'a', 'url': '/nonexistent/a.png', 'context': 'ctx a'},
            {'id': 'b', 'url': '/nonexistent/b.png'},
        ],
    }
    doc.update(over)
    return doc


def test_validate_ok():
    assert validate(_doc()) == []


@pytest.mark.parametrize(
    'over',
    [
        {'list_id': 'bad id'},
        {'form': [{'key': 'x', 'type': 'choice'}]},
        {'form': [{'key': 'x', 'type': 'slider'}]},
        {'items': []},
        {'items': [{'id': 'a', 'url': '/x.png'}, {'id': 'a', 'url': '/y.png'}]},
        {'schema_id': 'other.v1'},
    ],
)
def test_validate_rejects(over):
    assert validate(_doc(**over))


def test_is_answered():
    assert not is_answered(None)
    assert not is_answered({'accept': None, 'why': [], 'note': ''})
    assert is_answered({'ok': False})


@pytest.fixture
def rv():
    rv = ReviewImgs(config='test', verbose=0)
    rv.delete(LIST_ID)
    yield rv
    rv.delete(LIST_ID)


def test_roundtrip(rv):
    doc = rv.create(_doc())
    assert doc['show_context'] is False and doc['comment'] is None
    assert doc['items'][0]['response'] is None
    with pytest.raises(ValueError):
        rv.create(_doc())
    rv.create(_doc(), replace=True)

    resp = {'accept': 'reject', 'why': ['head'], 'ok': False, 'note': 'n'}
    assert rv.set_response(LIST_ID, 0, 'a', resp)
    assert not rv.set_response(LIST_ID, 0, 'b', resp)  # id guard
    assert not rv.set_response(LIST_ID, 1, 'b', {'accept': 'maybe'})  # invalid option
    assert rv.set_comment(LIST_ID, 'hello')

    got = rv.get(LIST_ID)
    assert got['items'][0]['response'] == resp
    assert got['items'][1]['response'] is None
    assert got['comment'] == 'hello'
    summary = next(d for d in rv.ls() if d['list_id'] == LIST_ID)
    assert (summary['answered'], summary['total']) == (1, 2)

    assert rv.delete(LIST_ID)
    assert rv.get(LIST_ID) is None
