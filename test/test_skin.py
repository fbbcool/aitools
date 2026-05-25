"""Tests for the Skin loader.

Structural checks of the rebuilt 1xlasm skin: label paths, forbidden vocab,
body-type rules, validators, concept matching, render order, and the
compute_labels_ng legacy → path migration helper. (The byte-equality tests
that asserted parity with the deleted `xlasm.py` constants were retired
after the legacy module was removed.)
"""
import os
from pathlib import Path

import pytest

from ait.caption.skin import Skin, SkinRegistry, _compute_source_hash


REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module', autouse=True)
def _set_conf_ait():
    os.environ['CONF_AIT'] = str(REPO / 'conf')
    yield


@pytest.fixture(scope='module')
def skin() -> Skin:
    return SkinRegistry().get('1xlasm')


# Skin labels are now keyed by the structured PATH (`primary.attribute.muscular`)
# rather than the bare leaf. This map covers every legacy joy.LABEL_PROMPT key
# (minus `heap`/`none`) and gives the path it now lives at — covering both
# the `b_*` body-attribute renames and the `woman_*`/`man_*` pose renames.
# The on-body `sitting` variant is now `secondary.pose.perched`.
LEGACY_NAME_TO_PATH: dict[str, str] = {
    # body attributes
    'b_muscular': 'primary.attribute.muscular',
    'b_busty':    'primary.attribute.busty',
    'b_slim':     'primary.attribute.slim',
    'b_curvy':    'primary.attribute.curvy',
    'b_hairy':    'primary.attribute.hairy',
    # primary poses
    'all4':          'primary.pose.all4',
    'tower':         'primary.pose.tower',
    'woman_front':   'primary.pose.front',
    'woman_back':    'primary.pose.back',
    'woman_side':    'primary.pose.side',
    'woman_sitting': 'primary.pose.sitting',
    'woman_on_back': 'primary.pose.on_back',
    # primary actions
    'step':       'primary.action.step',
    'holding':    'primary.action.holding',
    'blowjob':    'primary.action.blowjob',
    'handjob':    'primary.action.handjob',
    'teasing_hj': 'primary.action.teasing_hj',
    'job':        'primary.action.job',
    # secondary attributes
    'penis':    'secondary.attribute.penis',
    # secondary poses
    'man_front':   'secondary.pose.front',
    'man_back':    'secondary.pose.back',
    'man_side':    'secondary.pose.side',
    'man_sitting': 'secondary.pose.sitting',
    'man_on_back': 'secondary.pose.on_back',
    'hanging':     'secondary.pose.hanging',
    'sitting':     'secondary.pose.perched',  # on-body-part variant
    # secondary actions
    'masturbating': 'secondary.action.masturbating',
    'cum':          'secondary.action.cum',
    # interaction.touch
    'ass':    'interaction.touch.ass',
    'body':   'interaction.touch.body',
    'breast': 'interaction.touch.breast',
    'face':   'interaction.touch.face',
    'foot':   'interaction.touch.foot',
    'hand':   'interaction.touch.hand',
    'leg':    'interaction.touch.leg',
    'mouth':  'interaction.touch.mouth',
    'pussy':  'interaction.touch.pussy',
    'thigh':  'interaction.touch.thigh',
    'tongue': 'interaction.touch.tongue',
    # interaction.insertion (i_ prefix dropped on i_*_* labels)
    'insert':         'interaction.insertion.insert',
    'panties':        'interaction.insertion.panties',
    'i_breasts_body': 'interaction.insertion.breasts_body',
    'i_breasts_head': 'interaction.insertion.breasts_head',
    'i_breasts_low':  'interaction.insertion.breasts_low',
    'i_breasts_up':   'interaction.insertion.breasts_up',
    'i_vagina_low':   'interaction.insertion.vagina_low',
    'i_vagina_up':    'interaction.insertion.vagina_up',
    'i_vagina_head':  'interaction.insertion.vagina_head',
    'i_ass_low':      'interaction.insertion.ass_low',
    'i_ass_up':       'interaction.insertion.ass_up',
    'i_ass_head':     'interaction.insertion.ass_head',
    'i_mouth_body':   'interaction.insertion.mouth_body',
    'i_mouth_head':   'interaction.insertion.mouth_head',
    'i_mouth_low':    'interaction.insertion.mouth_low',
    'i_mouth_up':     'interaction.insertion.mouth_up',
    # interaction.act
    'sex': 'interaction.act.sex',
}


