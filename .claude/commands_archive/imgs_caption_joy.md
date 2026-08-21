---
description: Caption curated images whose caption_joy is stale wrt caption_prompt. Default: caption_prompt non-empty AND (caption_joy empty OR ts_caption_prompt > ts_caption_joy). With `force`: every curated image with a non-empty caption_prompt, regardless of freshness. With `ignore_curated`: drop the suggestion requirement, accept any image with non-empty labels_ng + hints + caption_prompt (legacy / non-curator-promoted cohort). Curated = non-empty labels_ng AND non-empty hints AND non-empty suggestion. Uses the STORED caption_prompt verbatim (Stage 1 is a no-op); Stage 2 captions via joy_server; Stage 3 validates + auto-fixes. Upstream is /imgs_caption_prompt.
argument-hint: "[force] [ignore_curated] [set=<name> | rating[==|>=|<=|>|<]<n> | skin=<name> | limit=<n> | …]"
---

`$ARGUMENTS` is an optional space-separated list of bare-word flags and `key=value` / `key<op>value` filter terms (connectives like `for` / `and` / `where` ignored). Empty → all curated images with a non-empty `caption_prompt` and stale `caption_joy`, DB-wide. Supported terms:

- `force` — bare flag. Caption every eligible image with a non-empty `caption_prompt` regardless of `caption_joy` freshness (the recency check is skipped) AND bypass the **rating>=3 guard** (see below) so production-grade images are included. Useful after a captioner refresh (LoRA swap, skin rule change) when every existing caption should be regenerated against the current prompts.
- `ignore_curated` — bare flag. Drop the suggestion-non-empty requirement. Eligibility becomes "labels_ng non-empty AND hints non-empty AND caption_prompt non-empty". Mirrors the `/imgs_caption_prompt ignore_curated` flag — needed when that upstream was used to compile prompts for non-curator-promoted images (legacy data, manual labels+hints without `_SUGGESTION`).
- `set=<name>` — restrict to a SceneSet's active members.
- `rating==<n>` / `rating=<n>` / `rating>=<n>` / `rating<=<n>` / `rating><n>` / `rating<<n>` — relational rating filter.
- `skin=<name>` — which skin (and matching joy_server skin) to caption with. Default `1xlasm`. Drives `SkinRegistry().get(skin)` for directive + Stage-3 validators, and `joy_client.ensure_running(skin=skin)` (auto-restarts the server if a different skin is currently loaded). Not a row filter.
- `limit=<n>` — cap the batch at N images (default unlimited). Use when the pending list is large and the curator wants to review the first batch before continuing.

Flags compose with the filters — e.g. `force set=gts_v3 limit=10` recaptions the 10 newest curated images in `gts_v3` whether or not their captions were already fresh; `ignore_curated rating==0` captions the rating-0 cohort regardless of suggestion provenance.

**Single-image mode**: if `$ARGUMENTS` is (or contains) a 24-char hex MongoDB ObjectId (regex `^[0-9a-f]{24}$`), the command processes just that image. The eligibility filter (`is_curated` / `is_labeled`) is **skipped** — the curator named it explicitly. The freshness check is also skipped (single-image = implicit `force`). The **rating>=3 guard is also bypassed** in single-image mode for the same reason. The non-empty-`caption_prompt` precondition still applies (Stage 2 needs a prompt to forward to joy_server); if `caption_prompt` is empty, abort with `caption_prompt is empty — run /imgs_caption_prompt or /imgs_update_caption_prompt first`.

## Rating>=3 guard

Images with `rating>=3` are treated as production-grade — by default they are **skipped** in batch mode to prevent accidental re-captioning of curator-finalized images. To process them, pass the bare `force` flag. Single-image ObjectId mode is an implicit force for this guard.

**An eligible image with an EMPTY `caption_prompt` is NEVER in scope** — even with `force` or `ignore_curated`. Run `/imgs_caption_prompt` first to compile the prompt; that's this command's upstream. The report counts and lists such images so the curator knows.

Same parser as `/imgs_update_caption_prompt`, extended with the `force` and `ignore_curated` bare-word flags and bare-ObjectId single-image mode.

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


def is_labeled(img) -> bool:
    """Labeled = labels_ng AND hints non-empty (suggestion ignored)."""
    d = img.data
    return bool(d.get(SceneDef.FIELD_LABELS_NG) or []) \
        and bool((d.get(SceneDef.FIELD_HINTS) or '').strip())


def is_curated_pending(img, *, force: bool = False,
                              ignore_curated: bool = False) -> bool:
    """Eligible image AND non-empty caption_prompt AND caption_joy is stale wrt caption_prompt.

    Eligibility:
      - default: is_curated(img)
      - ignore_curated=True: is_labeled(img)   (no suggestion required)

    With force=True the recency check AND the rating>=3 guard are both
    skipped — eligibility + non-empty caption_prompt are still required.
    """
    if ignore_curated:
        if not is_labeled(img):
            return False
    else:
        if not is_curated(img):
            return False
    d = img.data
    cap_prompt = (d.get(SceneDef.FIELD_CAPTION_PROMPT) or '').strip()
    if not cap_prompt:
        return False                     # upstream is /imgs_caption_prompt
    # rating>=3 guard — production-grade images require explicit `force`
    if (d.get(SceneDef.FIELD_RATING) or SceneDef.RATING_INIT) >= 3 and not force:
        return False
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
ID_RE    = re.compile(r'\b([0-9a-f]{24})\b')
TERM_RE  = re.compile(r'(\w+)\s*(==|>=|<=|=|>|<)\s*(\S+)')
FORCE_RE = re.compile(r'\bforce\b', re.IGNORECASE)
IGN_RE   = re.compile(r'\bignore_curated\b', re.IGNORECASE)

