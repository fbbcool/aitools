---
description: Run the per-image judgment-mode caption_prompt compile (the same Stage 1 as /img_caption) on curated images. Default: only those whose caption_prompt is out of date (suggestion newer than caption_prompt, or caption_prompt empty). With `force`: every curated image regardless of freshness. Curated = non-empty labels_ng AND non-empty hints AND non-empty suggestion. Produces tight ~400-1000 char prompts, NOT the ~5000 char deterministic kind. Persists FIELD_CAPTION_PROMPT only; downstream /imgs_update_caption_joy picks them up.
argument-hint: "[force] [set=<name> | rating[==|>=|<=|>|<]<n> | limit=<n> | …]"
---

`$ARGUMENTS` is an optional space-separated list of bare-word flags and `key=value` / `key<op>value` filter terms (connectives like `for` / `and` / `where` ignored). Empty → all curated images with stale `caption_prompt`, DB-wide. Supported terms:

- `force` — bare flag. Process every curated image regardless of `caption_prompt` freshness (the default-mode recency check is skipped). Useful after a prompt-compile-recipe edit when the curator wants every existing prompt rebuilt.
- `set=<name>` — restrict to a SceneSet's active members.
- `rating==<n>` / `rating=<n>` / `rating>=<n>` / `rating<=<n>` / `rating><n>` / `rating<<n>` — relational rating filter.
- `limit=<n>` — cap the batch at N images (default unlimited). Use when the pending list is large and the curator wants to review the first batch before continuing.

`force` composes with the other filters — e.g. `force set=gts_v3 limit=10` rebuilds prompts for the first 10 curated images in `gts_v3` whether or not they have a current caption_prompt.

Same parser as `/imgs_update_caption_prompt`, extended with the `force` bare-word flag. A 24-char ObjectId is NOT a valid argument — use `/img_caption <id>` (which runs all three stages) or `/imgs_update_caption_prompt <id>` (single-image, Stage 1 only).

## Why this exists

`/imgs_caption` does end-to-end Stage 1+2+3 in one shot, but its Stage 1 uses the **deterministic** recipe (mechanical concat of all label expansions + every constraint, ~5000 chars). That trades narrative quality for batch throughput — observed in production as elevated `naked_multi` and `photo_filler` fix counts because the prompt doesn't tailor to the image.

This command is the high-quality alternative: it runs the **judgment-mode** Stage 1 (the per-image hand-crafted ~400-1000 char prompt from `/img_caption` Stage 1) for the same cohort, but only Stage 1. The curator then runs `/imgs_update_caption_joy` to caption and `/imgs_validate_captions` to fix.

The cost is **Claude's context window** — each judgment compile reads the skin's `theme_md` briefing and reasons about the specific image's hint, archetype, anti-patterns, and label set. For N images this is ~N×~15-30 seconds of my thinking + several thousand tokens per image. Run with `limit=<n>` (e.g. 5-10) when context budget is a concern; the same command can be re-invoked later to handle the rest.

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


def is_prompt_compile_pending(img, *, force: bool = False) -> bool:
    """Default: curated AND suggestion is newer than caption_prompt (or caption_prompt empty).
    With force=True: curated, regardless of caption_prompt freshness."""
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
    cap_prompt = (d.get(SceneDef.FIELD_CAPTION_PROMPT) or '').strip()
    if not cap_prompt:
        return True
    ts_cp = d.get(SceneDef.FIELD_TIMESTAMP_CAPTION_PROMPT) or 0
    return ts_sugg > ts_cp
```

The filter mirrors `/imgs_caption` exactly except the timestamp compared against is `caption_prompt`, not `caption_joy`. Result: images that have been suggested-then-curated but whose stored caption_prompt is stale (or empty).

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

For each candidate: apply `is_prompt_compile_pending(img, force=force)` AND remaining filters (e.g. `rating`). Sort the pending list by `timestamp_created` descending (newest first) so a `limit=N` slice picks the most recently created images. Apply `limit` if set.

If `len(pending) == 0`, print `nothing to do — no curated images have stale caption_prompt` (or `nothing to do — no curated images match the filters` in `force` mode) and stop.

If `len(pending) > 0`, print the count and the first ~5 ids before starting so the curator knows what's about to be processed.

## Per-image pipeline (judgment mode, repeated N times)

For each `iid` in `pending`, run the **`/img_caption` Stage 1 recipe verbatim** (see `.claude/commands/img_caption.md` step 1 and `.claude/commands/imgs_update_caption_prompt.md` "Per-image mode" steps 1-6):

1. Pull `labels_ng` + `hints` from the SceneImage. If `hints == 'none'` (case-insensitive), use the label-driven compose path.
2. Read `Skin('1xlasm').theme_md`. This is the primary briefing — archetypes, anti-patterns, captioner quirks, hint-spine workflow (§4.1).
3. Identify scene archetype (MD §3.2), anti-patterns at risk for this image (MD §5), captioner quirks to guard against (MD §6).
4. Hand-craft a tight prompt (~400-1000 chars) using the hint-threading pattern (verbatim vs prefused per MD §4.1 heuristic). Apply `skin.render_label_prompts(labels_ng)` as a candidate set, dropping label expansions the hint already covers.
5. Persist via `simg.set_caption_prompt(p) + simg.db_store()`. This bumps `timestamp_caption_prompt` past the suggestion timestamps, removing this image from future runs of this command.
6. Record a one-line trace: image id, char count, MD sections that informed it.

This is the *expensive* step. Each image consumes my context and tokens for judgment work — there is no Python shortcut.

If a single image fails (image not found, labels empty, judgment errors), record the failure and continue to the next.

## Report

Print under ~40 lines total:

1. **header** — filters applied, `len(pending)` images selected, `limit=N` if set
2. **per-image one-liner table** — `<id>  chars=N  archetype=X  pattern=verbatim|prefused  notes=…`
3. one-line summary: `imgs_caption_prompt [filters: …]: ok=N, errors=N`

Detailed per-image traces (the actual composed prompts) are NOT printed here — they're persisted in the DB and visible via `/img_caption <id>` re-run or direct DB inspection. The slash command stays compact even for N=20.

## Re-running

Idempotent. After a successful run, each image's `timestamp_caption_prompt` advances past its suggestion timestamps and the image is excluded on the next invocation — unless `/img_suggest` is re-run on it (which would bump suggestion timestamps again).

The typical sequence is:

```
/imgs_suggest [num]                  # populates _SUGGESTION fields
  ↓ curator review + promote
/imgs_caption_prompt         # this command — high-quality Stage 1
  ↓ Stage 2+3
/imgs_update_caption_joy             # picks up newly-fresh caption_prompts, runs joy
/imgs_validate_captions              # audit + auto-fix
```

The lighter-weight alternative for the same cohort is `/imgs_caption`, which collapses all three into one batch but uses the deterministic Stage 1.

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION_PROMPT` only (this command does not run the GPU captioner; no caption_joy / caption mutation) can be done w/o yes from user. No GPU prereq — runs entirely in Claude's context.

## See also

- `/img_caption <id>` — single-image variant; runs Stage 1+2+3 for one image with judgment Stage 1 and on-GPU caption.
- `/imgs_caption` — batch variant that runs Stage 1+2+3 but with the deterministic Stage 1; faster but lower per-image quality.
- `/imgs_update_caption_joy` — the natural downstream — picks up images whose `caption_prompt` is newer than `caption_joy`.
- `/imgs_update_caption_prompt <id>` — single-image, Stage 1 only (the upstream of this command's per-image work).
