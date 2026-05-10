"""Tests for the skin build phase.

Cover: deterministic composition, source-edit hash invalidation, schema
rejection of malformed sources.
"""
import json
import os
import re
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import ValidationError

from ait.caption.skin import _compute_source_hash, SkinRegistry
from ait.caption.skin_build import compose_built


REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module', autouse=True)
def _set_conf_ait():
    os.environ['CONF_AIT'] = str(REPO / 'conf')
    yield


@pytest.fixture(scope='module')
def source() -> dict:
    with open(REPO / 'conf' / 'skins' / '1xlasm.json') as f:
        data = json.load(f)
    # strip _built so we test composition from source only
    data.pop('_built', None)
    return data


# --- compose_built basics ---


def test_compose_built_keys(source):
    built = compose_built(source)
    assert set(built) >= {
        'version', 'built_at', 'source_hash',
        'directive', 'labels', 'label_to_group', 'label_to_entity', 'forbidden',
    }


def test_compose_built_label_count(source):
    built = compose_built(source)
    # primary: 5 attribute + 7 pose + 6 action = 18
    # secondary: 2 attribute + 7 pose + 2 action = 11
    # interaction: 11 touch + 16 insertion + 1 act = 28
    # total = 57
    assert len(built['labels']) == 57


def test_compose_built_interpolation(source):
    built = compose_built(source)
    assert '{entities.primary.phrase}' not in built['directive']
    assert '{entities.secondary.phrase}' not in built['directive']
    for label, prompt in built['labels'].items():
        assert '{entities.' not in prompt, f'placeholder leaked into label {label!r}'
    # but {hint} should NOT be in any built field — it lives only in user_hint_preamble (a source field)
    assert '{hint}' not in built['directive']


def test_label_to_group_reverse_index(source):
    built = compose_built(source)
    assert built['label_to_group']['primary.attribute.muscular'] == 'primary.attribute'
    assert built['label_to_group']['primary.pose.front']         == 'primary.pose'
    assert built['label_to_group']['secondary.pose.front']       == 'secondary.pose'
    assert built['label_to_group']['interaction.insertion.breasts_body'] == 'interaction.insertion'
    assert built['label_to_group']['interaction.touch.ass']      == 'interaction.touch'


def test_label_to_entity_reverse_index(source):
    built = compose_built(source)
    assert built['label_to_entity']['primary.attribute.muscular'] == 'primary'
    assert built['label_to_entity']['primary.pose.front']         == 'primary'
    assert built['label_to_entity']['secondary.pose.front']       == 'secondary'
    assert built['label_to_entity']['interaction.insertion.breasts_body'] == 'interaction'


def test_path_keyed_allows_same_leaf_across_groups(source):
    """primary.pose.front and secondary.pose.front coexist in path-keyed labels."""
    built = compose_built(source)
    assert 'primary.pose.front' in built['labels']
    assert 'secondary.pose.front' in built['labels']
    assert built['labels']['primary.pose.front'] != built['labels']['secondary.pose.front']


def test_forbidden_union_dedupes(source):
    built = compose_built(source)
    forbidden = built['forbidden']
    assert len(forbidden) == len(set(forbidden))   # deduplicated
    # words from each entity present:
    assert 'giantess' in forbidden
    assert 'tiny' in forbidden
    assert 'figurine' in forbidden


# --- determinism + hash invalidation ---


def test_compose_is_deterministic(source):
    """Same source -> identical built output, modulo built_at."""
    a = compose_built(source)
    b = compose_built(source)
    a_strip = {k: v for k, v in a.items() if k != 'built_at'}
    b_strip = {k: v for k, v in b.items() if k != 'built_at'}
    assert a_strip == b_strip


def test_source_edit_changes_hash(source):
    """Mutating any source field changes source_hash."""
    h0 = _compute_source_hash(source)
    s = deepcopy(source)
    s['entities']['primary']['rules'] = list(s['entities']['primary']['rules']) + ['X']
    h1 = _compute_source_hash(s)
    assert h0 != h1


