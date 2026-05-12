---
description: Caption curated images whose caption_joy is stale wrt caption_prompt. Default: caption_prompt non-empty AND (caption_joy empty OR ts_caption_prompt > ts_caption_joy). With `force`: every curated image with a non-empty caption_prompt, regardless of freshness. Curated = non-empty labels_ng AND non-empty hints AND non-empty suggestion. Uses the STORED caption_prompt verbatim (Stage 1 is a no-op); Stage 2 captions via joy_server; Stage 3 validates + auto-fixes. Upstream is /imgs_caption_prompt.
argument-hint: "[force] [set=<name> | rating[==|>=|<=|>|<]<n> | limit=<n> | …]"
---

`$ARGUMENTS` is an optional space-separated list of bare-word flags and `key=value` / `key<op>value` filter terms (connectives like `for` / `and` / `where` ignored). Empty → all curated images with a non-empty `caption_prompt` and stale `caption_joy`, DB-wide. Supported terms:

- `force` — bare flag. Caption every curated image with a non-empty `caption_prompt` regardless of `caption_joy` freshness (the recency check is skipped). Useful after a captioner refresh (LoRA swap, skin rule change) when every existing caption should be regenerated against the current prompts.
- `set=<name>` — restrict to a SceneSet's active members.
- `rating==<n>` / `rating=<n>` / `rating>=<n>` / `rating<=<n>` / `rating><n>` / `rating<<n>` — relational rating filter.
- `limit=<n>` — cap the batch at N images (default unlimited). Use when the pending list is large and the curator wants to review the first batch before continuing.

`force` composes with the other filters — e.g. `force set=gts_v3 limit=10` recaptions the 10 newest curated images in `gts_v3` whether or not their captions were already fresh.

**A curated image with an EMPTY `caption_prompt` is NEVER in scope** — even with `force`. Run `/imgs_caption_prompt` first to compile the prompt; that's this command's upstream. The report counts and lists such images so the curator knows.

Same parser as `/imgs_update_caption_prompt`, extended with the `force` bare-word flag. A 24-char ObjectId is NOT a valid argument — use `/img_caption <id>` for single-image work.

## Why this exists

This command sits **downstream of `/imgs_caption_prompt`** in the curator workflow:

```
/imgs_suggest            — Claude probes joy, writes _SUGGESTION fields
  ↓ curator review + promote
/imgs_caption_prompt     — judgment-mode caption_prompt compile for curated imgs
  ↓
/imgs_caption_joy            — this command: caption + validate+fix using the stored prompt
```

"Curated" is shorthand for **labels_ng AND hints AND suggestion all non-empty** — the curator has finished labeling and the suggestion fields remain as the provenance signal. The recency check then narrows to images whose `caption_joy` is older than the current `caption_prompt` (or empty).

The Stage 1 prompt-compile work is **already done by `/imgs_caption_prompt`** and stored in `FIELD_CAPTION_PROMPT`. This command uses that stored prompt verbatim — no recompose, no overwrite. That way the high-quality judgment-mode prompts are preserved.

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
    """Curated AND non-empty caption_prompt AND caption_joy is stale wrt caption_prompt.
    With force=True: only the recency check is skipped — curated + non-empty prompt
    are still required.
    """
    if not is_curated(img):
        return False
    d = img.data
    cap_prompt = (d.get(SceneDef.FIELD_CAPTION_PROMPT) or '').strip()
    if not cap_prompt:
        return False                     # upstream is /imgs_caption_prompt
    if force:
        return True
    cap_joy = (d.get(SceneDef.FIELD_CAPTION_JOY) or '').strip()
    if not cap_joy:
        return True                      # never captioned → in scope
    ts_cp = d.get(SceneDef.FIELD_TIMESTAMP_CAPTION_PROMPT) or 0
    ts_cj = d.get(SceneDef.FIELD_TIMESTAMP_CAPTION_JOY) or 0
    return ts_cp > ts_cj
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

Separately, count curated images that have an **empty `caption_prompt`** — these are NOT processed but the count is shown in the header so the curator knows to run `/imgs_caption_prompt` upstream.

If `len(pending) == 0`, print `nothing to do — no curated images have stale caption_joy wrt caption_prompt` (or `nothing to do — no curated images with a non-empty caption_prompt match the filters` in `force` mode) and stop.

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

### Stage 1 — use the stored caption_prompt (no recompose)

The selection filter guarantees `caption_prompt` is non-empty for every pending image — `/imgs_caption_prompt` (the upstream) has already done the Stage 1 work and stored the judgment-mode prompt. This command **reads it verbatim from the DB and forwards it to Stage 2**. No recompose, no overwrite — that protects the judgment-mode quality.

(For images without a stored prompt, the filter excludes them so the curator runs `/imgs_caption_prompt` first.)

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

`/imgs_caption_joy` typically processes 5-50 images. Total time = ~30s startup + N × (~5s prompt + ~5s caption + ~1s validate) ≈ 30s + N×11s. For N>5, run with `run_in_background: true` — the user will be notified on completion.

## Report

Print under ~30 lines:

1. **header** — filters applied, `len(pending)` images selected, plus a separate count of curated-but-no-prompt images that were skipped (with a hint to run `/imgs_caption_prompt` for them)
2. **per-image one-liner table** — `<id>  prompt=N chars  caption=N chars  fixes=[…]  status=clean|flagged|error`
3. one-line summary: `imgs_caption [filters: …]: ok=N, flagged=N, errors=N, skipped_no_prompt=N, total_seconds=N`

## Re-running

Idempotent. After a successful run, each captioned image's `timestamp_caption_joy` advances past its `timestamp_caption_prompt` and the image is excluded on the next default-mode run. `force` mode keeps re-captioning regardless.

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION` / `FIELD_CAPTION_JOY` / `FIELD_CAPTION_PROMPT` (scoped to images matching the curator-pending filter) can be done w/o yes from user. Captioning consumes ~16 GiB VRAM for the duration of the batch; ask before starting if the GPU is contested.

## See also

- `/img_caption <id>` — single-image variant; runs Stage 1 (judgment) + Stage 2 + Stage 3 for one image.
- `/imgs_caption_prompt` — the immediate upstream — produces the tight judgment-mode prompts this command then consumes.
- `/imgs_suggest [num]` — populates the `_SUGGESTION` fields that gate "curated".
- `/imgs_update_caption_joy` / `/imgs_validate_captions` — the lower-level batch steps bundled by Stage 2 + Stage 3.
