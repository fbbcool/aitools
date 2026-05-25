"""Bucket aip's `face_meta.structural` measurements into 1xlface skin label paths.

The aip avatar project emits raw structural measurements per face crop
(see avatar-project contract). aitools owns the thresholds + bucketing
into the active skin's label vocabulary. Presence-driven: aip's policy
is "1.0 confidence or omit the key entirely" — so this module simply
checks for measurement presence and skips bucketing when a measurement
is absent. No graded thresholds across the project boundary.

Conventions documented at the boundary:

- `head_pose_ypr_deg[0]` (yaw): positive = subject's head turned to
  subject's left (viewer's right). *Confirmed by aip via landmark
  projection on Fuck Yes.mp4 frame 200, sign-convention reply.*
- `head_pose_ypr_deg[1]` (pitch): positive = subject looking UPWARD.
  *Confirmed by aip via landmark projection on Fuck Yes.mp4 frame 200.*
- `head_pose_ypr_deg[2]` (roll): positive = top of head tilts to
  viewer's right. *Confirmed by aip; not currently bucketed.*
- `gaze_yaw_deg` / `gaze_pitch_deg`: face-relative gaze in degrees.
  Camera-relative gaze is computed as `head_pose + gaze` before bucketing.
- `face_centroid_norm`: [x, y] in normalised image coords, origin
  top-left, both in [0..1] (PIL/OpenCV convention).
- `bbox_frac`: face bbox area / image area, [0..1].
- `ear_left` / `ear_right`: Eye Aspect Ratio. Range is model-dependent;
  on aip-fvx/0.1.0+insightface-buffalo_l+1k3d68 clearly-open eyes
  run ~0.35–0.50 (higher than EAR-paper defaults of ~0.25–0.30).
  Thresholds below are calibrated for that extractor.
- `mar`: Mouth Aspect Ratio. Range model-dependent; thresholds below
  are first-draft pending real sample data.

Calibration source: aip-fvx/0.1.0+insightface-buffalo_l+1k3d68. Re-tune
the constants below when the extractor version changes or once real
sample payloads land for fine-tuning.
"""
from __future__ import annotations

import json
from typing import Any, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from pathlib import Path
    from PIL import Image as PILImage
    from .skin import Skin


# Key used by aip when writing the PNG tEXt chunk.
PNG_TEXT_KEY: str = 'face_meta'


# ---------------------------------------------------------------------------
# Threshold constants — tune these as we learn from real data
# ---------------------------------------------------------------------------

# Gaze direction (camera-relative yaw / pitch, in degrees)
_GAZE_AT_CAMERA_YAW_DEG: float = 10.0
_GAZE_AT_CAMERA_PITCH_DEG: float = 10.0
_GAZE_OFF_AXIS_YAW_DEG: float = 15.0
_GAZE_OFF_AXIS_PITCH_DEG: float = 15.0

# Eye Aspect Ratio — calibrated against aip-fvx/0.1.0+insightface 1k3d68.
# Clearly-open eyes run ~0.35–0.50 on this extractor (vs ~0.25–0.30 in
# classic EAR-paper defaults), so the half_closed cutoff is shifted up
# proportionally. Re-tune when extractor version changes.
_EAR_FULLY_CLOSED: float = 0.12   # below → gaze.eyes_closed (overrides eye_state)
_EAR_HALF_CLOSED: float = 0.30    # below → eye_state.half_closed; ≥ → open

# Mouth Aspect Ratio — three cuts giving 4 bands. Calibrated against
# aip-fvx/0.1.0+1k3d68's 749-crop empirical bands:
#   closed/just-parted:  0.05–0.15
#   slightly parted:     0.20–0.40
#   clearly open:        0.45–0.70
#   wide / gape:         0.70+
# (My initial jezebeth-test recalibration to 0.40/0.65 was biased — that
# scene is heavily open-mouth video frames. The literature defaults for
# the closed/parted boundaries hold on the broader population.)
_MAR_CLOSED: float = 0.05         # below → mouth_state.closed
_MAR_PARTED: float = 0.20         # below → mouth_state.slightly_parted
_MAR_WIDE: float = 0.45           # below → mouth_state.open; above → wide

# Face bbox area as fraction of image area → framing distance bucket
_FRAMING_EXTREME_CLOSE_UP: float = 0.70
_FRAMING_CLOSE_UP: float = 0.40
_FRAMING_HEADSHOT: float = 0.20
_FRAMING_HEAD_AND_SHOULDERS: float = 0.10
# below 0.10 → three_quarter

