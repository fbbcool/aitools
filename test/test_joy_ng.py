"""Tests for JoyNG prompt assembly.

We exercise `JoyNG.compose_prompt` (no model call) to verify the prompt
structure: default_prompt + user_content + (optional hint) + label_prompts +
post_prompt. Behavioral correctness of the model call itself is exercised by
the JoySceneDBNG end-to-end smoke test, not here.
"""
import os
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module', autouse=True)
def _set_conf_ait():
    os.environ['CONF_AIT'] = str(REPO / 'conf')
    yield


def _make_compose():
    """Bind compose_prompt without instantiating JoyNG (which loads the model).

    JoyNG.compose_prompt is a regular method that doesn't touch self.model;
    we can call it via the unbound function directly.
    """
    from ait.caption.joy_ng import JoyNG
    return JoyNG.compose_prompt


def test_compose_minimal():
    compose = _make_compose()
    p = compose(
        None,  # self placeholder; method doesn't use it
        user_content='UC',
        default_prompt='DP',
    )
    assert p == 'DPUC'


def test_compose_with_hint():
    compose = _make_compose()
    p = compose(
        None,
        user_content='UC',
        default_prompt='DP',
        user_hint_preamble=' [hint: {hint}]',
        user_hint='handjob with left hand',
    )
    assert p == 'DPUC [hint: handjob with left hand]'


def test_compose_hint_requires_preamble():
    compose = _make_compose()
    with pytest.raises(ValueError, match='user_hint_preamble'):
        compose(None, user_content='UC', user_hint='something')


def test_compose_hint_empty_skips_preamble():
    """If user_hint is empty/whitespace, the preamble is skipped."""
    compose = _make_compose()
    p = compose(
        None,
        user_content='UC',
        default_prompt='DP',
        user_hint_preamble=' [hint: {hint}]',
        user_hint='   ',   # whitespace
    )
    assert p == 'DPUC'


def test_compose_label_prompts_concatenated():
    compose = _make_compose()
    p = compose(
        None,
        user_content='UC',
        default_prompt='DP',
        label_prompts=['L1.', ' L2.', ' L3.'],
    )
    assert p == 'DPUCL1. L2. L3.'


def test_compose_post_prompt():
    compose = _make_compose()
    p = compose(
        None,
        user_content='UC',
        default_prompt='DP',
        label_prompts=['L1.'],
        post_prompt=' END',
    )
    assert p == 'DPUCL1. END'


def test_compose_full_pipeline():
    """Verify the full compose order matches what JoySceneDBNG/Joy would produce:
    default_prompt + user_content + hint preamble + label prompts + post_prompt.
    """
    compose = _make_compose()
    p = compose(
        None,
        user_content='SYS_DIRECTIVE',
        default_prompt='Write a detailed description of this image.',
        user_hint_preamble=' Hint: {hint}.',
        user_hint='woman steps on man',
        label_prompts=['Label A.', ' Label B.'],
        post_prompt=' DONE',
    )
    expected = (
        'Write a detailed description of this image.SYS_DIRECTIVE'
        ' Hint: woman steps on man.'
        'Label A. Label B.'
        ' DONE'
    )
    assert p == expected


def test_skin_to_joy_ng_compose_components_match_legacy():
    """Compose a prompt the way JoySceneDBNG would. The directive (user_content)
    is rebuilt from entities/interaction so it deliberately differs from
    legacy CONTENT_PROMPT (per plan); label render order is by group rather
    than input list. We assert the structural components match: default
    prompt, hint preamble, label-prompt set, and post prompt are all present.
    """
    from ait.caption import joy
    from ait.caption.joy_ng import JoyNG
    from ait.caption.skin import SkinRegistry

    skin = SkinRegistry().get('1xlasm')
    # Skin uses the renamed (un-prefixed) `busty` label; the legacy LABEL_PROMPT
    # under joy.py still uses `b_busty`. Map below correlates them.
    labels_new = ['blowjob', 'busty']
    labels_legacy = ['blowjob', 'b_busty']
    hint = 'large breasts visible'

    rendered = skin.render_label_prompts(labels_new)
    new = JoyNG.compose_prompt(
        None,
        user_content=skin.directive,
        default_prompt=skin.default_prompt,
        label_prompts=rendered,
        user_hint_preamble=skin.user_hint_preamble,
        user_hint=hint,
        post_prompt=skin.post_prompt,
    )

    # default_prompt unchanged
    assert new.startswith(joy.DEFAULT_PROMPT)
    # directive present (rebuilt — not byte-equal to CONTENT_PROMPT)
    assert skin.directive in new
    # hint preamble interpolated correctly
    assert joy.USER_HINT_PREAMBLE.format(hint=hint) in new
    # every applied label's prompt appears verbatim, byte-equal to LABEL_PROMPT
    for label in labels_legacy:
        assert joy.LABEL_PROMPT[label] in new
    # render order is group-declaration order: busty (primary.attribute) BEFORE
    # blowjob (primary.action) — opposite of legacy input-order behavior.
    assert new.index(joy.LABEL_PROMPT['b_busty']) < new.index(joy.LABEL_PROMPT['blowjob'])
