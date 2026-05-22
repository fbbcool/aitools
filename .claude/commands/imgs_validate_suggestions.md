---
description: Validate the /img_suggest process against curator-authored labels+hints on done images (used as ground truth). Picks N random done images, runs the suggestion loop on each with canonical fields hidden, compares the suggestion output to the curator's stored labels_ng + hints, reports aggregate metrics. Read-only by default.
argument-hint: "[count=N] [set=gts_v3] [iters=5] [persist=true|false] [force]"
---

`$ARGUMENTS` may contain optional `key=value` pairs:
- `count=N` (default `30`) — number of done images to sample
- `set=NAME` (default `gts_v3`) — which SceneSet to sample from
- `iters=N` (default `5`) — max iterations per image (matches `/img_suggest`)
- `persist=true|false` (default `false`) — if true, ALSO write the produced suggestions to the SceneImage's `_SUGGESTION` fields. Default false = pure read-only validation.
- `force` — bare flag. Bypass the **rating>=3 guard** (see below) so production-grade images can be written to when `persist=true`. Has no effect in the default read-only mode.

## Rating>=3 guard

The validation set is drawn from done images (rating>=1) — by design, rating>=3 images are part of the ground-truth pool. **The guard only applies when `persist=true`**: in that case, any sampled image with `rating>=3` is excluded from the write step (it still contributes to the read-only metrics computation, just nothing is persisted to its `_SUGGESTION` fields). Pass the bare `force` flag to allow `_SUGGESTION` writes on rating>=3 images. Default read-only mode (`persist=false`) is unaffected — no writes happen anywhere, so the guard is moot.

## Why this exists

The captioning workflow has a refinement loop driven by comparing `caption_joy` against curator-edited `caption` on done images. We need the same for the suggestion process: a way to *measure* whether the suggestion procedure is improving (or regressing) as we tune `1xlasm_suggestions.md`.

Curator-authored `labels_ng` and `hints` on done images function as **ground truth (with caveats — see plan)**: the curator decided which labels apply and observed the central interaction. The 119 done images in `gts_v3` (rating ≥ 1) are sufficient for a meaningful 30-image validation pass.

## Pipeline

### 1. Pick the test set

```python
from aidb import SceneDef, SceneManager
from aidb.scene.scene_set_manager import SceneSetManager
import random

scm = SceneManager(config='prod', verbose=0)
ssm = SceneSetManager(scm._dbc, scm, verbose=0)
s = ssm.set_from_id_or_name(set_name)

done = []
for img in s.imgs:
    if (img.rating or 0) < 1: continue
    if not (img.labels_ng or []): continue
    if not (img.data.get(SceneDef.FIELD_HINTS) or '').strip(): continue
    done.append(img)

random.seed(42)  # deterministic sampling across runs
sample = random.sample(done, min(count, len(done)))
```

### 2. Run suggestion on each (canonical hidden)

For each image:

```python
from ait.caption import joy_client
from ait.caption.skin import SkinRegistry

joy_client.ensure_running()
sk = SkinRegistry().get('1xlasm')

truth_labels = set(simg.labels_ng)
truth_hint   = (simg.data.get(SceneDef.FIELD_HINTS) or '').strip()

# Run the SAME judgment-driven probe loop as /img_suggest, but with
# canonical labels_ng / hints treated as empty regardless of DB state.
# Cap iterations per the `iters` arg.
state = {
    'labels_candidate': set(),
    'labels_dropped':   set(),
    'hint_fragments':   [],
    'iter_traces':      [],
}
for i in range(iters):
    probe = compose_probe(state, iteration=i+1, skin=sk)
    _, response = joy_client.caption(
        image_url=str(simg.url_from_data),
        user_content=probe,
        system_content=sk.directive,
    )
    new_labels, new_hints, notes = parse_response(response, state, skin=sk)
    state['iter_traces'].append({...})
    state['labels_candidate'] |= new_labels
    state['hint_fragments'].extend(new_hints)
    if i >= 1 and not new_labels and not new_hints:
        break

suggested_labels = high_confidence_subset(state['labels_candidate'], state['iter_traces'])
suggested_hint   = compose_hint_text(state['hint_fragments'], skin=sk)
iter_count       = len(state['iter_traces'])
```

