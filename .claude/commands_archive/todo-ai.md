---
description: Score every potential image by concept-deficit weighted by closeness-to-done and persist the ranked list to the `claude_todo` collection so the gradio "todo ai 20" button can read it. Concept map and targets come from the skin JSON.
argument-hint: "[skin (default: 1xlasm)] [set-name (default: skin.default_set or gts_v3)]"
---

Build a captioning-priority ranking for the chosen set under the chosen skin and persist it to MongoDB. The gradio app's "todo ai 20" button reads from this ranking; running this command refreshes it.

Args: `$ARGUMENTS` — first token is the skin name (default `1xlasm`), second is the set name (default = `skin.default_set` or `gts_v3`).

## Concept mapping

Concept names, match rules, and targets all come from `conf/skins/<skin>.json` under the `concepts` key. **Do not duplicate them here.** Iterate `skin.concepts` in declaration order.

## Scoring

For each non-prototype image in the set that is **labeled but NOT done** (i.e. each "potential" image — done = hints + labels_ng (or labels) + caption_joy + caption all non-empty):

1. **Applied labels for matching** — take `labels_ng` (FIELD_LABELS_NG) directly; if missing/empty, fall back to `compute_labels_ng(labels, skin)`. Both feed `skin.matched_concepts(...)`.
2. **Concept matches** — `skin.matched_concepts(applied_paths) -> {concept_name: bool}`. An image can match multiple concepts; residual handling is internal.
3. **Concept deficit** — first compute global per-concept `done` counts across the set (same matching). Then for each concept `c` matched by image `i`: `deficit_c = max(0, (target_c - done_c) / target_c)` where `target_c = skin.concepts[c].target`. Sum across matched concepts → `deficit_sum_i`.
4. **Closeness to done** — count how many of `hints`, `caption_joy`, `caption` are already non-empty (range 0..3; `labels`/`labels_ng` is non-empty by construction).
5. **Score** — `score_i = deficit_sum_i * (1 + 0.5 * closeness_i)`.

Drop images whose score is 0 (only matched OK concepts). Sort descending by score; tiebreak by closeness desc, then most-recent timestamp desc.

## Persist

Upsert one document into the `claude_todo` collection of the active `scenes_<config>` database:

```
{
  'kind': 'caption_priority',
  'set_name': <name>,
  'skin_name': <skin>,
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

Load skin and set:

```python
from ait.caption.skin import SkinRegistry
skin = SkinRegistry().get(skin_name)
target_set = set_arg or skin.default_set or 'gts_v3'
```

Use `SceneSetManager(config='prod')` and `set_from_id_or_name(target_set)`. Iterate `scene_set.imgs`; skip prototype images.

## Output

Print, in order:
1. One-line confirmation: `wrote N items to claude_todo for skin=<skin> set=<set>`.
2. Per-concept summary: `<concept>: done=<d>/<t> deficit=<deficit>` (one line each, in plan order).
3. Top-5 preview table: `rank | image_id | score | concepts | closeness`.

Keep total output under ~25 lines.

## Access rights

Read access to canonical collections + read/write to `claude_*` collections in the active scenes db can be done w/o yes from user.
