---
description: Compile a short, precise caption_prompt for one image (with id) or bulk-refresh all eligible images (no arg). Reads labels_ng + hints + skin rules; writes the result back to FIELD_CAPTION_PROMPT. Caption workflow then picks it up verbatim.
argument-hint: "[image-id (omit to refresh all images with non-empty labels_ng + hints)]"
---

`$ARGUMENTS` controls the mode:

- **`$ARGUMENTS` is a single image id** → hand-craft one SHORT, PRECISE `caption_prompt` for THAT image using Claude's judgment. Use the recipe below.
- **`$ARGUMENTS` is empty** → bulk-refresh: iterate every non-prototype image whose `labels_ng` and `hints` are both non-empty, compose a focused prompt for each via the deterministic recipe (same constraints as the per-image judgment, just executed as Python so 100+ images finish in seconds), and persist. Print a one-line summary at the end.

In either mode the resulting prompt is stored in `FIELD_CAPTION_PROMPT`; the next click of `caption 1xlasm` (or set-editor batch) reads this field and sends it verbatim to JoyCaption.

## Bulk mode (`$ARGUMENTS` empty)

Run a single Python script that mirrors the recipe below as deterministic code. It iterates `coll.find({labels_ng: non-empty, hints: non-empty, prototype != true}, …)`, composes the focused prompt for each, and calls `simg.set_caption_prompt(p) + simg.db_store()` so the timestamp gets bumped. The opener anchor is picked from labels via this preference: `interaction.insertion.*` → `primary.action.*` → `interaction.*` → generic `'This image features a {primary.phrase} and a {secondary.phrase}.'`. Each prompt assembles as:

```
default_prompt = 'Write a detailed description of this image.'
opener = <picked label expansion's first sentence, or generic both-trigger>
hint_section = "Preserve every verb and body-part reference verbatim: {hint}"
labels = each applied path's expansion (anchor skipped to avoid duplication)
constraints = [
  "Do not use 'tall', 'huge', 'giant', 'enormous', or numerical heights — the phrase '{P}' carries her size.",
  "Never describe the {S} as 'tiny', 'small', 'child', 'figurine', etc. — he is always an adult man, no matter how small he appears.",
  "If either figure is naked, attach 'naked' to that figure ONCE at its first reference (e.g. 'The {P}, naked, ...' or 'The naked {S} ...'). Never use 'naked', 'nude', 'undressed', or 'unclothed' for that same figure afterward. Anti-pattern: 'The {P} holds the naked {S}. The naked {S} smiles.' is WRONG — the second sentence must say 'The {S} smiles.'",
  # if NO primary.attribute.* applied:
  "Do not use 'muscular', 'bodybuilder', 'busty', 'voluptuous', 'slim', 'slender', 'lean', 'curvy', 'hourglass', 'cleavage', 'large breasts', 'big breasts'.",
  # if NO secondary.attribute.* applied:
  "Do not describe his body build (no 'slim', 'muscular', 'lean', 'toned').",
]
closer = "Describe the interaction first; clothing, hair, makeup, background, lighting, and camera angle come strictly after."
prompt = ' '.join([default_prompt, opener, hint_section, *labels, *constraints, closer])
```

Print one line at the end: `bulk update: N images refreshed (avg {chars} chars)`.

## Per-image mode (`$ARGUMENTS` is an id)

This is a **judgment task**: programmatic concatenation of every skin rule + every label sentence produces a 2000-3000 char prompt, which dilutes the model's attention. Your job is to compose a tight, image-specific prompt (~400-1000 chars) that bakes in **only the rules that matter for this image** and inlines the hint and applied-label content into natural prose.

## Steps

1. **Pull the image data.** Run a small Python script with `PYTHONPATH=src CONF_AIT=./conf HOME_AIT=. WORKSPACE=$HOME/Workspace AIDB_SCENE_CONFIG=prod AIDB_SCENE_DEFAULT=0000`:

