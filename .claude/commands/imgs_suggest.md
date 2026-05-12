---
description: Batch /img_suggest. Picks the newest active image from each scene that has no done image, restricted to images whose labels_ng_SUGGESTION AND hints_SUGGESTION are both empty, and runs the full suggestion loop on the top N. Never mutates canonical fields.
argument-hint: "[num]"
---

`$ARGUMENTS` is an optional positive integer `num` (default `20`). Anything else is rejected with a short error.

## Why this exists

Curators promote `_SUGGESTION` fields into canonical `labels_ng` / `hints` on review; suggestions need to exist first. `/img_suggest` does this per image, but the productive case is "fill in suggestions for the next N un-touched scenes so the curator can review a batch in the gradio UI". This command picks a sensible batch and runs `/img_suggest`'s pipeline on each.

The selection policy — one newest-active image per scene-without-done — spreads suggestion coverage across many scenes rather than burning the batch on N images from one well-populated scene. This is the same policy the prior ad-hoc `/tmp/suggest_batch_50.py` script used.

## Selection

```python
from aidb import SceneDef, SceneManager
from ait.caption.skin import SkinRegistry

scm = SceneManager(config='prod', verbose=0)
sm  = scm  # set manager
sim = scm.scene_image_manager()
sk  = SkinRegistry().get('1xlasm')

def is_done(img) -> bool:
    """v1-status done-rule: hints + labels_ng (or labels) + caption_joy + caption all non-empty,
    non-prototype, active. Mirrors `/v1-status` precisely."""
    if img.prototype:
        return False
    d = img.data
    if not (d.get(SceneDef.FIELD_HINTS) or '').strip():
        return False
    if not (d.get(SceneDef.FIELD_LABELS_NG) or d.get(SceneDef.FIELD_LABELS)):
        return False
    if not (d.get(SceneDef.FIELD_CAPTION_JOY) or '').strip():
        return False
    if not (d.get(SceneDef.FIELD_CAPTION) or '').strip():
        return False
    return True

def has_empty_suggestions(img) -> bool:
    return (not (img.labels_ng_suggestion or [])
            and not (img.hints_suggestion or '').strip())

candidates: list[tuple[int, object]] = []  # (timestamp_created, simg)
for scene in sm.scenes():
    imgs = list(scene.imgs)
    if any(is_done(i) for i in imgs):
        continue                                       # skip: scene has a done img
    # active = non-prototype; scene.imgs already filters excluded
    active = [i for i in imgs if not i.prototype]
    active = [i for i in active if has_empty_suggestions(i)]
    if not active:
        continue
    # newest active by timestamp_created desc
    active.sort(key=lambda i: -(i.data.get(SceneDef.FIELD_TIMESTAMP_CREATED) or 0))
    newest = active[0]
    candidates.append((newest.data.get(SceneDef.FIELD_TIMESTAMP_CREATED) or 0, newest))

candidates.sort(key=lambda t: -t[0])  # newest-image-first across scenes
batch = [simg for _, simg in candidates[:num]]
```

(Exact iterator over scenes is whatever `SceneManager` exposes — `scenes()` or
`coll.find({})` wrapped via `SceneManager.scene_from_data`. Pick whichever is
idiomatic to the codebase; the predicate logic above is the load-bearing part.)

If `len(batch) == 0` print `nothing to do — no scenes-without-done have an active image with empty suggestions.` and stop.

If `len(batch) < num` continue with what was found, and report the shortfall.

## Joy server

```python
from ait.caption import joy_client
joy_client.ensure_running()
```

GPU prereq: ≥16 GiB free for the server's startup. If `ensure_running` raises, surface the same "free the GPU" guidance as `/img_caption` Stage 2.

Pre-warming once amortizes the ~23s model load across the whole batch — at ~25-30s per image (5 probes × ~5s), N=20 takes ~10 minutes.

## Per-image processing

For each `simg` in `batch`, run **the full `/img_suggest` pipeline** verbatim (sections 2-4 of `.claude/commands/img_suggest.md`): iteration loop (max 5, converge early), final-suggestion composition, persist via `set_labels_ng_suggestion` / `set_hints_suggestion` + `db_store()`. Iter-5 uses the hint LoRA via `adapter='hint'` when `sk.lora_hint_path` is set.

`not-1xlasm-shape` images are skipped (no persist) and counted in the report; processing continues to the next image.

A per-image hard error (joy server crash, image fetch fails, etc.) is caught, logged with the image id, and the batch continues. The final report flags failures.

**Never** call `set_labels_ng`, `set_hints`, or `set_caption_*` on any image in the batch. Canonical fields are sacrosanct.

## Report

Print under ~40 lines:

1. **header** — `num` requested, `len(batch)` selected, scenes scanned, scenes-without-done count
2. **per-image one-liner table** — `<id>  iters=N  labels=N  hint=N chars  status=ok|not-1xlasm-shape|error`
3. one-line summary: `imgs_suggest <num>: ok=N, not_1xlasm=N, errors=N, total_seconds=N`

Per-image iteration traces are NOT printed here — only the summary line. For a deep trace, the curator can re-run `/img_suggest <id>` on any individual image.

## Re-running

Idempotent. Subsequent runs skip images that have non-empty `labels_ng_SUGGESTION` or `hints_SUGGESTION` (the "empty suggestions" filter excludes them), so the batch always picks fresh candidates.

## Access rights

Read access to canonical collections + write to `FIELD_LABELS_NG_SUGGESTION` / `FIELD_HINTS_SUGGESTION` only. Batch can take ~10+ minutes and holds ~16 GiB VRAM; ask before starting if the GPU is contested or a curator session is in progress.

## See also

- `/img_suggest <id>` — single-image variant; reuse for deep per-image traces.
- `/joy_server start|stop|status` — explicit server lifecycle (worth pre-warming before a large batch).
- `/imgs_validate_suggestions count=N` — validate the suggestion process against done images as ground truth.
