---
description: Score every potential image by concept-deficit weighted by closeness-to-done and persist the ranked list to the `claude_todo` collection so the gradio "todo ai 20" button can read it.
argument-hint: "[set-name (default: gts_v3)]"
---

Build a captioning-priority ranking for the set named `$ARGUMENTS` (default `gts_v3`) and persist it to MongoDB. The gradio app's "todo ai 20" button reads from this ranking; running this command refreshes it.

## Concept mapping

Identical to `.claude/commands/v1-status.md` (keep the two files in sync):

- `insertion` (target 200) — any label starting with `i_`
- `holding` (target 130) — `holding`
- `stepping` (target 130) — `step`
- `handjob` (target 130) — `handjob`, `teasing_hj`
- `blowjob` (target 130) — `blowjob`
- `masturbation` (target 130) — `masturbating`
- `general` (target 100) — labeled image with no themed match (and ignore real-side `b_*` for the "no match" decision)

Real concepts (`busty` / `fbb` / `leggy` / `hairy`) are deactivated.

## Scoring

For each non-prototype image in the set that is **labeled but NOT done** (i.e. each "potential" image — done = hints + labels + caption_joy + caption all non-empty):

1. **Concept matches** — apply the mapping above. An image can match multiple concepts (overlap fine). `general` only fires when no themed concept matches.
2. **Concept deficit** — first compute global per-concept `done` counts across the set (using the same matching). Then for each concept `c` matched by image `i`: `deficit_c = max(0, (target_c - done_c) / target_c)`. Sum across matched concepts → `deficit_sum_i`.
3. **Closeness to done** — count how many of `hints`, `caption_joy`, `caption` are already non-empty (range 0..3; `labels` is non-empty by construction).
4. **Score** — `score_i = deficit_sum_i * (1 + 0.5 * closeness_i)`.

Drop images whose score is 0 (only matched OK concepts). Sort descending by score; tiebreak by closeness desc, then most-recent timestamp desc.

## Persist

Upsert one document into the `claude_todo` collection of the active `scenes_<config>` database:

```
{
  'kind': 'caption_priority',
  'set_name': <name>,
  'generated_at': <utc datetime>,
  'version': 1,
  'concept_done': {<concept>: <int>, ...},
  'concept_deficits': {<concept>: <float>, ...},
  'items': [
    {'image_id': <str>, 'score': <float>, 'concepts': [<str>, ...], 'closeness': <int>},
    ...
  ]
}
```

Upsert key: `{'kind': 'caption_priority', 'set_name': <name>}`. Use `coll.update_one(query, {'$set': payload}, upsert=True)`. Direct collection access via `dbc._get_collection('claude_todo')` is the convention (see CLAUDE.md "Cross-cutting").

Cap the persisted list at 200 items — the gradio button only reads the top 20, but a longer tail is useful for diagnostics without bloating the doc.

## Setup

```
PYTHONPATH=src HOME_AIT=. CONF_AIT=./conf WORKSPACE=$HOME/Workspace AIDB_SCENE_CONFIG=prod AIDB_SCENE_DEFAULT=0000
```

Use `SceneSetManager(config='prod')` and `set_from_id_or_name(name)`. Iterate `scene_set.imgs`; skip prototype images.

## Output

Print, in order:
1. One-line confirmation: `wrote N items to claude_todo for set=<name>`.
2. Per-concept summary: `<concept>: done=<d>/<t> deficit=<deficit>` (one line each, in plan order).
3. Top-5 preview table: `rank | image_id | score | concepts | closeness`.

Keep total output under ~25 lines.

## Access rights

Read access to canonical collections + read/write to `claude_*` collections in the active scenes db can be done w/o yes from user.