# Composition: distance from frame midline (normalised)
_COMPOSITION_OFF_CENTER_DELTA: float = 0.15


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_png_face_meta(source: 'Union[Path, str, PILImage.Image]') -> Optional[dict[str, Any]]:
    """Read aip's `face_meta` PNG tEXt chunk from a file path or PIL Image.

    Returns the parsed `face_meta` dict (with `extractor_version` +
    `structural` + existing-extractor keys) when present and valid, else
    `None`. Defensive: any of {file not a PNG / chunk absent / chunk
    not valid JSON / chunk JSON not a dict} returns None silently —
    aitools side falls back to JoyCaption-only suggestion.
    """
    from PIL import Image as _PILImage

    img: Optional['PILImage.Image']
    if isinstance(source, _PILImage.Image):
        img = source
    else:
        try:
            img = _PILImage.open(str(source))
        except Exception:
            return None

    raw = img.info.get(PNG_TEXT_KEY) if img.info else None
    if not raw or not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def bucket_from_png(
    source: 'Union[Path, str, PILImage.Image]',
    skin: 'Skin',
) -> list[str]:
    """Convenience: parse_png_face_meta() + bucket(face_meta['structural']).

    Returns `[]` when there is no face_meta chunk, no `structural` block,
    or no measurements buckets cleanly. Never raises.
    """
    fm = parse_png_face_meta(source)
    if fm is None:
        return []
    structural = fm.get('structural')
    if not isinstance(structural, dict):
        return []
    return bucket(structural, skin)


def apply_to_scene_image(simg, skin: 'Skin', *, persist: bool = True) -> list[str]:
    """End-to-end: read the SceneImage's file, parse its `face_meta` PNG
    chunk, bucket against `skin`, and (optionally) persist the result to
    the SceneImage's `FIELD_LABELS_NG_EXTRACTION` field.

    Returns the bucketed label-path list (possibly empty when there is
    no `face_meta` chunk, no `structural` block, or no measurement
    buckets cleanly). When `persist=True`, also calls
    `simg.set_labels_ng_extraction(paths) + simg.db_store()` so the
    Mongo record is updated.

    `simg` is a `SceneImage` instance. `skin` is the active skin (the
    bucketing's vocabulary lives there).
    """
    url = simg.url_from_data
    if url is None:
        return []
    paths = bucket_from_png(str(url), skin)
    if persist and paths:
        simg.set_labels_ng_extraction(paths)
        simg.db_store()
    return paths


def bucket(structural: dict[str, Any], skin: 'Skin') -> list[str]:
    """Bucket a `face_meta.structural` dict into skin label paths.

    Returns a list of label paths from the skin's vocabulary. Each
    returned path is guaranteed to exist in `skin.labels`. Empty list
    when no measurements bucket cleanly.

    aip's "1.0 or omit" policy means presence-driven: a measurement
    being in the dict implies it is trustworthy; missing keys are
    skipped. The `structural.confidence.*` sub-dict is informational
    only at this layer — the presence of the parent key is the actual
    signal.

    Best-effort: a partial-coverage payload (e.g. profile shot where
    mesh fit failed) emits only what it has (typically framing +
    composition); the remaining groups stay empty for /img_suggest
    to fill.
    """
    if not structural:
        return []

    out: list[str] = []

    # framing — from bbox_frac
    framing = _bucket_framing(structural, skin)
    if framing:
        out.append(framing)

    # composition — from face_centroid_norm
    out.extend(_bucket_composition(structural, skin))

    # gaze + eye_state — combined (gaze.eyes_closed overrides eye_state)
    gaze_label, eye_label = _bucket_eyes(structural, skin)
    if gaze_label:
        out.append(gaze_label)
    if eye_label:
        out.append(eye_label)

    # mouth_state — from MAR
    mouth_label = _bucket_mouth(structural, skin)
    if mouth_label:
        out.append(mouth_label)

    # Filter to paths that actually exist in the active skin (defensive
    # — bucketing is 1xlface-shaped; on a non-1xlface skin some paths
    # may be absent).
    return [p for p in out if p in skin.labels]


# ---------------------------------------------------------------------------
# Per-group bucketing
# ---------------------------------------------------------------------------

def _bucket_framing(structural: dict[str, Any], skin: 'Skin') -> Optional[str]:
    bbox_frac = structural.get('bbox_frac')
    if not isinstance(bbox_frac, (int, float)):
        return None
    if bbox_frac >= _FRAMING_EXTREME_CLOSE_UP:
        leaf = 'extreme_close_up'
    elif bbox_frac >= _FRAMING_CLOSE_UP:
        leaf = 'close_up'
    elif bbox_frac >= _FRAMING_HEADSHOT:
        leaf = 'headshot'
    elif bbox_frac >= _FRAMING_HEAD_AND_SHOULDERS:
        leaf = 'head_and_shoulders'
    else:
        leaf = 'three_quarter'
    return f'primary.framing.{leaf}'


