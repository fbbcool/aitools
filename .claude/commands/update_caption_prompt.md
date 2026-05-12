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

**Primary input.** This is where the **JSON/MD split** (see `conf/skins/_schema.json` top description) becomes operative. The structured surface (entities, labels, compose tables, validators) lives in `1xlasm.json` and is auto-applied by `Skin.render_label_prompts`. The **theme/world knowledge** — scene archetypes, anti-pattern principles, captioner quirks, stylistic intuition — lives in `conf/skins/1xlasm.md`, loaded into `skin.theme_md`. Read the MD before composing; it's the briefing that lets you *think* about this image instead of mechanically concatenating expansions.

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

2. **Read the skin AND the theme briefing.** `Skin('1xlasm')` exposes:
   - `entities_primary.phrase`, `entities_secondary.phrase` — the trigger phrases
   - `labels` (path → rendered sentence) — for static fallback rendering
   - `render_label_prompts(applied_paths)` — context-aware rendering (uses `compose` tables when a group has one, e.g. proximity verb selection by secondary pose)
   - `theme_md` — verbatim contents of `conf/skins/1xlasm.md`; primary input for theme/style judgment, captioner-quirk awareness, and anti-pattern reasoning

   Use `skin.render_label_prompts(labels_ng)` rather than indexing `skin.labels[path]` directly, so compose-aware expansions are applied.

3. **Reason from the MD.** Before drafting, identify which sections of `skin.theme_md` matter for *this* image:
   - **Hint-spine principle** (§4.1): READ FIRST. The hint is the primary source of contextual truth; labels are coarse approximations. The compile is NOT `expand(labels) + hint`; it is hint-driven narrative with labels confirming/filling gaps. See §4.1 for the workflow.
   - **Scene archetype** (§3.2): does this image match held-to-mouth, between-thighs, panties-insertion, all-fours, standing-tower, or vaginal-insertion? Use the archetype's composition cues.
   - **Anti-patterns at risk** (§5): if the man is fully nude → §5.1/§5.3 risk elevated; if the image has watermarks → §5.5 risk; if 3+ pose labels are set on one figure → §4.4 / pose-combination intervention needed.
   - **Captioner quirks** (§6): bake in inline guidance for the quirks most likely on this image.

4. **Compose.** Apply this recipe with judgment, aiming for ~400-1000 chars. Note the **hint-first ordering** below — labels are NOT the spine.
    - **Read the hint** (when present). Treat it as the spine of the interaction description: its verbs, body parts, and spatial relationships are precise; the labels are approximate. If `hints == 'none'` (case-insensitive), fall back to a label-driven compose.
    - **Pull `skin.render_label_prompts(labels_ng)`**. For each rendered sentence: ask *"does the hint already say this, possibly with different wording?"* If yes — drop the label expansion and use the hint's phrasing instead. If no — the label fills a gap (pose, attribute, etc.) the hint is silent on; include it.
    - **Pick a hint-threading pattern** (MD §4.1, "Hint-threading pattern"). **Do not duplicate the hint** — pick ONE:
        - **verbatim pattern**: include the hint verbatim with *"Preserve every verb and body-part reference exactly: …"* lead-in. Let the captioner compose its own integrated sentence. **Do NOT pre-write an integrated sentence with the same content** in the prompt — duplication triggers a repetition spiral.
        - **prefused pattern**: pre-write the integrated sentence (hint vocabulary fused with label-confirmed details). OMIT the verbatim hint quote. A short directive (*"Use the hint vocabulary verbatim"*) is fine.
        - Heuristic: hint is a clean complete sentence → verbatim pattern; hint is fragmentary, has typos, or needs heavy label-fusion → prefused pattern.
    - **Opener:** one complete sentence naming BOTH `xlgts woman` AND `xlasm man`. Pick a verb that fits the labels (insertion → "inserted into her <orifice>"; holding → "holds the xlasm man …"; otherwise generic). Apply MD §4.2 (opener pattern) and §2 (noun-phrase nudity).
    - **Interaction sentences** (the body of the prompt, per chosen pattern):
        - verbatim pattern: emit `Preserve … : <verbatim hint>` and stop there for the interaction. No pre-composed paraphrase.
        - prefused pattern: emit the pre-composed integrated sentence(s) only. No verbatim hint quote.
    - **Gap-fill from labels:** for pose, attribute, and other labels the hint doesn't mention, include the label expansion as a short clause. For multi-pose figures, fuse poses into one compound sentence (MD §4.4).
    - **Inline anti-pattern guard** (only the ones at risk for this image): e.g. for a nude man, add *"never emit 'is naked, with ...'; bind nudity to the noun phrase"*. Don't ship the full §5 list — pick the 1-3 relevant ones.
    - **Closer:** one short ordering instruction ("describe interaction first, then setting").

5. **Persist** via `simg.set_caption_prompt(p) + simg.db_store()`.

6. **Report:** image id, labels_ng, hint, char count vs. previous, the composed prompt verbatim, and a one-line note on which MD sections informed the composition (e.g. *"hint-spine: stands+immersed; archetype=between-thighs; risks=§5.1; labels-dropped: touch.thigh+pose.standing (covered by hint)"*). Keep under ~30 lines.

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION_PROMPT` (per-image updates, scoped to the named filter or single image) can be done w/o yes from user.
