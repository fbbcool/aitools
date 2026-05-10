---
description: Run JoySceneDBNG('1xlasm') against one image (with id) OR a filtered batch (scope by set, rating, etc.). Only images whose caption_prompt is newer than caption_joy are captioned. Empty caption_prompt skips. Same argument grammar as /update_caption_prompt.
argument-hint: "[<image-id> | set=<name> | rating[==|>=|<=|>|<]<n> | …]"
---

`$ARGUMENTS` is parsed in three layers (same grammar as `/update_caption_prompt`):

1. **`$ARGUMENTS` is empty** → batch over every non-prototype image with non-empty `caption_prompt` that's newer than `caption_joy` (DB-wide, all sets).
2. **`$ARGUMENTS` matches a 24-char hex MongoDB ObjectId** → single-image: caption that one image (force=True bypasses the freshness check; the stored `caption_prompt` is sent verbatim if non-empty, else fresh skin-compose).
3. **`$ARGUMENTS` is a space-separated list of `key=value` / `key<op>value` filter terms** (connectives like `for` / `and` / `where` ignored) → batch restricted to matching images. Supported terms:
    - `set=<name>` — restrict to a SceneSet's active members (excluded ids skipped).
    - `rating==<n>` / `rating=<n>` / `rating>=<n>` / `rating<=<n>` / `rating><n>` / `rating<<n>` — relational rating filter.
    - Multiple terms AND together.

In every batch mode the **stale-prompt** filter applies on top: only caption images where `caption_prompt` is non-empty AND (`caption_joy` empty OR `timestamp_caption_prompt > timestamp_caption_joy`). Images with empty `caption_prompt` are skipped (the upstream is `/update_caption_prompt`).

In every mode the resulting caption is persisted via `simg.set_caption_joy(caption) + simg.set_caption_prompt(prompt) + simg.db_store()` so the timestamps line up.

## Argument parser

Reuse the parser from `/update_caption_prompt`:

```python
import re

ID_RE   = re.compile(r'^[0-9a-f]{24}$')
TERM_RE = re.compile(r'(\w+)\s*(==|>=|<=|=|>|<)\s*(\S+)')

def parse_args(s: str):
    s = (s or '').strip()
    if not s:
        return ('batch', {})
    if ID_RE.match(s):
        return ('id', s)
    filters = {}
    for kw, op, val in TERM_RE.findall(s):
        op = '==' if op == '=' else op
        if kw == 'rating':
            filters[('rating', op)] = int(val)
        elif kw == 'set':
            filters[('set', op)] = val
    return ('batch', filters)
```

## Batch mode

Iterator selection:
- `('set', '==')` filter present → load `SceneSetManager(...).set_from_id_or_name(value)` and iterate `scene_set.imgs`, skipping `excluded_ids`.
- Else → iterate `coll.find({caption_prompt: non-empty, prototype != true}, …)`.

For each candidate:
- Apply remaining filters (e.g. `rating` op).
- Apply the stale-prompt check: skip if `caption_prompt` empty; include if `caption_joy` empty; otherwise include only when `timestamp_caption_prompt > timestamp_caption_joy`.

Then run the captioner once and loop:

```python
from ait.caption.joy_scenedb_ng import JoySceneDBNG
db = JoySceneDBNG(config='prod', skin='1xlasm', verbose=0, force=True, lora=True)
_ = db._joy   # eager-load model
for iid in ids:
    prompt, caption = db.caption_image(iid)
    if not caption:
        continue
    simg = sim.img_from_id(iid)
    if prompt:
        simg.set_caption_prompt(prompt)
    simg.set_caption_joy(caption)
    simg.db_store()
```

Use `run_in_background: true` if the batch is >5 images — the model load is ~30s and each caption is ~3-5s. The batch will notify on completion.

GPU prerequisite: ensure ≥16 GiB free on the target GPU before instantiating the captioner. If `nvidia-smi --query-gpu=memory.free` shows less, ask the user to free the device (typically the gradio app holding a warm model) and retry.

Print one line at the end:
```
caption_joy batch [filters: set=…, rating==…]: N captioned, M failed in {seconds}s
```

## Single-image mode

When `$ARGUMENTS` is an ObjectId, skip the stale-prompt check (the user explicitly asked for this image), instantiate `JoySceneDBNG(force=True)`, run `caption_image(image_id)`, persist both fields.

Report: `image_id`, prompt length used, caption text, and a one-line validator summary (forbidden / body-type / missing-trigger).

## Sequencing tip

Typical workflow: `/update_caption_prompt <scope>` → `/update_caption_joy <scope>` → `/validate_captions <set>`. The three together close the loop from rule edit to clean caption_joy on disk.

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION` / `FIELD_CAPTION_JOY` / `FIELD_CAPTION_PROMPT` (per-image updates, scoped by the named filter or single image) can be done w/o yes from user. Captioning consumes ~16 GiB VRAM for the duration of the batch; ask before starting if the GPU is contested.
