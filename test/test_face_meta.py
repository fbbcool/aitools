"""Unit tests for the face_meta bucketing module.

Exercises every Tier-A measurement → label-path mapping under the
1xlface skin, plus partial-coverage and edge-case behaviour, plus the
PNG tEXt-chunk parser.

No model load, no DB connection — pure dict-in / list-out.
"""
import io
import json
import os
from pathlib import Path

import pytest

from ait.caption.face_meta import (
    bucket,
    bucket_from_png,
    parse_png_face_meta,
    PNG_TEXT_KEY,
)
from ait.caption.skin import SkinRegistry


REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module', autouse=True)
def _set_conf_ait():
    os.environ['CONF_AIT'] = str(REPO / 'conf')
    yield


@pytest.fixture(scope='module')
def skin():
    return SkinRegistry().get('1xlface')


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _full_payload(**overrides):
    """A face-mesh-confident, head-on, eyes-open, mouth-closed payload at
    a head-and-shoulders distance. Override individual measurements to
    test each axis in isolation.

    Default `ear_left`/`ear_right` = 0.40 sits in aip-fvx/0.1.0's
    clearly-open range (~0.35–0.50)."""
    base = {
        'bbox_frac':          0.15,
        'face_centroid_norm': [0.50, 0.45],
        'head_pose_ypr_deg':  [0.0, 0.0, 0.0],
        'gaze_yaw_deg':       0.0,
        'gaze_pitch_deg':     0.0,
        'ear_left':           0.40,
        'ear_right':          0.40,
        'mar':                0.03,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# framing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('bbox_frac,expected', [
    (0.85, 'primary.framing.extreme_close_up'),
    (0.55, 'primary.framing.close_up'),
    (0.30, 'primary.framing.headshot'),
    (0.15, 'primary.framing.head_and_shoulders'),
    (0.05, 'primary.framing.three_quarter'),
])
def test_framing_buckets(skin, bbox_frac, expected):
    out = bucket(_full_payload(bbox_frac=bbox_frac), skin)
    assert expected in out


def test_framing_absent_when_bbox_missing(skin):
    """No bbox_frac → no framing label (best-effort partial coverage)."""
    payload = _full_payload()
    del payload['bbox_frac']
    out = bucket(payload, skin)
    framing_paths = [p for p in out if p.startswith('primary.framing.')]
    assert framing_paths == []


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------

def test_composition_off_center_when_centroid_far_from_midline(skin):
    out = bucket(_full_payload(face_centroid_norm=[0.78, 0.45]), skin)
    assert 'primary.composition.off_center' in out


def test_composition_not_off_center_when_centered(skin):
    out = bucket(_full_payload(face_centroid_norm=[0.52, 0.45]), skin)
    assert 'primary.composition.off_center' not in out


def test_composition_orthogonal_to_framing(skin):
    """Both can fire together — off_center is a modifier, framing is the
    distance bucket."""
    out = bucket(_full_payload(
        bbox_frac=0.55,
        face_centroid_norm=[0.78, 0.45],
    ), skin)
    assert 'primary.framing.close_up' in out
    assert 'primary.composition.off_center' in out


# ---------------------------------------------------------------------------
# gaze (head_pose + iris combined)
# ---------------------------------------------------------------------------

def test_gaze_at_camera(skin):
    out = bucket(_full_payload(
        head_pose_ypr_deg=[2.0, -1.5, 0.0],
        gaze_yaw_deg=3.0, gaze_pitch_deg=-2.0,
    ), skin)
    assert 'primary.gaze.at_camera' in out


def test_gaze_off_camera_left_when_head_turned_subject_left(skin):
    """Positive yaw = subject's gaze pointed to subject's left
    (viewer's right) → `off_camera_left` per the skin description."""
    out = bucket(_full_payload(
        head_pose_ypr_deg=[25.0, 0.0, 0.0],
        gaze_yaw_deg=5.0, gaze_pitch_deg=0.0,
    ), skin)
    assert 'primary.gaze.off_camera_left' in out


def test_gaze_off_camera_right_when_head_turned_subject_right(skin):
    out = bucket(_full_payload(
        head_pose_ypr_deg=[-25.0, 0.0, 0.0],
        gaze_yaw_deg=-5.0, gaze_pitch_deg=0.0,
    ), skin)
    assert 'primary.gaze.off_camera_right' in out


def test_gaze_up_when_pitch_dominates(skin):
    """aip-verified: POSITIVE pitch = looking UP."""
    out = bucket(_full_payload(
        head_pose_ypr_deg=[0.0, 25.0, 0.0],
        gaze_yaw_deg=0.0, gaze_pitch_deg=5.0,
    ), skin)
    assert 'primary.gaze.up' in out


