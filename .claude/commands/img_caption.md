---
description: Run the full caption pipeline (compose prompt → caption → validate) for ONE image by ObjectId. No batch mode — single-image only.
argument-hint: "<image-id>"
---

`$ARGUMENTS` must be a 24-char hex MongoDB ObjectId (regex `^[0-9a-f]{24}$`). Anything else (empty, filter expression like `set=…`, multiple ids) is rejected with a short error — this command is explicitly single-image.

## Pipeline

For the given image id, run these three stages in order. If any stage hard-errors (image not found, GPU OOM, etc.), abort and report which stage failed.

### 1. Compose caption_prompt (per-image judgment mode)

Use the per-image recipe from `/imgs_update_caption_prompt`'s "Per-image mode": pull `labels_ng` + `hints` + `Skin('1xlasm')`, hand-craft a tight prompt (~400-1000 chars) that bakes in only the rules that matter for this image, persist via `simg.set_caption_prompt(p) + simg.db_store()`.

**Primary inputs are the curator's `hints` and `skin.theme_md`** (the theme briefing in `conf/skins/1xlasm.md`). The hint is the source of contextual truth for the interaction — its verbs, body parts, and spatial relationships are precise. Labels are coarse approximations and confirm/refine specific aspects of what the hint already describes; the compile is hint-driven narrative with labels filling gaps the hint is silent on. **NOT** `expand(labels) + hint` — read MD §4.1 first for the hint-spine workflow. JSON/MD split: structured taxonomy + mechanical validators live in the JSON; theme/world knowledge (archetypes, anti-pattern principles, captioner quirks) lives in the MD. See `/imgs_update_caption_prompt` per-image mode steps 2-4 for the full recipe.

Use `skin.render_label_prompts(labels_ng)` (context-aware via `compose` tables) for the label sentence pool — but use those sentences as a *candidate set to confirm/drop against the hint*, not as a scaffold to concatenate.

Hint sentinel: a `hints` value equal to the literal string `'none'` (case-insensitive, stripped) means no hint — skip the *"Preserve every verb…"* lead-in.

If `labels_ng` is empty, abort: this command refuses to caption an unlabeled image.

### 2. Run JoyCaption (force=True)

GPU prerequisite: `nvidia-smi --query-gpu=memory.free` ≥ 16 GiB. If not, ask the user to free the device and stop.

**Preferred path — via the persistent `joy_server`** (reuses the loaded model across invocations; ~5-10s per caption after the first):

```python
import time
from ait.caption import joy_client, caption_log
from ait.caption.skin import SkinRegistry

joy_client.ensure_running()   # ~23s on first call; ~0s if already up
sk = SkinRegistry().get('1xlasm')
simg = sim.img_from_id(image_id)
caption_log.start_run(simg, run_tag='img_caption')
stored_prompt = (simg.data.get(SceneDef.FIELD_CAPTION_PROMPT) or '').strip()
t0 = time.time()
prompt, caption = joy_client.caption(
    image_url=str(simg.url_from_data),
    user_content=stored_prompt,
    system_content=sk.directive,
)
elapsed = time.time() - t0
if not caption:
    abort('captioner returned no caption')
simg.set_caption_joy(caption)
simg.db_store()
caption_log.log_joy_call(
    simg, stage='caption_joy',
    user_content=stored_prompt, skin=sk,
    response_caption=caption,
    elapsed_seconds=elapsed,
)
```

**Fallback path — in-process load** (when the server can't be started, e.g. GPU contested at the moment of startup):

```python
from ait.caption.joy_scenedb_ng import JoySceneDBNG
db = JoySceneDBNG(config='prod', skin='1xlasm', verbose=1, force=True, lora=True)
prompt, caption = db.caption_image(image_id)
if not caption:
    abort('captioner returned no caption')
simg = sim.img_from_id(image_id)
if prompt:
    simg.set_caption_prompt(prompt)
simg.set_caption_joy(caption)
simg.db_store()
```

Either path: the stored caption_prompt from Stage 1 is sent verbatim. `force=True` semantics are implicit in the joy_client path (it always runs the caption regardless of freshness).

### 3. Validate + auto-fix

Use the single-image pipeline from `/imgs_validate_captions`: audit `caption_joy` against `skin.caption_violations` / `skin.body_type_warnings` / `skin.missing_triggers` / opener / naked-multi, then auto-fix the mechanically tractable categories (naked-multi, body-type, opener, forbidden vocab). Missing-trigger is flagged only — no auto-fix.

Bracket the audit with `caption_log.log_audit(simg, when='audit_before', ...)` and `caption_log.log_audit(simg, when='audit_after', ...)` so the persisted log has the full before/after state — categorised flags on the 'before' entry, applied fix labels on the 'after' entry. Future audit probes (Stage 3.5 visual audit) should call `caption_log.log_joy_call(simg, stage='audit_probe', ...)` once per probe round-trip.

If a fix is applied, persist `simg.set_caption_joy(fixed)`. When `FIELD_CAPTION` was identical to `FIELD_CAPTION_JOY` before stage 2, also update `set_caption(fixed)` so the manual caption stays in sync.

## Report

Print under ~25 lines, with these sections:

1. **header** — image id, labels_ng, hint (or `<none>`)
2. **stage 1** — composed caption_prompt char count (and delta from previous if non-empty)
3. **stage 2** — captioner output (first ~200 chars of caption_joy, or truncated marker)
4. **stage 3** — issues before/after with the categories that fired; auto-fixes applied; final caption diff (BEFORE → AFTER) if anything changed
5. one-line summary: `caption_image <id>: prompt=N chars, caption=N chars, fixes=[…], status=clean|flagged`

## Access rights

Read access to canonical collections + write to `FIELD_CAPTION` / `FIELD_CAPTION_JOY` / `FIELD_CAPTION_PROMPT` (single image, fully reversible by re-running) can be done w/o yes from user. Captioning consumes ~16 GiB VRAM for ~10s; ask before starting if the GPU is contested.

## See also

- `/imgs_update_caption_prompt <id>` — stage 1 only
- `/imgs_update_caption_joy <id>` — stage 2 only
- `/imgs_validate_captions <id>` — stage 3 only

This command is the orchestrator; use it when you want the whole loop on one image without three round trips.
