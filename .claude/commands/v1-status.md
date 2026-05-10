---
description: Report v1 dataset progress for the Qwen-Image-Edit gts LoRA against the editable plan below.
argument-hint: "[set-name (default: gts_v3)]"
---

Report v1 dataset progress for the Qwen-Image-2512 gts LoRA. The set to inspect is `$ARGUMENTS` (default `gts_v3`).

Only **done** images count, in any set. **Done** = non-prototype, active image with non-empty `hints` AND non-empty `labels` AND non-empty `caption_joy` AND non-empty `caption`.

## V1 plan (edit me)

- **total target images:** 1000
- **lora rank:** 32

### Real concepts (DEACTIVATED — skip for now)

The four real concepts (`busty` / `fbb` / `leggy` / `hairy` SceneSets, 50 each) are part of the v1 plan but **deactivated** for the current report. Do not load any real sets, do not include real concepts in the tables, and do not include real-side todos in the urgency list. They will be reactivated later.

### GTS concepts (fixed)

The gts concept list is fixed. Labels are mapped onto concepts (not 1:1). An image counts toward **every** concept it matches; overlap is expected (e.g. a `holding` + `i_breasts_body` image counts for both `holding` and `insertion`). The `general` bucket is the residual: it fires only when a labeled image matches no other concept.

| concept       | target | matched by                                          |
|---------------|-------:|-----------------------------------------------------|
| insertion     |    200 | any label starting with `i_`                        |
| holding       |    130 | `holding`                                           |
| stepping      |    130 | `step`                                              |
| handjob       |    130 | `handjob`, `teasing_hj`                             |
| blowjob       |    130 | `blowjob`                                           |
| masturbation  |    130 | `masturbating`                                      |
| general       |    100 | non-prototype labeled image with NO match above     |

Insertion sub-concepts (informational only — no targets, just visibility into coverage of the umbrella):

| sub-concept | matched by         |
|-------------|--------------------|
| breasts     | `i_breasts_*`      |
| vagina      | `i_vagina_*`       |
| ass         | `i_ass_*`          |
| mouth       | `i_mouth_*`        |

Labels that match no concept and are not real-side `b_*` (e.g. `penis`, `man_front`, `hand`, `cum`, `panties`, `all4`, …) are anatomy/pose qualifiers — they do not define their own concept; they only contribute to `general` when no concept label is present on the same image.

For each concept, two counts matter:

- **done**: distinct images matching the concept that pass the full done filter (hints + labels + caption_joy + caption all non-empty).
- **labeled-not-done** ("potential"): non-prototype images matching the concept that are NOT yet done — the captioning queue waiting on this concept.

`done + potential` = total matched images for the concept. The done count is what trains; the potential count tells you how much runway exists before you'd need to source/register new images.

## Setup

Connect to prod with the env vars documented in CLAUDE.md:

```
PYTHONPATH=src HOME_AIT=. CONF_AIT=./conf WORKSPACE=$HOME/Workspace AIDB_SCENE_CONFIG=prod AIDB_SCENE_DEFAULT=0000
```

Use `SceneSetManager(config='prod')` and `set_from_id_or_name(name)` to load each set. Iterate `scene_set.imgs` and skip prototype images. Wrap each `set_from_id_or_name(...)` call in try/except so a missing real set yields 0 instead of an error.

## Compute

1. **Input set** — load the set named `$ARGUMENTS` (default `gts_v3`).
2. **Concept matching** — for each non-prototype image with at least one label, decide which fixed concepts it matches using the mapping table above. An image can match multiple concepts (no dedup across concepts). For each concept build `{done, potential}` where:
    - `done` = image matches the concept AND passes the full done filter.
    - `potential` = image matches the concept AND is not done.
   `general` matches when the image has at least one label but **none** of its labels map to a concept (and ignore real-side `b_*` labels when deciding whether anything matched — `b_*` does not by itself trigger `general`).
3. **Insertion sub-concepts** — additionally compute `{done, potential}` per sub-concept (`breasts`/`vagina`/`ass`/`mouth`) for the informational sub-table. These are not separate concepts and have no target.
4. **Distinct done total** — count distinct done images in the input set. This is the v1 dataset total for now (real subsets deactivated).

For each concept, compute progress against its target with a status flag:
- `OK` if `current >= target`
- `LOW` if `0.4 * target <= current < target`
- `EMPTY` if `current < 0.4 * target` (count of 0 is also EMPTY)

## Report

Output a compact status report:

1. **Header** — input set name, total target, rank, total done (gts only — real deactivated), percent toward total target.
2. **GTS concepts table** — columns: `concept`, `done`, `potential`, `target`, `%done`, `status`. One row per fixed concept (in plan order: insertion, holding, stepping, handjob, blowjob, masturbation, general). Don't sort; keep the plan order so the table reads the same on every run.
3. **Insertion sub-concepts table** — columns: `sub-concept`, `done`, `potential`. Rows: `breasts`, `vagina`, `ass`, `mouth`. Informational only (no target/status).
4. **Bottom-line takeaway** — one or two sentences naming the concepts at EMPTY/LOW, mentioning whether they have a usable potential queue (i.e. captioning would unblock them) or need new images registered.
5. **Most urgent todos** — a numbered list of 3-5 concrete next actions, sorted by urgency. Each item must be specific and actionable with a number attached:
    - "caption N more images for concept `Y` (potential queue: P)"
    - "register / source N more images for concept `Y` (potential queue exhausted)"
    - Not vague encouragement.
   Urgency rules:
    - **EMPTY > LOW > OK**.
    - Within the same status tier, prioritize concepts that have a **usable potential queue** (≥ ~10 labeled-not-done images ready to caption) — captioning unblocks them immediately. Concepts with `potential = 0` need upstream sourcing/labeling work, which is more expensive.
    - Within the captionable subset, prefer concepts with the largest gap to target (highest expected v1 contribution).
    - When a concept needs sourcing, suggest a number bounded by `target - done` so the user doesn't over-source.

Keep the report under ~60 lines. No additional context, no markdown headers beyond the tables.

## Access rights

read-only access to the db can be done w/o yes from user