def _bucket_composition(structural: dict[str, Any], skin: 'Skin') -> list[str]:
    centroid = structural.get('face_centroid_norm')
    if not (isinstance(centroid, (list, tuple)) and len(centroid) == 2):
        return []
    cx = centroid[0]
    if not isinstance(cx, (int, float)):
        return []
    if abs(cx - 0.5) > _COMPOSITION_OFF_CENTER_DELTA:
        return ['primary.composition.off_center']
    return []


def _bucket_eyes(structural: dict[str, Any], skin: 'Skin') -> tuple[Optional[str], Optional[str]]:
    """Return (gaze_label, eye_state_label).

    gaze.eyes_closed overrides eye_state per the skin's group description
    — when both eyes are very closed we emit gaze.eyes_closed and skip
    eye_state entirely (the skin marks them redundant).

    Otherwise:
      - gaze direction is bucketed from camera-relative gaze
        (`head_pose + gaze` per the aip contract)
      - eye_state is bucketed from mean EAR
    """
    ear_left = structural.get('ear_left')
    ear_right = structural.get('ear_right')
    ears = [v for v in (ear_left, ear_right) if isinstance(v, (int, float))]
    mean_ear: Optional[float] = sum(ears) / len(ears) if ears else None

    # Eyes-closed override
    if mean_ear is not None and mean_ear < _EAR_FULLY_CLOSED:
        return ('primary.gaze.eyes_closed', None)

    # Gaze direction from combined head + iris vectors
    gaze_label = _bucket_gaze_direction(structural)

    # eye_state from EAR
    eye_state_label: Optional[str] = None
    if mean_ear is not None:
        if mean_ear < _EAR_HALF_CLOSED:
            eye_state_label = 'primary.eye_state.half_closed'
        else:
            eye_state_label = 'primary.eye_state.open'
        # `squinting` discrimination needs more than EAR alone (symmetric
        # narrowing + brow context) — deferred to JoyCaption.

    return (gaze_label, eye_state_label)


def _bucket_gaze_direction(structural: dict[str, Any]) -> Optional[str]:
    """Bucket gaze direction into one of the 5 direction leaves (not
    eyes_closed — that's handled upstream)."""
    head_pose = structural.get('head_pose_ypr_deg')
    gaze_yaw = structural.get('gaze_yaw_deg')
    gaze_pitch = structural.get('gaze_pitch_deg')

    have_head = isinstance(head_pose, (list, tuple)) and len(head_pose) >= 2
    have_gaze = isinstance(gaze_yaw, (int, float)) and isinstance(gaze_pitch, (int, float))
    if not (have_head and have_gaze):
        return None

    head_yaw = head_pose[0]
    head_pitch = head_pose[1]
    if not (isinstance(head_yaw, (int, float)) and isinstance(head_pitch, (int, float))):
        return None

    cam_yaw = float(head_yaw) + float(gaze_yaw)
    cam_pitch = float(head_pitch) + float(gaze_pitch)

    # at_camera: close to (0, 0)
    if abs(cam_yaw) < _GAZE_AT_CAMERA_YAW_DEG and abs(cam_pitch) < _GAZE_AT_CAMERA_PITCH_DEG:
        return 'primary.gaze.at_camera'

    # Up/down dominates when pitch is the largest off-axis component.
    # aip-verified convention: POSITIVE pitch = looking UP,
    # NEGATIVE pitch = looking DOWN (verified by landmark projection
    # on Fuck Yes.mp4 frame 200).
    if abs(cam_pitch) > abs(cam_yaw):
        if cam_pitch > _GAZE_OFF_AXIS_PITCH_DEG:
            return 'primary.gaze.up'
        if cam_pitch < -_GAZE_OFF_AXIS_PITCH_DEG:
            return 'primary.gaze.down'
    # Otherwise yaw direction
    # Convention: positive yaw = subject's gaze to subject's left
    # (viewer's right). Skin's `off_camera_left` = "eyes turned to the
    # subject's left", i.e. positive yaw.
    if cam_yaw > _GAZE_OFF_AXIS_YAW_DEG:
        return 'primary.gaze.off_camera_left'
    if cam_yaw < -_GAZE_OFF_AXIS_YAW_DEG:
        return 'primary.gaze.off_camera_right'

    # Inside the off-axis dead-zone but outside the at_camera box —
    # leave unbucketed so JoyCaption can refine.
    return None


def _bucket_mouth(structural: dict[str, Any], skin: 'Skin') -> Optional[str]:
    mar = structural.get('mar')
    if not isinstance(mar, (int, float)):
        return None
    if mar < _MAR_CLOSED:
        leaf = 'closed'
    elif mar < _MAR_PARTED:
        leaf = 'slightly_parted'
    elif mar < _MAR_WIDE:
        leaf = 'open'
    else:
        leaf = 'wide'
    # tongue_out / biting_lip are not bucketable from MAR alone — deferred
    # to JoyCaption.
    return f'primary.mouth_state.{leaf}'