# Paths that exist only in the new schema (no legacy entry).
# Listed separately so the no-extras test stays an explicit allow-list rather
# than a permissive “anything goes” check.
NEW_PATHS_NOT_IN_LEGACY: set[str] = {
    # poses (added in two batches: standing, kneeling/arms_spread/legs_spread,
    # then lying / lifted)
    'primary.pose.standing',
    'primary.pose.kneeling',
    'primary.pose.arms_spread',
    'primary.pose.legs_spread',
    'primary.pose.lying',
    'secondary.pose.standing',
    'secondary.pose.kneeling',
    'secondary.pose.arms_spread',
    'secondary.pose.legs_spread',
    'secondary.pose.lifted',
    'secondary.pose.lying',
    # body-attribute extensions (curated via the editor)
    'primary.attribute.bigass',
    'primary.attribute.leggy',
    # interaction.act gaze labels
    'interaction.act.he_look_at_her',
    'interaction.act.look_at_each',
    'interaction.act.she_look_at_him',
    'interaction.act.she_look_at_penis',
    # interaction.proximity group (added after the legacy schema)
    'interaction.proximity.ass',
    'interaction.proximity.breasts',
    'interaction.proximity.face',
    'interaction.proximity.mouth',
    'interaction.proximity.thighs',
    'interaction.proximity.vagina',
}


# --- meta ---


def test_skin_loads(skin):
    assert skin.name == '1xlasm'
    assert skin.entities_primary.phrase == 'xlgts woman'
    assert skin.entities_primary.token == 'xlgts'
    assert skin.entities_secondary is not None
    assert skin.entities_secondary.phrase == 'xlasm man'
    assert skin.interaction is not None
    assert skin.require_trigger_presence is True


def test_default_set(skin):
    assert skin.default_set == 'gts_v3'


# --- label coverage (every legacy path resolves to a populated label) ---


def test_label_paths_present(skin):
    """Every legacy-name → path mapping resolves to a populated entry in
    skin.labels. Catches schema/path-rename regressions without depending on
    the deleted xlasm.LABEL_PROMPT constants."""
    for legacy_name, path in LEGACY_NAME_TO_PATH.items():
        assert path in skin.labels, f'missing path: {path} (legacy: {legacy_name})'
        assert skin.labels[path].strip(), f'empty expansion for {path}'


def test_no_extra_labels(skin):
    expected = set(LEGACY_NAME_TO_PATH.values()) | NEW_PATHS_NOT_IN_LEGACY
    extras = set(skin.labels) - expected
    assert not extras


def test_forbidden_covers_known_words(skin):
    """The legacy 1xlasm forbidden list collapsed to set semantics — we now
    only assert that the load-bearing vocabulary is present (specific words
    the captioner is known to slip; matches the original test_caption_violations
    fixture data below)."""
    forbidden_lower = {w.lower() for w in skin.forbidden}
    for term in ('tiny', 'figurine', 'giantess', 'doll', 'enormous',
                 'towering', 'child'):
        assert term in forbidden_lower, f'expected forbidden word missing: {term!r}'


def test_body_type_words_shape(skin):
    """The four body-type leaves each have their authorizing word list."""
    expected_leaves = {'muscular', 'busty', 'slim', 'curvy'}
    assert set(skin.body_type_words.keys()) >= expected_leaves
    for leaf in expected_leaves:
        words = skin.body_type_words[leaf]
        assert isinstance(words, tuple)
        assert len(words) >= 1, f'body_type_words[{leaf!r}] is empty'
        # leaf-name itself should be one of the authorized words
        assert leaf in {w.lower() for w in words}