def parse_args(s: str):
    s = (s or '').strip()
    image_id: str | None = None
    m = ID_RE.search(s)
    if m:
        image_id = m.group(1)
    filters: dict = {}
    limit: int | None = None
    force = bool(FORCE_RE.search(s))
    ignore_curated = bool(IGN_RE.search(s))
    for kw, op, val in TERM_RE.findall(s):
        op = '==' if op == '=' else op
        if kw == 'rating':
            filters[('rating', op)] = int(val)
        elif kw == 'set':
            filters[('set', op)] = val
        elif kw == 'limit':
            limit = int(val)
    return image_id, filters, limit, force, ignore_curated
```

If `image_id` is set, jump straight to single-image mode (below); the
other filters/flags are ignored.

## Iterator

- `image_id` set (single-image mode) → `pending = [sim.img_from_id(image_id)]`. Skip the eligibility/freshness check; require only that `caption_prompt` is non-empty. If empty, abort with `caption_prompt is empty — run /imgs_caption_prompt or /imgs_update_caption_prompt first`.
- `('set', '==')` present → load `SceneSetManager(...).set_from_id_or_name(value)` and iterate `scene_set.imgs`, skipping `excluded_ids`.
- Else → iterate `coll.find({prototype: {$ne: true}}, …)`.

For each candidate (batch modes): apply `is_curated_pending(img, force=force, ignore_curated=ignore_curated)` AND remaining filters (e.g. `rating`). Sort the pending list by `timestamp_created` descending (newest first) so a `limit=N` slice picks the most recently created images. Apply `limit` if set. Collect matching ids into `pending`.

Separately, count eligible images (curated or labeled, depending on flag) that have an **empty `caption_prompt`** — these are NOT processed but the count is shown in the header so the curator knows to run `/imgs_caption_prompt` upstream.

If `len(pending) == 0`, print `nothing to do — no <scope> images have stale caption_joy wrt caption_prompt` where `<scope>` is "curated" (default) or "labeled" (`ignore_curated`); `force` mode swaps "stale caption_joy" for "match the filters". Then stop.

## Pipeline

GPU prereq: ≥16 GiB free. If not, ask the user to free the device.

```python
from ait.caption import joy_client
from ait.caption.skin import SkinRegistry
from aidb import SceneDef

joy_client.ensure_running(skin=skin)   # `skin` is the parsed arg, default '1xlasm'
sk = SkinRegistry().get(skin)
```

For each `iid` in `pending`:

### Stage 1 — use the stored caption_prompt (no recompose)

The selection filter guarantees `caption_prompt` is non-empty for every pending image — `/imgs_caption_prompt` (the upstream) has already done the Stage 1 work and stored the judgment-mode prompt. This command **reads it verbatim from the DB and forwards it to Stage 2**. No recompose, no overwrite — that protects the judgment-mode quality.

(For images without a stored prompt, the filter excludes them so the curator runs `/imgs_caption_prompt` first.)

### Stage 2 — caption

The captioning call goes through `JoySceneDB.caption_image` (server-backed when joy_server is up). That path already writes one `caption_log` entry per image — stage tag `caption_joy`, including the user prompt, a skin reference (name + source hash, not the full directive), the response caption, and elapsed seconds. If you bypass it and call `joy_client.caption()` directly, also call `ait.caption.caption_log.log_joy_call(simg, stage='caption_joy', ...)` so the trail is consistent across paths.

Before Stage 2 runs, call `ait.caption.caption_log.start_run(simg, run_tag='imgs_caption_joy')` to clear any prior trail and stamp a `run_start` marker. (This protects against conflating two independent /imgs_caption runs on the same image.)

```python
from ait.caption import caption_log

caption_log.start_run(simg, run_tag='imgs_caption_joy')

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

# Manual log path (only if you bypassed JoySceneDB.caption_image):
caption_log.log_joy_call(
    simg, stage='caption_joy',
    user_content=stored_prompt, skin=sk,
    response_caption=caption,
    elapsed_seconds=elapsed,
)
```

### Stage 3 — validate + auto-fix

Reuse the single-image audit-and-fix pipeline from `/imgs_validate_captions`. Mechanically tractable categories (naked-multi, body-type, opener, forbidden vocab) auto-fix. Missing-trigger is flagged only.

Bracket the audit with two `caption_log` entries: `audit_before` (the caption as it came out of Stage 2 plus the flag set you ran against it) and `audit_after` (the post-fix caption plus the list of fix labels applied). The two entries form the audit diff in the persisted log.

```python
caption_log.log_audit(
    simg, when='audit_before',
    caption=caption,
    violations=skin_violations,
    body_warnings=body_warnings,
    missing_triggers=missing_triggers,
    extra_flags={'pose_mandate_present': pose_present, 'naked_attributions': naked_attrs},
)

fixed = run_auto_fixes(caption)        # mechanical fixes

caption_log.log_audit(
    simg, when='audit_after',
    caption=fixed,
    violations=skin_violations_after,
    body_warnings=body_warnings_after,
    missing_triggers=missing_triggers_after,
    fixes_applied=fix_labels,
)
```

If any probe round-trips through joy_server are added in the future (Stage 3.5 visual audit), call `caption_log.log_joy_call(simg, stage='audit_probe', ...)` for each — same shape as Stage 2's entry.

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
