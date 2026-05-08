---
description: Audit and fix captions where hints/labels are not correctly integrated.
argument-hint: "[set-name (default: gts_v3)]"
---

Audit and fix `caption_joy` fields in the prod `aidb` DB for the set named `$ARGUMENTS` (default `gts_v3`) where hints or labels are not correctly integrated. The human-edited `caption` field is out of scope and must not be modified.

## Setup

Connect to prod with the env vars documented in CLAUDE.md:

```
PYTHONPATH=src HOME_AIT=. CONF_AIT=./conf WORKSPACE=$HOME/Workspace AIDB_SCENE_CONFIG=prod AIDB_SCENE_DEFAULT=0000
```

Use `SceneSetManager(config='prod')` and `set_from_id_or_name(name)`. Use `SceneImageManager.img_from_id(id)` for per-image lookups.

## Audit pass

Iterate all "cap_joy" active images of the set:

- "active": skip `img.prototype`; rely on `scene_set.imgs` to pre-filter excluded.
- "cap_joy": all three of `FIELD_HINTS`, `FIELD_LABELS`, `FIELD_CAPTION_JOY` are non-empty.

The main purpose is to fix discrepancies between `caption_joy` and the ground-truth `hints` + `labels`. Compare each `caption_joy` against its `hints` and `labels` and flag these issue classes:

1. **Active-verb softening** — hint uses an active female-driven verb (`squeeze`, `sit`, `insert`, `press`, `lift`, `grip`) and `caption_joy` uses a passive male-positioning verb instead (`cup`, `held`, `positioned`, `placed`, `supported`).
2. **Body-part / spatial mismatch** — `caption_joy` describes a body part or spatial relationship that contradicts or is less specific than what the hint says.
3. **Qualifier stripping** — hint contains a degree word (`half`, `deeply`, `partly`, `slightly`, `barely`, `fully`) that `caption_joy` omits.
4. **Forbidden vocabulary** — `caption_joy` contains words on `_FORBIDDEN_IN_XLASM`. Use `ait.caption.joy.caption_has_xlasm_violations(caption_joy)`.
5. **Trigger absence** — `caption_joy` missing `xlgts woman` or `xlasm man`. Use `ait.caption.joy.validate_trigger_presence(caption_joy)`.

## Skip rules

- Skip any `caption_joy` that shows clear signs of manual editing (e.g. structural cleanup the model wouldn't produce, deliberate phrasing like *"The central interaction is..."*). `caption_joy` is meant to be the raw model output, but if the user has manually tightened it, don't override that work.
- Skip if `hints` and `labels` are both empty or trivially short — there's nothing to verify against.

## Proposal pass

For each image with at least one issue, propose **minimal in-place patches** as `from → to` string-replace diffs. Hard rules:

- No full rewrites.
- No inventing visual details that aren't already in `caption_joy` or the hint.
- Each patch must be an exact substring match of the current `caption_joy`.
- Prefer one patch per issue. Bundle multiple patches per image only if the issues are independent.

Present the proposed edits as a markdown table per image, then ask for batch approval (one yes/no for the whole set).

## Persist pass (only after approval)

For each approved image:

1. Read current `caption_joy`.
2. Apply each `(from, to)` patch via `str.replace(old, new, 1)`.
3. Verify each `from` substring was found before applying.
4. Write the new value via `img._data |= {SceneDef.FIELD_CAPTION_JOY: new_cap_joy}; img.db_store()`.
5. Read back and confirm the new substrings are present.

**Do not touch `caption`.** It is the human-edited, training-fed field and is out of scope for this command. Only `caption_joy` (the model-output / audit trail field) is repaired here.

Report a per-image OK/FAIL summary at the end.
