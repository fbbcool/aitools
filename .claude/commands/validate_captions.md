---
description: Audit caption_joy in a SceneSet against the skin's rules (forbidden vocab, body-type authorization, missing triggers, naked-multi, opener) and auto-fix the mechanically tractable issues.
argument-hint: "[set-name (default: gts_v3)] [skin (default: 1xlasm)]"
---

Validate `caption_joy` for every non-prototype image in `$ARGUMENTS` (default set `gts_v3`, default skin `1xlasm`) against the active skin's rules and auto-fix what can be patched without rerunning the captioner. Print a before / fixes / after summary so the user can see what the model produced vs. what's persisted.

## Steps

Run a single Python script against prod (`PYTHONPATH=src CONF_AIT=./conf HOME_AIT=. WORKSPACE=$HOME/Workspace AIDB_SCENE_CONFIG=prod AIDB_SCENE_DEFAULT=0000`).

```python
import re
from collections import Counter
from aidb import SceneDef
from aidb.scene.scene_set_manager import SceneSetManager
from ait.caption.skin import SkinRegistry

# args: token 1 = set (default 'gts_v3'), token 2 = skin (default '1xlasm')
skin = SkinRegistry().get(skin_name)
P, S = skin.entities_primary.phrase, skin.entities_secondary.phrase
P_RE, S_RE = re.compile(re.escape(P), re.IGNORECASE), re.compile(re.escape(S), re.IGNORECASE)
NAKED_RE = re.compile(r'\b(naked|nude|undressed|unclothed)\b', re.IGNORECASE)
SENT_SPLIT = re.compile(r'(?<=[.!?])\s+')
```

## Audit categories (per image)

For each image with non-empty `caption_joy`:

1. **forbidden vocab** — `skin.caption_violations(cj)`. Words on the skin's forbidden list (`tiny`, `little`, `small man`, `figurine`, `giantess`, etc.).
2. **body-type unauthorized** — `skin.body_type_warnings(cj, applied_labels_ng)`. Body-type words that appear in caption without their authorizing label (`busty`, `muscular`, `slim`, `curvy`).
3. **missing trigger** — `skin.missing_triggers(cj)`. Caption is missing one of the entity phrases (`xlgts woman` / `xlasm man`) entirely.
4. **opener** — first sentence (split on `.!?`) does not contain BOTH trigger phrases.
5. **naked-multi** — `naked|nude|undressed|unclothed` appears more than once for the SAME figure. Attribute each match to whichever trigger phrase is nearest in either direction; flag if any figure has count > 1.

## Auto-fix recipe

- **naked-multi** → walk matches in order; for each, attribute via nearest-trigger (in either direction). The first match per figure is kept; later matches are stripped (along with a leading "a/an/completely/fully" or trailing comma+space, then collapse whitespace).
- **body-type** → for each unauthorized body-type word still present, strip occurrences via the skin's compiled regex (`skin._body_type_res`). Same whitespace cleanup.
- **opener** → if the first sentence is missing both phrases, prepend `"This image features a {primary.phrase} and a {secondary.phrase}."` as the new opening sentence. Original caption stays intact below.
- **forbidden vocab** → drop the entire SENTENCE containing the forbidden word (more aggressive — preserves the rest of the caption but removes the offending observation). If every sentence has a violation, leave the caption alone for human review.
- **missing trigger** → no auto-fix; flag only. (Re-captioning the image is the right path.)

For each modified caption, persist via `simg.set_caption_joy(fixed)` (which bumps `timestamp_caption_joy`). When `FIELD_CAPTION` was identical to `FIELD_CAPTION_JOY` before the fix, also update `set_caption(fixed)` so the curated and raw views stay aligned.

## Report

Print three sections, each one short:

1. **BEFORE** — issue counts before any fixes.
2. **FIX PASSES** — how many images each fix category touched.
3. **AFTER** — final issue counts. Print `ALL CLEAN` when the dict is empty.

Keep total output under ~30 lines.

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION` / `FIELD_CAPTION_JOY` (per-image updates, scoped to the named set, reversible from a backup) can be done w/o yes from user.
