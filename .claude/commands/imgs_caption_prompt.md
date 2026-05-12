---
description: Run the per-image judgment-mode caption_prompt compile (the same Stage 1 as /img_caption) on curated images. Default: only those whose caption_prompt is out of date (suggestion newer than caption_prompt, or caption_prompt empty). With `force`: every curated image regardless of freshness. With `ignore_curated`: drop the suggestion requirement and accept any image with non-empty labels_ng + hints (legacy / non-curator-promoted cohort). Curated = non-empty labels_ng AND non-empty hints AND non-empty suggestion. Produces tight ~400-1000 char prompts, NOT the ~5000 char deterministic kind. Persists FIELD_CAPTION_PROMPT only; downstream /imgs_caption_joy picks them up.
argument-hint: "[force] [ignore_curated] [set=<name> | rating[==|>=|<=|>|<]<n> | limit=<n> | …]"
---

`$ARGUMENTS` is an optional space-separated list of bare-word flags and `key=value` / `key<op>value` filter terms (connectives like `for` / `and` / `where` ignored). Empty → all curated images with stale `caption_prompt`, DB-wide. Supported terms:

- `force` — bare flag. Process every eligible image regardless of `caption_prompt` freshness (the recency check is skipped). Useful after a prompt-compile-recipe edit when the curator wants every existing prompt rebuilt.
- `ignore_curated` — bare flag. Drop the suggestion-non-empty requirement. Eligible image becomes "labels_ng non-empty AND hints non-empty" (the minimum needed to compose a prompt). Useful for legacy images that pre-date the `_SUGGESTION` workflow but still carry curator labels+hints, or images promoted to canonical without ever running `/img_suggest`.
- `set=<name>` — restrict to a SceneSet's active members.
- `rating==<n>` / `rating=<n>` / `rating>=<n>` / `rating<=<n>` / `rating><n>` / `rating<<n>` — relational rating filter.
- `limit=<n>` — cap the batch at N images (default unlimited). Use when the pending list is large and the curator wants to review the first batch before continuing.

Flags compose with the filters — e.g. `force set=gts_v3 limit=10` rebuilds prompts for the first 10 curated images in `gts_v3` whether or not they have a current caption_prompt; `ignore_curated rating==1` picks up the entire done cohort regardless of suggestion provenance.

**Single-image mode**: if `$ARGUMENTS` is (or contains) a 24-char hex MongoDB ObjectId (regex `^[0-9a-f]{24}$`), the command processes just that image. The eligibility filter (`is_curated` / `is_labeled`) is **skipped** — the curator named it explicitly, so the only precondition is that `labels_ng` and `hints` are both non-empty (the structural minimum to compose any prompt). The freshness check is also skipped (single-image = implicit `force`). If `labels_ng` or `hints` is empty, abort with a short message.

Same parser as `/imgs_update_caption_prompt`, extended with the `force` and `ignore_curated` bare-word flags and bare-ObjectId single-image mode.

## Why this exists

This command is **Stage 1 of the curator workflow** — judgment-mode `caption_prompt` compile for curated images. It produces tight ~400-1000 char prompts that bake in only the rules relevant to each specific image. Downstream `/imgs_caption_joy` consumes these prompts verbatim to generate `caption_joy`.

Contrast with the lower-level `/imgs_update_caption_prompt` (bulk-mode), which mechanically concatenates `default_prompt + opener + label_prompts + every-constraint + closer` into a ~5000-char prompt. That's faster (no judgment cost) but dilutes the captioner's attention — observed in production as elevated `naked_multi` and `photo_filler` fix counts.

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


def is_labeled(img) -> bool:
    """Labeled = labels_ng AND hints non-empty (suggestion ignored)."""
    d = img.data
    has_labels = bool(d.get(SceneDef.FIELD_LABELS_NG) or [])
    has_hint   = bool((d.get(SceneDef.FIELD_HINTS) or '').strip())
    return has_labels and has_hint


