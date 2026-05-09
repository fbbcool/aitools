---
description: Report v1 dataset progress for the Qwen-Image-Edit gts LoRA against the editable plan below.
argument-hint: "[set-name (default: gts_v3)]"
---

Report v1 dataset progress for the Qwen-Image-Edit gts LoRA. The set to inspect is `$ARGUMENTS` (default `gts_v3`).

Only **done** images count, in any set. **Done** = non-prototype, active image with non-empty `hints` AND non-empty `labels` AND non-empty `caption_joy` AND non-empty `caption`.

## V1 plan (edit me)

- **total target images:** 1000
- **lora rank:** 32
- **per-gts-concept target:** 130

### Real concepts (DEACTIVATED — skip for now)

The four real concepts (`busty` / `fbb` / `leggy` / `hairy` SceneSets, 50 each) are part of the v1 plan but **deactivated** for the current report. Do not load any real sets, do not include real concepts in the tables, and do not include real-side todos in the urgency list. They will be reactivated later.

### GTS concepts

Do **not** hard-code gts concepts. Derive them from labels actually present in the input set: every label string that appears on at least one **non-prototype, labeled** image is a gts concept (regardless of whether that image is done yet), with target = 130. (Ignore the four real-concept labels `b_busty`, `b_muscular`, `b_slim`, `b_curvy` — those belong to the real subset.)

For each concept, two counts matter:

- **done**: images that pass the full done filter (hints + labels + caption_joy + caption all non-empty).
- **labeled-not-done** ("potential"): non-prototype images that have this label but are NOT yet done — i.e. the captioning queue waiting on this concept.

`done + potential` = total labeled images for the concept. The done count is what trains; the potential count tells you how much runway exists before you'd need to source/register new images.

## Setup

Connect to prod with the env vars documented in CLAUDE.md:

```
PYTHONPATH=src HOME_AIT=. CONF_AIT=./conf WORKSPACE=$HOME/Workspace AIDB_SCENE_CONFIG=prod AIDB_SCENE_DEFAULT=0000
```

Use `SceneSetManager(config='prod')` and `set_from_id_or_name(name)` to load each set. Iterate `scene_set.imgs` and skip prototype images. Wrap each `set_from_id_or_name(...)` call in try/except so a missing real set yields 0 instead of an error.

## Compute

1. **Input set** — load the set named `$ARGUMENTS` (default `gts_v3`).
2. **GTS labels** — scan all non-prototype images that have at least one label, build per-label `{done, potential}` where:
    - `done` = the image passes the full done filter.
    - `potential` = the image is labeled but NOT done.
   Skip the four real-concept labels (`b_busty` / `b_muscular` / `b_slim` / `b_curvy`).
3. **Distinct done total** — count distinct done images in the input set. This is the v1 dataset total for now (real subsets deactivated).

For each concept (real or gts), compute progress against its target with a status flag:
- `OK` if `current >= target`
- `LOW` if `0.4 * target <= current < target`
- `EMPTY` if `current < 0.4 * target` (count of 0 is also EMPTY)

## Report

Output a compact status report:

1. **Header** — input set name, total target, rank, total done (gts only — real deactivated), percent toward total target.
2. **GTS concepts table** — columns: `label`, `done`, `potential`, `target`, `%done`, `status`. Sort by `done` descending, with `potential` as a secondary sort key. Don't truncate; list every label that appears.
3. **Bottom-line takeaway** — one or two sentences naming the gts concepts at EMPTY/LOW, mentioning whether they have a usable potential queue (i.e. captioning would unblock them) or need new images registered.
4. **Most urgent todos** — a numbered list of 3-5 concrete next actions, sorted by urgency. Each item must be specific and actionable with a number attached:
    - "caption N more `Y`-labeled images (potential queue: P)"
    - "register / source N more images for label `Y` (potential queue exhausted)"
    - Not vague encouragement.
   Urgency rules:
    - **EMPTY > LOW > OK**.
    - Within the same status tier, prioritize concepts that have a **usable potential queue** (≥ ~10 labeled-not-done images ready to caption) — captioning unblocks them immediately. Concepts with `potential = 0` need upstream sourcing/labeling work, which is more expensive.
    - Within the captionable subset, prefer concepts with the largest gap to target (highest expected v1 contribution).
    - When a concept needs sourcing, suggest a number bounded by `target - done` so the user doesn't over-source.

Keep the report under ~60 lines. No additional context, no markdown headers beyond the tables.

## Access rights

read-only access to the db can be done w/o yes from user