```python
from aidb import SceneDef, SceneManager
scm = SceneManager(config='prod', verbose=0)
sim = scm.scene_image_manager()
simg = sim.img_from_id('$ARGUMENTS')
labels_ng = simg.data.get(SceneDef.FIELD_LABELS_NG) or []
hints     = simg.data.get(SceneDef.FIELD_HINTS, '') or ''
```

If the image is missing or `labels_ng` is empty, abort with a short message.

2. **Read the skin.** Load `Skin('1xlasm')`. You need:
   - `skin.entities_primary.phrase` and `skin.entities_secondary.phrase` (the trigger phrases).
   - `skin.labels` (path → rendered sentence). Use `skin.labels[path]` for each applied path to get the canonical expansion.
   - `skin.entities_primary.rules`, `skin.entities_secondary.rules`, `skin.interaction.rules` for the constraint vocabulary.
   - `skin.user_hint_preamble` for the hint-handling guidance.

3. **Compose the prompt.** Apply this recipe with judgment:

   **a) Opener (always):** one complete sentence naming BOTH `xlgts woman` AND `xlasm man`. Pick a verb that fits the labels — *e.g.* if `interaction.insertion.*` is applied, use *"The xlasm man is inserted into the xlgts woman's <orifice>."*; if `primary.action.holding` is applied, *"The xlgts woman holds the xlasm man …"*; otherwise a generic *"This image features a xlgts woman and a xlasm man."*

   **b) Hint (when present):** include the hint sentences essentially verbatim, with a brief "Preserve every verb and body-part reference exactly: …" lead-in (cribbed from `user_hint_preamble`, but trimmed to one short sentence). Don't expand the hint into multiple paraphrases.

   **c) Label expansions (selective):** include `skin.labels[path]` for each applied path, but skip ones already implicit in the hint or the opener (e.g. if the hint says *"he is inserted into her vagina"* and `interaction.insertion.vagina_up` is applied, you don't need to repeat the label expansion). The point is *one* fact per assertion, not redundant repetition.

   **d) Constraints (conditional):**
     - Always include the size-word ban: *"Do not use 'tall', 'huge', 'giant', 'enormous', or numerical heights — the trigger phrase 'xlgts woman' carries her size."*
     - Always include the diminutive ban: *"Never describe the xlasm man as 'tiny', 'small', 'child', 'figurine', etc. — he is always an adult man, no matter how small he appears."*
     - Always include the naked-attribute rule: *"If either figure is naked, attach 'naked' to that figure ONCE at its first reference (e.g. 'The xlgts woman, naked, …' or 'The naked xlasm man …'). Never use 'naked', 'nude', 'undressed', or 'unclothed' for that same figure afterward. Anti-pattern: 'The xlgts woman holds the naked xlasm man. The naked xlasm man smiles.' is WRONG — the second sentence must say 'The xlasm man smiles.'"*
     - If NO `primary.attribute.*` label is applied: add the explicit-word ban: *"Do not use 'muscular', 'bodybuilder', 'busty', 'voluptuous', 'slim', 'slender', 'lean', 'curvy', 'hourglass', 'cleavage', 'large breasts', 'big breasts'."*
     - If NO `secondary.attribute.*` label is applied: add *"Do not describe his body build (no 'slim', 'muscular', 'lean', 'toned')."*
     - If hint present: emphasize verb/body-part preservation in one short sentence.

   **e) Closer (always):** one short instruction like *"Describe the interaction first; clothing, hair, makeup, background, lighting, and camera angle come strictly after."*

   Aim for ~400-1000 chars. Sentences should flow as one paragraph. Order: opener → hint (if any) → label expansions → constraints → closer.

4. **Persist.** Write the composed prompt to `FIELD_CAPTION_PROMPT`:

```python
from aidb.scene.scene_common import SceneDef
simg.set_caption_prompt(composed_prompt)
simg.db_store()
```

5. **Report.** Print:
   - image id, applied labels_ng, hint
   - char count of the new prompt vs. the previous (if any)
   - the composed prompt (full text)

## Output style

Keep the report under ~30 lines. Show the composed prompt verbatim so the user can review before re-captioning.

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION_PROMPT` (single-document update, scoped to the named image) can be done w/o yes from user.