def test_user_hint_preamble_format_slot(skin):
    """The preamble must contain a `{hint}` slot so compile_user_prompt
    can interpolate per-image hints."""
    assert '{hint}' in skin.user_hint_preamble


# --- validators (structural assertions on fixture text) ---


CLEAN = (
    'The xlgts woman holds the xlasm man at her hip level. '
    'She wraps her hand around him and squeezes his torso.'
)
CONTAINS_FORBIDDEN = (
    'The xlgts woman holds a tiny figurine of the xlasm man. '
    'She is a giantess.'
)
WITH_BODY_TYPE = (
    'The xlgts woman has busty large breasts and a muscular bodybuilder physique.'
)
MISSING_TRIGGER_MAN = 'The xlgts woman holds him in her hand.'


def test_caption_violations_clean(skin):
    assert skin.caption_violations(CLEAN) == []


def test_caption_violations_dirty(skin):
    violations = sorted(skin.caption_violations(CONTAINS_FORBIDDEN))
    assert 'tiny' in violations
    assert 'figurine' in violations
    assert 'giantess' in violations


def test_body_type_warnings_unauthorized(skin):
    """Body-type words appearing without their authorizing label → warnings."""
    warnings = skin.body_type_warnings(WITH_BODY_TYPE, applied_labels=[])
    assert warnings, 'expected at least one warning (busty/muscular without label)'
    joined = ' '.join(warnings).lower()
    assert 'busty' in joined or 'muscular' in joined


def test_body_type_warnings_authorized(skin):
    """Same body-type text, but with authorizing labels → no warnings."""
    warnings = skin.body_type_warnings(WITH_BODY_TYPE, applied_labels=['busty', 'muscular'])
    assert warnings == []


def test_missing_triggers_clean(skin):
    assert skin.missing_triggers(CLEAN) == []


def test_missing_triggers_missing_man(skin):
    missing = skin.missing_triggers(MISSING_TRIGGER_MAN)
    assert missing  # non-empty: 'xlasm man' is absent
    joined = ' '.join(missing).lower()
    assert 'xlasm' in joined


# --- concept matching ---


def test_concept_matches_insertion(skin):
    matched = skin.matched_concepts(['interaction.insertion.breasts_body', 'secondary.pose.front'])
    assert matched['insertion'] is True
    assert matched['holding'] is False
    assert matched['general'] is False  # themed match present


def test_concept_matches_residual(skin):
    matched = skin.matched_concepts(['man_front'])
    assert matched['insertion'] is False
    assert matched['general'] is True
    # body-attribute label alone -> residual disabled by ignore_labels
    matched_b = skin.matched_concepts(['busty'])
    assert matched_b['general'] is False


def test_concept_subconcepts(skin):
    insertion = skin.concepts['insertion']
    assert 'breasts' in insertion.sub_concepts
    # passes both forms — full path and bare leaf — through matches()
    assert insertion.sub_concepts['breasts'].matches(['interaction.insertion.breasts_body']) is True
    assert insertion.sub_concepts['breasts'].matches(['breasts_body']) is True
    assert insertion.sub_concepts['vagina'].matches(['interaction.insertion.breasts_body']) is False


# --- render order ---


def test_render_label_prompts_preserves_group_order(skin):
    out = skin.render_label_prompts([
        'primary.action.blowjob',
        'primary.attribute.muscular',
        'secondary.pose.front',
    ])
    # groups in build order: primary.attribute, primary.pose, primary.action,
    # secondary.attribute, secondary.pose, …
    bm = out.index(skin.labels['primary.attribute.muscular'])
    bj = out.index(skin.labels['primary.action.blowjob'])
    mf = out.index(skin.labels['secondary.pose.front'])
    assert bm < bj < mf


def test_render_label_prompts_drops_unknown(skin):
    out = skin.render_label_prompts(['primary.action.blowjob', 'not_a_label'])
    assert len(out) == 1
    assert out[0] == skin.labels['primary.action.blowjob']