def test_gaze_down_when_pitch_dominates(skin):
    """aip-verified: NEGATIVE pitch = looking DOWN."""
    out = bucket(_full_payload(
        head_pose_ypr_deg=[0.0, -25.0, 0.0],
        gaze_yaw_deg=0.0, gaze_pitch_deg=-5.0,
    ), skin)
    assert 'primary.gaze.down' in out


def test_gaze_dead_zone_unbucketed(skin):
    """Inside off-axis dead-zone but outside at_camera box → no gaze
    label (JoyCaption will refine). Still emits eye_state."""
    out = bucket(_full_payload(
        head_pose_ypr_deg=[12.0, 0.0, 0.0],
        gaze_yaw_deg=0.0, gaze_pitch_deg=0.0,
    ), skin)
    gaze_paths = [p for p in out if p.startswith('primary.gaze.')]
    assert gaze_paths == []
    # eye_state still emitted because EAR is present
    assert any(p.startswith('primary.eye_state.') for p in out)


def test_gaze_absent_when_head_pose_missing(skin):
    payload = _full_payload()
    del payload['head_pose_ypr_deg']
    out = bucket(payload, skin)
    gaze_direction_paths = [
        p for p in out
        if p.startswith('primary.gaze.') and p != 'primary.gaze.eyes_closed'
    ]
    assert gaze_direction_paths == []


# ---------------------------------------------------------------------------
# eye_state + eyes_closed override
# ---------------------------------------------------------------------------

def test_eyes_fully_closed_emits_gaze_eyes_closed_no_eye_state(skin):
    """When mean EAR < 0.12 → gaze.eyes_closed overrides eye_state group
    (calibrated for aip-fvx/0.1.0+1k3d68)."""
    out = bucket(_full_payload(ear_left=0.05, ear_right=0.05), skin)
    assert 'primary.gaze.eyes_closed' in out
    assert not any(p.startswith('primary.eye_state.') for p in out)


def test_eye_state_half_closed(skin):
    """Mean EAR in [0.12, 0.30) → half_closed."""
    out = bucket(_full_payload(ear_left=0.22, ear_right=0.22), skin)
    assert 'primary.eye_state.half_closed' in out
    assert 'primary.gaze.eyes_closed' not in out


def test_eye_state_open(skin):
    """Mean EAR ≥ 0.30 → open. Aip-fvx clearly-open eyes run 0.35–0.50."""
    out = bucket(_full_payload(ear_left=0.40, ear_right=0.40), skin)
    assert 'primary.eye_state.open' in out


def test_eye_state_asymmetric_averages(skin):
    """Asymmetric EAR (one eye occluded but still emitted) — averages
    cleanly. Profile shots typically omit one EAR rather than emitting
    a misleading value, so this case is mostly for completeness."""
    out = bucket(_full_payload(ear_left=0.40, ear_right=0.22), skin)
    # mean 0.31 → above 0.30 threshold → open
    eye_paths = [p for p in out if p.startswith('primary.eye_state.')]
    assert eye_paths == ['primary.eye_state.open']


def test_eye_state_absent_when_no_ear(skin):
    payload = _full_payload()
    del payload['ear_left']
    del payload['ear_right']
    out = bucket(payload, skin)
    eye_paths = [p for p in out if p.startswith('primary.eye_state.')]
    assert eye_paths == []


# ---------------------------------------------------------------------------
# mouth_state (MAR-only — open here means "wide gape", not "teeth visible")
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('mar,expected', [
    # MAR thresholds calibrated for aip-fvx/0.1.0+1k3d68 — 4-band scheme:
    # closed (<0.05) | slightly_parted (0.05–0.20) | open (0.20–0.45) | wide (≥0.45)
    (0.03, 'primary.mouth_state.closed'),
    (0.12, 'primary.mouth_state.slightly_parted'),
    (0.30, 'primary.mouth_state.open'),
    (0.88, 'primary.mouth_state.wide'),
])
def test_mouth_state_buckets(skin, mar, expected):
    out = bucket(_full_payload(mar=mar), skin)
    assert expected in out


def test_mouth_state_absent_when_mar_missing(skin):
    payload = _full_payload()
    del payload['mar']
    out = bucket(payload, skin)
    mouth_paths = [p for p in out if p.startswith('primary.mouth_state.')]
    assert mouth_paths == []


# ---------------------------------------------------------------------------
# partial coverage (profile / occlusion: framing only)
# ---------------------------------------------------------------------------

