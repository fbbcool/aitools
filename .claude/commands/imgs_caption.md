---
description: Caption curated images in batch. Default: only those whose caption_joy is stale (suggestion newer than caption_joy, or caption_joy empty). With `force`: every curated image regardless of freshness. Curated = non-empty labels_ng AND non-empty hints AND non-empty suggestion. Runs the full /img_caption pipeline (compile prompt → caption → validate+fix) on each match.
argument-hint: "[force] [set=<name> | rating[==|>=|<=|>|<]<n> | limit=<n> | …]"
---

`$ARGUMENTS` is an optional space-separated list of bare-word flags and `key=value` / `key<op>value` filter terms (connectives like `for` / `and` / `where` ignored). Empty → all curated images with stale `caption_joy`, DB-wide. Supported terms:

- `force` — bare flag. Caption every curated image regardless of `caption_joy` freshness (the default-mode recency check is skipped). Useful after a captioner refresh (LoRA swap, skin rule change) when every existing caption should be regenerated.
- `set=<name>` — restrict to a SceneSet's active members.
- `rating==<n>` / `rating=<n>` / `rating>=<n>` / `rating<=<n>` / `rating><n>` / `rating<<n>` — relational rating filter.
- `limit=<n>` — cap the batch at N images (default unlimited). Use when the pending list is large and the curator wants to review the first batch before continuing.

`force` composes with the other filters — e.g. `force set=gts_v3 limit=10` recaptions the 10 newest curated images in `gts_v3` whether or not their captions were already fresh.

Same parser as `/imgs_update_caption_prompt`, extended with the `force` bare-word flag. A 24-char ObjectId is NOT a valid argument — use `/img_caption <id>` for single-image work.

## Why this exists

The `/imgs_suggest` → curator-review → caption loop produces a steady stream of images that "just became ready". They have:

- a `_SUGGESTION` exists (Claude ran `/img_suggest` or `/imgs_suggest`)
- canonical `labels_ng` + `hints` are populated (curator promoted the suggestion fields, possibly with edits)
- but `caption_joy` is empty or older than the curator's promotion

"Curated" in this command's name is shorthand for the three-conjunct predicate: **suggestion AND hint AND labels are all non-empty**. The recency check then narrows it to the images that actually need a new caption.

This command captures exactly that cohort and runs the full `/img_caption` pipeline (Stage 1 prompt compile + Stage 2 captioner + Stage 3 validate-and-fix) on each. It's the batch counterpart of `/img_caption` for the "curator just finished reviewing N images" case.

The selection key is the **suggestion timestamp**, not `caption_prompt`. The curator may not have re-run `/imgs_update_caption_prompt` after promoting; that's fine — Stage 1 in this command compiles a fresh prompt deterministically (bulk-mode recipe, no per-image judgment).

## Selection filter

For every non-prototype image:

```python
def is_curated(img) -> bool:
    """Curated = suggestion AND hint AND labels are all non-empty."""
    d = img.data
    has_labels = bool(d.get(SceneDef.FIELD_LABELS_NG) or [])
    has_hint   = bool((d.get(SceneDef.FIELD_HINTS) or '').strip())
    has_sugg   = bool(d.get(SceneDef.FIELD_LABELS_NG_SUGGESTION) or []) \
              or bool((d.get(SceneDef.FIELD_HINTS_SUGGESTION) or '').strip())
    return has_labels and has_hint and has_sugg


def is_curated_pending(img, *, force: bool = False) -> bool:
    """Default: curated AND suggestion is newer than caption_joy (or caption_joy empty).
    With force=True: curated, regardless of caption_joy freshness."""
    if not is_curated(img):
        return False
    if force:
        return True
    d = img.data
    ts_sugg = max(
        d.get(SceneDef.FIELD_TIMESTAMP_LABELS_NG_SUGGESTION) or 0,
        d.get(SceneDef.FIELD_TIMESTAMP_HINTS_SUGGESTION) or 0,
    )
    if ts_sugg <= 0:
        return False
    cap_joy = (d.get(SceneDef.FIELD_CAPTION_JOY) or '').strip()
    if not cap_joy:
        return True
    ts_cap = d.get(SceneDef.FIELD_TIMESTAMP_CAPTION_JOY) or 0
    return ts_sugg > ts_cap
```

The "curator promoted" signal is implicit: the curator's promotion of `_SUGGESTION` → canonical bumps neither timestamp, but the curator typically *also* re-runs `/img_suggest` if they want to refine — in practice, an image with canonical labels_ng+hints populated AND a suggestion newer than the last caption is exactly the cohort we want. (If the curator promoted without re-running suggest, `ts_sugg` predates the promotion and may be older than `caption_joy`; that image is excluded — a deliberate trade-off to avoid re-captioning images the curator hasn't actively flagged as ready.)