If `persist=true`: also call `simg.set_labels_ng_suggestion(...)`, `simg.set_hints_suggestion(...)`, `simg.db_store()` — BUT apply the **rating>=3 guard** first: if `(simg.data.get(SceneDef.FIELD_RATING) or SceneDef.RATING_INIT) >= 3 and not force`, skip the write (record the image under a `skipped_rating>=3` bucket in the report). Default `persist=false` = nothing written.

### 3. Compute per-image metrics

```python
labels_intersect = set(suggested_labels) & truth_labels
labels_union     = set(suggested_labels) | truth_labels
precision = len(labels_intersect) / max(1, len(suggested_labels))
recall    = len(labels_intersect) / max(1, len(truth_labels))
f1        = 2 * precision * recall / max(1e-9, precision + recall)

# hint key-token overlap (semantic, not character-level)
truth_tokens     = content_tokens(truth_hint)     # ≥4 chars, exclude stopwords
suggested_tokens = content_tokens(suggested_hint)
hint_jaccard = len(truth_tokens & suggested_tokens) / max(1, len(truth_tokens | suggested_tokens))

# per-label-group breakdown (proximity/touch/insertion/pose/attribute/act)
per_group_precision_recall = breakdown_by_group(suggested_labels, truth_labels, skin=sk)
```

### 4. Aggregate

After all N images:

```python
metrics = {
    'n_images':        len(results),
    'mean_precision':  mean(r['precision'] for r in results),
    'mean_recall':     mean(r['recall']    for r in results),
    'mean_f1':         mean(r['f1']        for r in results),
    'mean_hint_jaccard': mean(r['hint_jaccard'] for r in results),
    'iter_distribution': {1: count_n_iter_1, ..., 5: count_n_iter_5},
    'per_group_recall':  {
        'primary.attribute': mean(...),
        'primary.pose':      mean(...),
        'primary.action':    mean(...),
        'secondary.attribute': mean(...),
        'secondary.pose':      mean(...),
        'secondary.action':    mean(...),
        'interaction.proximity': mean(...),
        'interaction.touch':     mean(...),
        'interaction.insertion': mean(...),
        'interaction.act':       mean(...),
    },
}
```

### 5. Report

Print under ~40 lines:

1. **header** — set, N images, iters cap, persist flag
2. **aggregate metrics** — table format with current numbers vs initial acceptance criteria (per `1xlasm_suggestions.md` §7)
3. **per-label-group recall** — table; flag groups below 0.60 with `XX`
4. **iter distribution** — how many images converged at iter 1, 2, 3, 4, 5
5. **outliers** — bottom 3 images by F1 (likely surface bias or mapping bugs); top 1 case where suggestion CORRECTLY surfaced a label the curator MISSED (the "curator-omitted labels" caveat from the plan)
6. **suggested MD refinements** — if any group is below target, point at the specific `1xlasm_suggestions.md` section (§3 probe templates, §5 mapping rules) that likely needs editing
7. one-line summary: `validate_suggestions n=N: f1=X, hint_jacc=Y, median_iter=Z, groups_below_target=[…]`

### 6. (Optional) Persist findings to the MD

If invoked with `persist=true`, also append a dated entry to `conf/skins/1xlasm_suggestions.md` §7 "Most recent validation run" with the metrics. This makes the validation results auditable across MD-refinement cycles.

## When to run

- After authoring or editing `1xlasm_suggestions.md` §3 (probe templates) or §5 (mapping rules) — confirm the change moved the targeted metric
- Periodically as the curator adds more done images (the test set grows)
- Before declaring `/img_suggest` ready for production use

## Access rights

Pure read by default (`persist=false`). With `persist=true`, writes to `_SUGGESTION` fields only — canonical fields never touched.

## See also

- `/img_suggest <id>` — the suggestion procedure under test.
- `1xlasm_suggestions.md` §7 — the validation methodology and current acceptance criteria.
- Plan file `/home/misw/.claude/plans/elegant-brewing-dawn.md` — full methodology, refinement-loop pattern, ground-truth caveats.
