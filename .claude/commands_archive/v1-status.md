---
description: Report v1 dataset progress for the gts LoRA against the editable plan below. Concept map and per-concept targets are sourced from the skin JSON.
argument-hint: "[skin (default: 1xlasm)] [set-name (default: skin.default_set or gts_v3)]"
---

Report v1 dataset progress for the gts LoRA. Args: `$ARGUMENTS` — first token is the skin name (default `1xlasm`), second is the set name (default = `skin.default_set` or `gts_v3`).

Only **done** images count, in any set. **Done** = non-prototype, active image with non-empty `hints` AND non-empty `labels_ng` (preferred) or `labels` (legacy) AND non-empty `caption_joy` AND non-empty `caption`. The skin's renamed/path-based label vocabulary lives in `labels_ng`; `labels` retains the original pre-rename names for backward compatibility and is no longer the source of truth for concept matching.

## V1 plan (edit me)

- **total target images:** 1000
- **lora rank:** 32

### Body variants — out of scope for gts-v3

Female body-type concepts (`busty` / `fbb` / `leggy` / `hairy` / `curvy` / etc.) and their dedicated SceneSets are **intentionally not part of the gts-v3 training set**. They are handled by a separate family of body-variant LoRAs trained AFTER gts-v3 ships, against a `snofs+gts-v3` merged base — see the body-LoRA architecture note in the project plan. Do not load body-variant sets, do not include body-variant concepts as report rows, and do not generate body-variant todos in the urgency list.

Nuance worth keeping: **body-attribute labels on otherwise gts-focused images stay applied.** Example — an insertion scene where the woman is also tagged `primary.attribute.busty` remains in the gts-v3 set with the busty label intact. gts-v3 then learns "given busty context, render this way" as a *conditional* feature, and the later body-LoRAs can compose with that knowledge cleanly. What's excluded is *images whose primary subject is the body variant itself* (e.g. busty-woman portraits with no gts/size context) — those become training data for the body LoRAs, not gts-v3.

### GTS concepts (from the skin JSON)

The fixed concept list, target counts, label match rules, and insertion sub-concepts all live in `conf/skins/<skin>.json` under the `concepts` key. **Do not duplicate the table here.** Iterate `skin.concepts` in declaration order (this is the canonical plan order).

Each concept has one of these match rules:
- `labels: [...]` — exact membership (any-of)
- `label_prefix: [...]` — any label starts with one of the prefixes
- `residual: true` — matches when the image has labels but no other concept matched, optionally filtered by `ignore_label_prefix`

A concept may have `sub_concepts` (informational only — no own target).

For each concept, two counts matter:

- **done**: distinct images matching the concept that pass the full done filter (hints + labels + caption_joy + caption all non-empty).
- **labeled-not-done** ("potential"): non-prototype images matching the concept that are NOT yet done — the captioning queue waiting on this concept.

## Setup

Connect to prod with the env vars documented in CLAUDE.md:

```
PYTHONPATH=src HOME_AIT=. CONF_AIT=./conf WORKSPACE=$HOME/Workspace AIDB_SCENE_CONFIG=prod AIDB_SCENE_DEFAULT=0000
```

Load the skin:

```python
from ait.caption.skin import SkinRegistry
skin = SkinRegistry().get(skin_name)   # raises if no such conf/skins/<skin_name>.json
target_set = set_arg or skin.default_set or 'gts_v3'
```

Use `SceneSetManager(config='prod')` and `set_from_id_or_name(target_set)` to load the set. Iterate `scene_set.imgs` and skip prototype images.

## Compute

1. **Args** — parse `$ARGUMENTS`: token 1 = skin name (default `1xlasm`), token 2 = set name (default `skin.default_set` or `gts_v3`).
2. **Input set** — load `target_set`.
3. **Applied labels for matching** — for each non-prototype image, take `labels_ng` (FIELD_LABELS_NG) directly; if missing/empty, fall back to translating `labels` (FIELD_LABELS) via `compute_labels_ng(labels, skin)`. Both forms feed `skin.matched_concepts(...)` — concept rules use leaf names, and the matcher extracts the leaf from each path automatically.
4. **Concept matching** — for each non-prototype image with at least one applied label, call `skin.matched_concepts(applied_paths) -> {concept_name: bool}` (residual handling is internal). Tally `{done, potential}` per concept where `done` requires the full done filter.
5. **Sub-concepts** — for each top-level concept that has `sub_concepts`, evaluate each sub-concept's match rule on the same image and tally `{done, potential}`. Sub-concepts have no target — informational only.
6. **Distinct done total** — count distinct done images in the input set.

For each concept, compute progress against its target with a status flag:
- `OK` if `current >= target`
- `LOW` if `0.4 * target <= current < target`
- `EMPTY` if `current < 0.4 * target` (count of 0 is also EMPTY)

## Report

Output a compact status report:

1. **Header** — skin name, input set name, total target, rank, total done, percent toward total target.
2. **GTS concepts table** — columns: `concept`, `done`, `potential`, `target`, `%done`, `status`. One row per top-level concept in `skin.concepts` declaration order.
3. **Sub-concepts table** — for each concept with sub_concepts, columns: `sub-concept`, `done`, `potential`. Informational only.
4. **Bottom-line takeaway** — one or two sentences naming the concepts at EMPTY/LOW, mentioning whether they have a usable potential queue (captioning would unblock them) or need new images registered.
5. **Most urgent todos** — a numbered list of 3-5 concrete next actions, sorted by urgency. Each item must be specific and actionable with a number attached:
    - "caption N more images for concept `Y` (potential queue: P)"
    - "register / source N more images for concept `Y` (potential queue exhausted)"
    - Not vague encouragement.
   Urgency rules:
    - **EMPTY > LOW > OK**.
    - Within the same status tier, prioritize concepts that have a **usable potential queue** (≥ ~10 labeled-not-done images ready to caption) — captioning unblocks them immediately. Concepts with `potential = 0` need upstream sourcing/labeling work, which is more expensive.
    - Within the captionable subset, prefer concepts with the largest gap to target (highest expected v1 contribution).
    - When a concept needs sourcing, suggest a number bounded by `target - done`.

Keep the report under ~60 lines. No additional context, no markdown headers beyond the tables.

## Access rights

read-only access to the db can be done w/o yes from user