## Argument parser

```python
import re
TERM_RE = re.compile(r'(\w+)\s*(==|>=|<=|=|>|<)\s*(\S+)')
WORD_RE = re.compile(r'\b(force)\b', re.IGNORECASE)

def parse_args(s: str):
    s = (s or '').strip()
    filters: dict = {}
    limit: int | None = None
    force = bool(WORD_RE.search(s))
    for kw, op, val in TERM_RE.findall(s):
        op = '==' if op == '=' else op
        if kw == 'rating':
            filters[('rating', op)] = int(val)
        elif kw == 'set':
            filters[('set', op)] = val
        elif kw == 'limit':
            limit = int(val)
    return filters, limit, force
```

## Iterator

- `('set', '==')` present → load `SceneSetManager(...).set_from_id_or_name(value)` and iterate `scene_set.imgs`, skipping `excluded_ids`.
- Else → iterate `coll.find({prototype: {$ne: true}}, …)`.

For each candidate: apply `is_curated_pending(img, force=force)` AND remaining filters (e.g. `rating`). Sort the pending list by `timestamp_created` descending (newest first) so a `limit=N` slice picks the most recently created images. Apply `limit` if set. Collect matching ids into `pending`.

If `len(pending) == 0`, print `nothing to do — no curated images have stale caption_joy` (or `nothing to do — no curated images match the filters` in `force` mode) and stop.

## Pipeline

GPU prereq: ≥16 GiB free. If not, ask the user to free the device.

```python
from ait.caption import joy_client
from ait.caption.skin import SkinRegistry
from aidb import SceneDef

joy_client.ensure_running()
sk = SkinRegistry().get('1xlasm')
```

For each `iid` in `pending`:

### Stage 1 — deterministic prompt compile

Use the **bulk-mode recipe from `/imgs_update_caption_prompt`** (the deterministic, non-judgment one). Compose `default_prompt + opener + hint_section + label_prompts + constraints + closer`, persist via `simg.set_caption_prompt(p) + simg.db_store()`.

Per-image judgment compose (the `/img_caption` Stage 1 path) is intentionally NOT used here — composing N tight prompts by hand is impractical at batch scale. The deterministic recipe is the documented fallback for batch operation.

### Stage 2 — caption

```python
stored_prompt = (simg.data.get(SceneDef.FIELD_CAPTION_PROMPT) or '').strip()
prompt, caption = joy_client.caption(
    image_url=str(simg.url_from_data),
    user_content=stored_prompt,
    system_content=sk.directive,
)
if not caption:
    record_failure(iid, 'no caption returned'); continue
simg.set_caption_joy(caption)
simg.db_store()
```

### Stage 3 — validate + auto-fix

Reuse the single-image audit-and-fix pipeline from `/imgs_validate_captions`. Mechanically tractable categories (naked-multi, body-type, opener, forbidden vocab) auto-fix. Missing-trigger is flagged only.

If a fix is applied, persist `simg.set_caption_joy(fixed)`. When `FIELD_CAPTION` was identical to `FIELD_CAPTION_JOY` before Stage 2, also update `set_caption(fixed)` so the manual caption stays in sync.

## Background mode

`/imgs_caption` typically processes 5-50 images. Total time = ~30s startup + N × (~5s prompt + ~5s caption + ~1s validate) ≈ 30s + N×11s. For N>5, run with `run_in_background: true` — the user will be notified on completion.

## Report

Print under ~30 lines:

1. **header** — filters applied, `len(pending)` images selected
2. **per-image one-liner table** — `<id>  prompt=N chars  caption=N chars  fixes=[…]  status=clean|flagged|error`
3. one-line summary: `imgs_caption [filters: …]: ok=N, flagged=N, errors=N, total_seconds=N`

## Re-running

Idempotent. After a successful run, each captioned image's `timestamp_caption_joy` advances past its suggestion timestamps and the image is excluded on the next run.

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION` / `FIELD_CAPTION_JOY` / `FIELD_CAPTION_PROMPT` (scoped to images matching the curator-pending filter) can be done w/o yes from user. Captioning consumes ~16 GiB VRAM for the duration of the batch; ask before starting if the GPU is contested.

## See also

- `/img_caption <id>` — single-image variant with judgment-mode Stage 1; reuse for one-off recaptions or when the deterministic prompt isn't tight enough.
- `/imgs_suggest [num]` — the upstream that populates the `_SUGGESTION` fields this command then waits for.
- `/imgs_update_caption_prompt` / `/imgs_update_caption_joy` / `/imgs_validate_captions` — the lower-level batch steps this command bundles.