def test_render_label_prompts_legacy_leaf_fallback(skin):
    """Bare leaf names (e.g. `blowjob`) still render — picking the first path
    whose final segment matches in build order. `front` is ambiguous (both
    primary and secondary have it); the build-order winner is primary."""
    out = skin.render_label_prompts(['blowjob'])
    assert out == [skin.labels['primary.action.blowjob']]
    out2 = skin.render_label_prompts(['front'])
    assert out2 == [skin.labels['primary.pose.front']]


# --- _built persistence integrity ---


def test_persisted_built_matches_source_hash(skin):
    """If the skin was built and persisted, source_hash should match."""
    raw = skin.source
    if raw.get('_built') is None:
        pytest.skip('no _built persisted; skipping')
    assert raw['_built']['source_hash'] == _compute_source_hash(raw)


# --- compute_labels_ng (legacy → structured path migration) ---


def test_compute_labels_ng_basic(skin):
    from ait.caption.skin import compute_labels_ng
    paths, unknown = compute_labels_ng(['blowjob', 'man_front', 'i_breasts_body'], skin)
    assert paths == [
        'primary.action.blowjob',
        'secondary.pose.front',
        'interaction.insertion.breasts_body',
    ]
    assert unknown == []


def test_compute_labels_ng_pose_renames(skin):
    """Legacy `woman_*` and `man_*` pose names resolve via the explicit
    rename map, plus the bare `sitting` legacy maps to the renamed
    on-body-part `secondary.pose.perched`."""
    from ait.caption.skin import compute_labels_ng
    paths, unknown = compute_labels_ng(
        ['woman_front', 'woman_sitting', 'man_front', 'man_sitting', 'sitting'],
        skin,
    )
    assert paths == [
        'primary.pose.front',
        'primary.pose.sitting',
        'secondary.pose.front',
        'secondary.pose.sitting',
        'secondary.pose.perched',
    ]
    assert unknown == []


def test_compute_labels_ng_strips_b_prefix(skin):
    """Legacy b_<name> labels resolve to their renamed un-prefixed form."""
    from ait.caption.skin import compute_labels_ng
    paths, unknown = compute_labels_ng(
        ['b_muscular', 'b_busty', 'b_slim', 'b_curvy', 'b_hairy'], skin
    )
    assert paths == [
        'primary.attribute.muscular',
        'primary.attribute.busty',
        'primary.attribute.slim',
        'primary.attribute.curvy',
        'primary.attribute.hairy',
    ]
    assert unknown == []


def test_compute_labels_ng_drops_unknown(skin):
    from ait.caption.skin import compute_labels_ng
    paths, unknown = compute_labels_ng(['blowjob', 'not_a_label', 'b_unknown'], skin)
    assert paths == ['primary.action.blowjob']
    assert sorted(unknown) == ['b_unknown', 'not_a_label']


def test_compute_labels_ng_empty(skin):
    from ait.caption.skin import compute_labels_ng
    assert compute_labels_ng([], skin) == ([], [])


def test_compile_user_prompt_includes_directive_and_label(skin):
    p = skin.compile_user_prompt(['primary.action.blowjob'], hint='')
    assert p.startswith(skin.default_prompt)
    assert skin.directive in p
    assert skin.labels['primary.action.blowjob'] in p
    assert '{hint}' not in p
    # no hint-preamble emitted when hint is empty
    assert skin.user_hint_preamble.format(hint='') not in p


def test_compile_user_prompt_inlines_hint(skin):
    p = skin.compile_user_prompt([], hint='she holds him close')
    assert 'she holds him close' in p
    # the {hint} placeholder is filled, not left raw
    assert '{hint}' not in p


def test_compile_user_prompt_no_labels_no_label_text(skin):
    p = skin.compile_user_prompt([], hint='')
    # no label expansions, just default_prompt + directive + post_prompt
    for v in skin.labels.values():
        assert v not in p


def test_compute_labels_ng_preserves_input_order(skin):
    """Output paths follow input order (caller controls semantics)."""
    from ait.caption.skin import compute_labels_ng
    paths, _ = compute_labels_ng(['man_front', 'b_muscular', 'blowjob'], skin)
    assert paths == [
        'secondary.pose.front',
        'primary.attribute.muscular',
        'primary.action.blowjob',
    ]
