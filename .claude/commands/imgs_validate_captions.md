---
description: Audit caption_joy in a scope (default whole DB) against the skin's rules (forbidden vocab, body-type authorization, missing triggers, naked-multi, opener) and auto-fix the mechanically tractable issues. Same argument grammar as /imgs_update_caption_prompt and /imgs_update_caption_joy.
argument-hint: "[<image-id> | force | set=<name> | rating[==|>=|<=|>|<]<n> | skin=<name> | …]"
---

`$ARGUMENTS` is parsed by the shared filter grammar:

1. **`$ARGUMENTS` is empty** → audit every non-prototype image with non-empty `caption_joy`, DB-wide.
2. **`$ARGUMENTS` matches a 24-char hex MongoDB ObjectId** → audit just that one image.
3. **`$ARGUMENTS` is a space-separated list of `key=value` / `key<op>value` filter terms** (connectives like `for` / `and` / `where` ignored) → audit restricted to matching images. Supported terms:
    - `force` — bare flag. Bypass the **rating>=3 guard** (see below) so auto-fix is allowed to mutate production-grade captions.
    - `set=<name>` — restrict to a SceneSet's active members (excluded ids skipped).
    - `rating==<n>` / `rating>=<n>` / `rating<=<n>` / `rating><n>` / `rating<<n>` — relational rating filter.
    - `skin=<name>` — which skin to audit against (default `1xlasm`).
    - Multiple terms AND together.

## Rating>=3 guard

Images with `rating>=3` are treated as production-grade. The audit **still reports issues** on them so the curator sees the state, but the **auto-fix passes are skipped** by default — no mutation. Pass the bare `force` flag to let auto-fix run on rating>=3 images. Single-image ObjectId mode is an implicit force for this guard.

If neither a `set=` filter nor an ObjectId is given, the iterator scans the whole `images` collection. The `skin=` term is special: it picks the rule set used for validation (not a row filter); default `1xlasm`.

## Argument parser

```python
import re

ID_RE    = re.compile(r'^[0-9a-f]{24}$')
TERM_RE  = re.compile(r'(\w+)\s*(==|>=|<=|=|>|<)\s*(\S+)')
FORCE_RE = re.compile(r'\bforce\b', re.IGNORECASE)

def parse_args(s: str):
    s = (s or '').strip()
    if not s:
        return ('batch', {}, '1xlasm', False)
    if ID_RE.match(s):
        return ('id', s, '1xlasm', True)   # single-image = implicit force
    filters = {}
    skin = '1xlasm'
    force = bool(FORCE_RE.search(s))
    for kw, op, val in TERM_RE.findall(s):
        op = '==' if op == '=' else op
        if kw == 'skin':
            skin = val
        elif kw == 'rating':
            filters[('rating', op)] = int(val)
        elif kw == 'set':
            filters[('set', op)] = val
    return ('batch', filters, skin, force)
```

## Iterator selection (batch mode)

- `('set', '==')` filter present → load `SceneSetManager(...).set_from_id_or_name(value)` and iterate `scene_set.imgs`, skipping prototype + excluded ids.
- Else → iterate `coll.find({caption_joy: non-empty, prototype != true}, …)`.

Apply remaining filters (e.g. `rating` op) client-side.

## Audit categories (per image)

For each image with non-empty `caption_joy`:

1. **forbidden vocab** — `skin.caption_violations(cj)`. Words on the skin's forbidden list (`tiny`, `little`, `small man`, `figurine`, `giantess`, etc.).
2. **body-type unauthorized** — `skin.body_type_warnings(cj, applied_labels_ng)`. Body-type words appearing without their authorizing label (`busty`, `muscular`, `slim`, `curvy`).
3. **missing trigger** — `skin.missing_triggers(cj)`. Caption is missing one of the entity phrases (`xlgts woman` / `xlasm man`) entirely.
4. **opener** — first sentence (split on `.!?`) does not contain BOTH trigger phrases.
5. **naked-multi** — `naked|nude|undressed|unclothed` appears more than once for the SAME figure (nearest-trigger attribution in either direction; flag if any figure has count > 1).
6. **photo_filler** — content-free metadata sentence like *"The image is a photograph."* or *"The image is a highly detailed, realistic photograph."* Regex: `^(?:The image|This image|This|It)\s+is\s+(?:a |an )?(?:[A-Za-z\-]+(?:,\s*|\s+))*(?:photograph|photo|picture|image)\s*\.?\s*$` (case-insensitive). Sentences with trailing content like *"photograph with a neutral gray background."* are NOT matched (the regex requires the noun to terminate the sentence).

## Auto-fix recipe

- **naked-multi** → walk matches in order; for each, attribute via nearest-trigger. The first match per figure is kept; later matches are stripped (along with a leading `a/an/completely/fully` or trailing comma+space, then collapse whitespace).
- **body-type** → for each unauthorized body-type word still present, strip occurrences via the skin's compiled regex (`skin._body_type_res`). Same whitespace cleanup.
- **opener** → if the first sentence is missing both phrases, prepend `"This image features a {primary.phrase} and a {secondary.phrase}."` as the new opening sentence.
- **forbidden vocab** → drop the entire SENTENCE containing the forbidden word. If every sentence has a violation, leave the caption alone for human review.
- **photo_filler** → drop the entire matched sentence. Run BEFORE the forbidden-vocab pass so the count of dropped sentences isn't confused with a forbidden-word fix.
- **missing trigger** → no auto-fix; flag only. (Re-captioning the image — `/imgs_update_caption_joy <id>` — is the right path.)

For each modified caption, persist via `simg.set_caption_joy(fixed)` (which bumps `timestamp_caption_joy`). When `FIELD_CAPTION` was identical to `FIELD_CAPTION_JOY` before the fix, also update `set_caption(fixed)`.

**Rating>=3 guard applies to writes.** Before persisting any auto-fix, check `(img.data.get(FIELD_RATING) or RATING_INIT) >= 3 and not force` — if true, skip the write (the audit row still reports the issue but the caption is left intact). The image is counted under a `skipped_rating>=3` bucket in the report.

## Single-image mode

Same audit + auto-fix pipeline, just on the one image. Print the diff (BEFORE → AFTER text) so the user can sanity-check the fix.

## Report

Print three sections, each one short:

1. **BEFORE** — issue counts before any fixes (header line announces the active scope, e.g. `set=gts_v3, rating==0, skin=1xlasm, captioned=53`).
2. **FIX PASSES** — how many images each fix category touched.
3. **AFTER** — final issue counts. Print `ALL CLEAN` when the dict is empty.

Keep total output under ~30 lines.

## Sequencing tip

`/imgs_update_caption_prompt <scope>` → `/imgs_update_caption_joy <scope>` → `/imgs_validate_captions <scope>` — the three share filter grammar so the same scope string can drive all three steps in sequence.

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION` / `FIELD_CAPTION_JOY` (per-image updates, scoped by the named filter or single image, reversible from a backup) can be done w/o yes from user.
