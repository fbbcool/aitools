---
description: Compile a focused caption_prompt for one image (with id) OR bulk-refresh many images with optional scope filters (set, rating). Reads labels_ng + hints + skin rules; writes the result back to FIELD_CAPTION_PROMPT. Caption workflow then picks it up verbatim.
argument-hint: "[<image-id> | set=<name> | rating[==|>=|<=|>|<]<n> | …]"
---

`$ARGUMENTS` is parsed in three layers:

1. **`$ARGUMENTS` is empty** → bulk-refresh every non-prototype image with non-empty `labels_ng` and `hints`.
2. **`$ARGUMENTS` matches a 24-char hex MongoDB ObjectId** (regex `^[0-9a-f]{24}$`) → per-image, judgment-driven compile (Claude hand-crafts one prompt). Recipe in §"Per-image mode" below.
3. **`$ARGUMENTS` is a space-separated list of `key=value` / `key<op>value` filter terms** (with optional connective words like "for", "and", "where" the parser ignores) → bulk-refresh restricted to images matching every filter. Supported terms:
    - `set=<name>` — restrict to images that are members of the named SceneSet (loaded via `SceneSetManager.set_from_id_or_name`). Excluded images of that set are skipped.
    - `rating==<n>` / `rating=<n>` — exact rating match (integer; -2..5).
    - `rating>=<n>` / `rating<=<n>` / `rating><n>` / `rating<<n>` — relational rating filter.
    - Multiple terms combine with AND (no OR support).

Mode 1 and mode 3 use the same deterministic Python recipe — only the source-of-truth iterator differs.

In every mode the resulting prompt is stored in `FIELD_CAPTION_PROMPT`; the next click of `caption 1xlasm` (or set-editor batch) reads this field and sends it verbatim to JoyCaption.

## Argument parser (tiny, written inline in the script)

```python
import re

ID_RE = re.compile(r'^[0-9a-f]{24}$')
TERM_RE = re.compile(r'(\w+)\s*(==|>=|<=|=|>|<)\s*(\S+)')

def parse_args(s: str):
    s = (s or '').strip()
    if not s:
        return ('bulk', {})
    if ID_RE.match(s):
        return ('id', s)
    filters = {}
    for kw, op, val in TERM_RE.findall(s):
        op = '==' if op == '=' else op
        if kw == 'rating':
            filters[('rating', op)] = int(val)
        elif kw == 'set':
            filters[('set', op)] = val
    return ('bulk', filters)
```

## Bulk mode

Iterator selection:
- If `('set', '==')` filter present → load `SceneSetManager(...).set_from_id_or_name(value)` and iterate `scene_set.imgs`, skipping `excluded_ids`.
- Else → iterate `coll.find({labels_ng: non-empty, hints: non-empty, prototype != true}, …)`.

For each candidate, apply remaining filters client-side:
- `('rating', op)` — compare `img.data.get(FIELD_RATING, RATING_INIT)` against the value using `op`.

Hint sentinel: if the SceneImage's `hints` field is the literal string `'none'` (case-insensitive after `.strip()`), treat it as no hint — skip the `Preserve every verb…` line in the composed prompt. The runtime (`JoySceneDBNG`, `Skin.compile_user_prompt`) does the same normalization, so caption-time and prompt-compile-time stay in sync.

Then compose using the recipe and persist via `simg.set_caption_prompt(p) + simg.db_store()`.

Recipe (deterministic):