def test_partial_coverage_framing_only(skin):
    """Mesh fit failed (no head_pose, no gaze, no EAR, no MAR), but the
    detector still emitted bbox + centroid. Expect framing + composition
    only."""
    payload = {
        'bbox_frac':          0.30,
        'face_centroid_norm': [0.50, 0.45],
    }
    out = bucket(payload, skin)
    assert out == ['primary.framing.headshot']


def test_empty_structural_returns_empty(skin):
    assert bucket({}, skin) == []
    assert bucket(None, skin) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# skin-vocabulary safety (non-1xlface skin should never bucket)
# ---------------------------------------------------------------------------

def test_non_face_skin_returns_empty(skin):
    """Bucketing against 1xlasm (which has no `primary.framing.*` paths)
    should return [] — the safety filter at the end drops paths absent
    from the active skin's vocabulary."""
    xlasm = SkinRegistry().get('1xlasm')
    out = bucket(_full_payload(), xlasm)
    assert out == []


# ---------------------------------------------------------------------------
# PNG tEXt chunk parsing
# ---------------------------------------------------------------------------

def _make_png_with_face_meta(face_meta: dict, tmp_path: Path) -> Path:
    """Synthesise a tiny PNG with `face_meta` embedded as a tEXt chunk."""
    from PIL import Image as _PILImage
    from PIL.PngImagePlugin import PngInfo
    img = _PILImage.new('RGB', (4, 4), color=(0, 0, 0))
    info = PngInfo()
    info.add_text(PNG_TEXT_KEY, json.dumps(face_meta))
    path = tmp_path / 'sample.png'
    img.save(path, 'PNG', pnginfo=info)
    return path


def test_parse_png_face_meta_roundtrips(tmp_path):
    fm = {
        'confidence': 0.99,
        'extractor_version': 'aip-fvx/0.1.0+insightface-buffalo_l+1k3d68',
        'structural': {
            'bbox_frac': 0.30,
            'ear_left': 0.40, 'ear_right': 0.40,
        },
    }
    p = _make_png_with_face_meta(fm, tmp_path)
    parsed = parse_png_face_meta(p)
    assert parsed == fm


def test_parse_png_face_meta_no_chunk(tmp_path):
    from PIL import Image as _PILImage
    img = _PILImage.new('RGB', (4, 4), color=(0, 0, 0))
    p = tmp_path / 'plain.png'
    img.save(p, 'PNG')
    assert parse_png_face_meta(p) is None


def test_parse_png_face_meta_invalid_path(tmp_path):
    assert parse_png_face_meta(tmp_path / 'does-not-exist.png') is None


def test_parse_png_face_meta_accepts_pil_image(tmp_path):
    fm = {'structural': {'bbox_frac': 0.20}}
    p = _make_png_with_face_meta(fm, tmp_path)
    from PIL import Image as _PILImage
    with _PILImage.open(p) as img:
        parsed = parse_png_face_meta(img)
    assert parsed == fm


def test_bucket_from_png_end_to_end(skin, tmp_path):
    """Full pipeline: synthesise PNG with face_meta → bucket_from_png →
    confirm the expected label paths come back."""
    fm = {
        'extractor_version': 'aip-fvx/0.1.0+insightface-buffalo_l+1k3d68',
        'structural': {
            'bbox_frac':          0.30,
            'face_centroid_norm': [0.50, 0.45],
            'head_pose_ypr_deg':  [0.0, 0.0, 0.0],
            'ear_left':           0.40, 'ear_right': 0.40,
            'mar':                0.03,
        },
    }
    p = _make_png_with_face_meta(fm, tmp_path)
    out = bucket_from_png(p, skin)
    # Expect headshot framing + open eyes + closed mouth. No gaze
    # direction (aip omits gaze keys in v0.1.0 → abstain).
    assert 'primary.framing.headshot' in out
    assert 'primary.eye_state.open' in out
    assert 'primary.mouth_state.closed' in out
    # Gaze omitted in v0.1.0 → no gaze.* label (absence = abstain)
    assert not any(p.startswith('primary.gaze.') for p in out)


def test_bucket_from_png_no_chunk_returns_empty(skin, tmp_path):
    from PIL import Image as _PILImage
    img = _PILImage.new('RGB', (4, 4), color=(0, 0, 0))
    p = tmp_path / 'plain.png'
    img.save(p, 'PNG')
    assert bucket_from_png(p, skin) == []


def test_bucket_from_png_no_structural_returns_empty(skin, tmp_path):
    """face_meta present but missing the `structural` block — should
    return [] silently (defensive: aitools side stays robust to
    partial/legacy aip payloads)."""
    fm = {'confidence': 0.9, 'extractor_version': 'aip-fvx/legacy'}
    p = _make_png_with_face_meta(fm, tmp_path)
    assert bucket_from_png(p, skin) == []