def is_prompt_compile_pending(img, *, force: bool = False,
                                     ignore_curated: bool = False) -> bool:
    """Default: curated AND upstream-edit ts > caption_prompt ts (or caption_prompt empty).
    With force=True: skip the freshness check.
    With ignore_curated=True: require only `is_labeled` (drop the suggestion check).

    Upstream-edit ts = max(ts_labels_ng, ts_hints, ts_labels_ng_SUGGESTION,
    ts_hints_SUGGESTION). Any edit to those fields counts as a reason to
    re-compile.
    """
    if ignore_curated:
        if not is_labeled(img):
            return False
    else:
        if not is_curated(img):
            return False
    if force:
        return True
    d = img.data
    ts_up = max(
        d.get(SceneDef.FIELD_TIMESTAMP_LABELS_NG) or 0,
        d.get(SceneDef.FIELD_TIMESTAMP_HINTS) or 0,
        d.get(SceneDef.FIELD_TIMESTAMP_LABELS_NG_SUGGESTION) or 0,
        d.get(SceneDef.FIELD_TIMESTAMP_HINTS_SUGGESTION) or 0,
    )
    cap_prompt = (d.get(SceneDef.FIELD_CAPTION_PROMPT) or '').strip()
    if not cap_prompt:
        return True                      # never compiled → in scope
    if ts_up <= 0:
        return False                     # legacy data, no edit ts → not stale
    ts_cp = d.get(SceneDef.FIELD_TIMESTAMP_CAPTION_PROMPT) or 0
    return ts_up > ts_cp
```

The filter mirrors `/imgs_caption_joy` exactly except the timestamp compared against is `caption_prompt`, not `caption_joy`. Result: images that have been suggested-then-curated but whose stored caption_prompt is stale (or empty).

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

- `image_id` set (single-image mode) → `pending = [sim.img_from_id(image_id)]`. Skip the eligibility/freshness check; require only that `labels_ng` and `hints` are non-empty. If either is empty, abort with `cannot compose: labels_ng or hints is empty`.
- `('set', '==')` present → load `SceneSetManager(...).set_from_id_or_name(value)` and iterate `scene_set.imgs`, skipping `excluded_ids`.
- Else → iterate `coll.find({prototype: {$ne: true}}, …)`.

For each candidate (batch modes): apply `is_prompt_compile_pending(img, force=force, ignore_curated=ignore_curated)` AND remaining filters (e.g. `rating`). Sort the pending list by `timestamp_created` descending (newest first) so a `limit=N` slice picks the most recently created images. Apply `limit` if set.

If `len(pending) == 0`, print `nothing to do — no <scope> images have stale caption_prompt` where `<scope>` is "curated" (default) or "labeled" (`ignore_curated`); `force` mode swaps "stale caption_prompt" for "match the filters". Then stop.

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
/imgs_caption_prompt         # this command — judgment-mode Stage 1
  ↓
/imgs_caption_joy            # Stage 2+3 using the stored prompts
```

The lower-level alternative is `/imgs_update_caption_prompt` (bulk-mode, deterministic Stage 1) followed by `/imgs_update_caption_joy` — faster but lower per-image quality.

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION_PROMPT` only (this command does not run the GPU captioner; no caption_joy / caption mutation) can be done w/o yes from user. No GPU prereq — runs entirely in Claude's context.

## See also

- `/imgs_caption_joy` — the immediate downstream — captions every curated image with a stored prompt (uses these prompts verbatim).
- `/img_caption <id>` — single-image variant; runs Stage 1+2+3 for one image with judgment Stage 1 and on-GPU caption.
- `/imgs_update_caption_prompt <id>` — single-image, Stage 1 only (the lower-level per-image equivalent of this command's work).
- `/imgs_update_caption_joy` — lower-level batch Stage 2 only; works on any image with a stored prompt (not scoped to curated).