```
default_prompt = 'Write a detailed description of this image.'
opener = <picked label expansion's first sentence (preference: interaction.insertion.* → primary.action.* → interaction.*) or generic both-trigger>
hint_section = "Preserve every verb and body-part reference verbatim: {hint}"
labels = each applied path's expansion (anchor skipped to avoid duplication)
constraints = [
  "Do not use 'tall', 'huge', 'giant', 'enormous', or numerical heights — the phrase '{P}' carries her size.",
  "Never describe the {S} as 'tiny', 'small', 'child', 'figurine', etc. — he is always an adult man, no matter how small he appears.",
  # naked-attribute rule (clothing-strict):
  "Each figure's clothing state is independent and must be evaluated from the image directly. A figure is 'naked' ONLY when no clothing is visible on them at all. If a figure wears any of: dress, skirt, top, shirt, tank top, blouse, lingerie, bra, panties, thong, stockings, tights, hosiery, gloves, robe, gown, harness, jacket, coat, leotard, corset, swimsuit — that figure is NOT naked, even if much skin is exposed. Apply 'naked' sparingly, only to a fully unclothed figure, ONCE at first reference (e.g. 'The naked {S} ...'). Never repeat 'naked', 'nude', 'undressed', or 'unclothed' for that same figure afterward. Anti-pattern: image shows the {P} wearing a dress or lingerie -> 'The {P}, naked, ...' is WRONG; she is clothed.",
  # if NO primary.attribute.* applied:
  "Do not use 'muscular', 'muscle', 'bodybuilder', 'ripped', 'defined', 'busty', 'voluptuous', 'slim', 'slender', 'lean', 'athletic build', 'curvy', 'hourglass', 'cleavage', 'large breasts', 'big breasts', 'leggy', 'long legs', 'big calves', 'big ass', 'big butt', 'round ass', 'bubble butt', 'thick thighs', 'hairy', 'pubic hair'.",
  # always emit (secondary.attribute.* only carries penis-visibility info, not build authorization):
  "Do not describe his body build (no 'slim', 'muscular', 'lean', 'toned', 'ripped', 'defined') and do not exaggerate his penis ('huge cock', 'massive cock', 'enormous penis', 'oversized penis').",
]
closer = "Describe the interaction first; clothing, hair, makeup, background, lighting, and camera angle come strictly after."
prompt = ' '.join([default_prompt, opener, hint_section, *labels, *constraints, closer])
```

Print one line at the end describing the scope and counts:
```
bulk update [filters: set=…, rating==…]: N images refreshed (avg {chars} chars)
```

## Per-image mode

This is a **judgment task**: programmatic concatenation of every skin rule + every label sentence produces a 2000-3000 char prompt, which dilutes the model's attention. Your job is to compose a tight, image-specific prompt (~400-1000 chars) that bakes in **only the rules that matter for this image** and inlines the hint and applied-label content into natural prose.

### Steps

1. **Pull the image data.** Use the env vars `PYTHONPATH=src CONF_AIT=./conf HOME_AIT=. WORKSPACE=$HOME/Workspace AIDB_SCENE_CONFIG=prod AIDB_SCENE_DEFAULT=0000`:

```python
from aidb import SceneDef, SceneManager
scm = SceneManager(config='prod', verbose=0)
sim = scm.scene_image_manager()
simg = sim.img_from_id(image_id)
labels_ng = simg.data.get(SceneDef.FIELD_LABELS_NG) or []
hints     = simg.data.get(SceneDef.FIELD_HINTS, '') or ''
```

If the image is missing or `labels_ng` is empty, abort with a short message.

2. **Read the skin.** `Skin('1xlasm')` exposes `entities_primary.phrase`, `entities_secondary.phrase`, `labels` (path → rendered sentence), and the rule lists.

3. **Compose.** Apply this recipe with judgment, aiming for ~400-1000 chars:
    - **Opener:** one complete sentence naming BOTH `xlgts woman` AND `xlasm man`. Pick a verb that fits the labels (insertion → "inserted into her <orifice>"; holding → "holds the xlasm man …"; otherwise generic).
    - **Hint** (when present): include the hint sentences essentially verbatim, with a one-line *"Preserve every verb and body-part reference exactly: …"* lead-in. Don't paraphrase.
    - **Label expansions** (selective): include `skin.labels[path]` for each applied path, but skip any already implicit in the hint or the opener.
    - **Constraints** (use the same set as bulk recipe above; conditional bans gated by attribute-label presence).
    - **Closer:** one short ordering instruction.

4. **Persist** via `simg.set_caption_prompt(p) + simg.db_store()`.

5. **Report:** image id, labels_ng, hint, char count vs. previous, and the composed prompt verbatim. Keep under ~30 lines.

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION_PROMPT` (per-image updates, scoped to the named filter or single image) can be done w/o yes from user.