def test_built_block_ignored_in_hash(source):
    """Adding a _built block doesn't change source_hash (so a stale build doesn't
    fool the loader)."""
    s = deepcopy(source)
    h0 = _compute_source_hash(s)
    s['_built'] = {'foo': 'bar'}
    h1 = _compute_source_hash(s)
    assert h0 == h1


# --- in-memory fallback ---


def test_loader_recomposes_when_built_missing(tmp_path, source):
    """If _built is absent in the JSON, the loader composes in-memory and the
    resulting Skin has fully-populated derived fields."""
    out = tmp_path / '1xlasm.json'
    s = deepcopy(source)
    s.pop('_built', None)
    out.write_text(json.dumps(s))
    seen_msgs: list[str] = []
    reg = SkinRegistry(srcdir=tmp_path, log=lambda m: seen_msgs.append(m))
    skin = reg.get('1xlasm')
    assert skin.directive
    assert len(skin.labels) == 57
    # warning message emitted
    assert any('skin_build' in m for m in seen_msgs)


def test_loader_recomposes_when_built_stale(tmp_path, source):
    """If _built carries a stale source_hash, the loader uses an in-memory
    rebuild."""
    out = tmp_path / '1xlasm.json'
    s = deepcopy(source)
    s['_built'] = {
        'version': 1,
        'built_at': '2000-01-01T00:00:00+00:00',
        'source_hash': 'sha256:wrong',
        'directive': 'STALE',
        'labels': {},
        'label_to_group': {},
        'label_to_entity': {},
        'forbidden': [],
    }
    out.write_text(json.dumps(s))
    seen_msgs: list[str] = []
    reg = SkinRegistry(srcdir=tmp_path, log=lambda m: seen_msgs.append(m))
    skin = reg.get('1xlasm')
    assert skin.directive != 'STALE'
    assert len(skin.labels) == 57
    assert any('stale' in m or 'skin_build' in m for m in seen_msgs)


# --- schema rejections ---


def _validate_via_loader(tmp_path, data):
    out = tmp_path / f'{data["name"]}.json'
    out.write_text(json.dumps(data))
    reg = SkinRegistry(srcdir=tmp_path)
    return reg.get(data['name'])


def test_rejects_missing_required(tmp_path, source):
    s = deepcopy(source)
    s.pop('default_prompt')
    with pytest.raises(ValidationError):
        _validate_via_loader(tmp_path, s)


def test_rejects_secondary_with_no_interaction_consistency(tmp_path, source):
    s = deepcopy(source)
    s['entities']['secondary'] = None
    # interaction still set -> should raise on cross-field validation
    with pytest.raises(ValueError, match='interaction'):
        _validate_via_loader(tmp_path, s)


def test_rejects_duplicate_label_paths_within_group(tmp_path, source):
    """Same leaf name in the same group is rejected at parse time."""
    s = deepcopy(source)
    s['entities']['primary']['label_groups']['attribute']['labels'].append(
        {'name': 'muscular', 'description': '', 'expansion': 'dup'}
    )
    with pytest.raises(ValueError, match='duplicate label name'):
        _validate_via_loader(tmp_path, s)


def test_allows_same_leaf_in_different_groups(tmp_path, source):
    """Cross-group duplication is fine — paths disambiguate."""
    s = deepcopy(source)
    # `front` already exists in primary.pose AND secondary.pose; loading must succeed.
    skin = _validate_via_loader(tmp_path, s)
    assert 'primary.pose.front' in skin.labels
    assert 'secondary.pose.front' in skin.labels


def test_rejects_name_filename_mismatch(tmp_path, source):
    s = deepcopy(source)
    s['name'] = 'wrong_name'
    out = tmp_path / '1xlasm.json'
    out.write_text(json.dumps(s))
    reg = SkinRegistry(srcdir=tmp_path)
    with pytest.raises(ValueError, match='filename stem'):
        reg.get('1xlasm')
