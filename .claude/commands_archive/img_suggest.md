---
description: Iteratively probe JoyCaption to suggest labels_ng + hints for an image. Persists labels_ng_SUGGESTION / hints_SUGGESTION on the SceneImage. Never mutates canonical labels_ng, hints, or caption fields. Max 5 iterations, converge early.
argument-hint: "<image-id> [skin=<name>]"
---

`$ARGUMENTS` must contain a 24-char hex MongoDB ObjectId (regex `^[0-9a-f]{24}$`), optionally followed by `skin=<name>` (default `1xlasm`). Anything else (empty, filter expression, multiple ids) is rejected with a short error — this command is explicitly single-image.

Parse the args:

```python
import re
raw = ($ARGUMENTS or '').strip()
id_m = re.search(r'\b([0-9a-f]{24})\b', raw)
sk_m = re.search(r'\bskin\s*=\s*(\S+)', raw, re.IGNORECASE)
if not id_m:
    abort('usage: /img_suggest <24-hex-id> [skin=<name>]')
image_id = id_m.group(1)
skin     = sk_m.group(1) if sk_m else '1xlasm'
```

Default `1xlasm` preserves existing behavior bit-exact. The skin name drives `SkinRegistry().get(skin)`, `joy_client.ensure_running(skin=skin)`, and the abort status string (`not-<skin>-shape`).

## Why this exists

The captioning workflow assumes `labels_ng` and `hints` are already populated. For a fresh imported image both are blank, and manually filling them is the slowest curator step. This command produces a **first-pass suggestion** by iteratively probing JoyCaption (acting as Claude's "eyes") and parsing each response into label-candidates and hint-material. Output goes to dedicated `_SUGGESTION` fields so the curator can review and edit before promoting.

**Primary input for compose** is `skin.theme_md_suggestions` (the briefing in `conf/skins/<skin>_suggestions.md`, e.g. `1xlasm_suggestions.md` by default) plus the image itself (via joy probes). Read the MD before composing probes — §3 has the probe templates, §5 has the response→label mapping rules.

## Pipeline

### 1. Pre-state check

```python
from aidb import SceneDef, SceneManager
from ait.caption.skin import SkinRegistry
from ait.caption import joy_client

scm = SceneManager(config='prod', verbose=0)
sim = scm.scene_image_manager()
sk = SkinRegistry().get(skin)
simg = sim.img_from_id(image_id)
if simg is None:
    abort('image not found')

# If canonical labels_ng or hints is non-empty, ask the curator before
# overwriting any existing _SUGGESTION fields.
has_canonical = bool(simg.labels_ng) or bool((simg.hints or '').strip())
has_prev_suggestion = bool(simg.labels_ng_suggestion) or bool((simg.hints_suggestion or '').strip())
if has_canonical:
    # Image is already curated; suggestion is unusual. Confirm intent.
    print('NOTE: this image already has canonical labels_ng / hints. '
          'Running /img_suggest will populate the _SUGGESTION fields '
          'but will NOT touch the canonical fields.')
```

**Prior — `labels_ng_extraction`** (face-skin only, optional). When the SceneImage has labels in `FIELD_LABELS_NG_EXTRACTION` (auto-populated by `script/imgs_extract_face_meta.py` from aip's `face_meta` PNG chunk), those are deterministic geometric/structural facts (gaze direction, eye/mouth state, framing, composition for 1xlface). Use them as a prior:

```python
extraction = set(simg.labels_ng_extraction or [])

# Groups already covered by extraction — skip the corresponding joy probes
groups_covered = {p.rsplit('.', 1)[0] for p in extraction}  # e.g. {'primary.framing', 'primary.eye_state'}
```

The judgment-driven probe loop below can skip iter-3 (pose/gaze) / iter-4 (body details) targets whose groups appear in `groups_covered`, and the final-suggestion composition starts with `state['labels_candidate'] |= extraction` so the extraction labels survive into `labels_ng_SUGGESTION` for curator review. Extraction is read-only here — `/img_suggest` never mutates `FIELD_LABELS_NG_EXTRACTION`.

Ensure the joy server is running with the requested skin (auto-restarts if a different skin is currently loaded):

```python
joy_client.ensure_running(skin=skin)
```

GPU prereq: at least 16 GiB free for the server's startup. If `ensure_running` raises, surface the same "free the GPU" guidance as `/img_caption` Stage 2.

### 2. Iteration loop (max 5, converge early)

This is a **judgment task**. Read `skin.theme_md_suggestions` §3 for the probe templates and adapt the sequence to the image:

```python
state = {
    'labels_candidate': set(),
    'labels_dropped':   set(),
    'hint_fragments':   [],
    'archetype_guess':  None,
    'iter_traces':      [],  # per-iter (probe, response_head, new_labels, new_hints)
}

for i in range(5):
    probe = compose_probe(state, iteration=i+1, skin=sk)   # judgment
    _, response = joy_client.caption(
        image_url=str(simg.url_from_data),
        user_content=probe,
        system_content=sk.directive,
    )
    new_labels, new_hint_fragments, notes = parse_response(response, state, skin=sk)  # judgment
    state['iter_traces'].append({
        'iter': i+1,
        'probe_head': probe[:120],
        'response_head': response[:200],
        'new_labels': new_labels,
        'new_hints': new_hint_fragments,
        'notes': notes,
    })
    state['labels_candidate'] |= new_labels
    state['hint_fragments'].extend(new_hint_fragments)

    # First probe also checks for not-<skin>-shape: each skin's
    # `<skin>_suggestions.md` §3.1 defines the abort condition. For
    # 1xlasm the test is trigger-phrase compliance; for 1xlface it
    # is "single adult woman in a face shot". Both surface as
    # `status=not-<skin>-shape` for uniform downstream handling.
    if i == 0 and not is_in_skin_shape(response, sk):
        # Image doesn't fit this skin's domain. Abort early — do
        # NOT persist anything.
        abort(f'status=not-{sk.name}-shape — joy did not identify the skin shape')

    # Convergence: at least 2 iterations + nothing new on the last probe
    if i >= 1 and not new_labels and not new_hint_fragments:
        break
```

**Compose-probe heuristic** (per `skin.theme_md_suggestions` §3):

- iter 1: broad scene id (§3.1)
- iter 2: entity locate IF the man's position was vague (§3.2)
- iter 3: pose probing (§3.3)
- iter 4: interaction geometry — the proximity/touch/insertion discrimination (§3.4)
- iter 5: hint-detail capture in curator style (§3.5)

Adapt order based on what each iteration reveals. Skip an iteration's probe if its target was already resolved by a prior iter (e.g. skip iter 4 if iter 1's response was unambiguous about insertion vs touch).

**Iter-5 uses the hint-specific LoRA adapter** (when `skin.lora_hint_path` is set, e.g. for 1xlasm). The captioning LoRA is the wrong distribution for terse curator-style hint generation; iter-5 routes through a separately-trained hint LoRA that closes the hint-jaccard gap from ~0.10 to ~0.39 on held-out validation. Skins without a hint LoRA (e.g. 1xlface as of 2026-05-25) silently fall back to the default adapter — degraded hint quality but the loop still runs:

```python
# iters 1-4 use the default (captioning) LoRA
_, response = joy_client.caption(image_url=..., user_content=probe, system_content=sk.directive)

# iter 5 uses the hint LoRA
_, response = joy_client.caption(image_url=..., user_content=probe, system_content=sk.directive, adapter='hint')
```

The server's `/healthz` reports available adapters in the `adapters` field. If `'hint'` is not in that list, the skin has no `lora_hint_path` configured; iter-5 falls back to the default adapter (with degraded hint quality).

**Parse-response heuristic** (per `skin.theme_md_suggestions` §5):

- map pose words → `primary.pose.*` / `secondary.pose.*` paths
- map interaction words (between, close to, inserted, touches) → `interaction.{proximity,touch,insertion}.*` paths
- map attribute words (busty, slim, hairy, erect penis) → `primary.attribute.*` / `secondary.attribute.*` paths
- map gaze references → `interaction.act.*_look_at_*` paths
- pull verb+bodypart fragments verbatim into `hint_fragments` (for the final hint composition)
- be conservative on body-type opt-in (§5.3) — don't set attribute labels on borderline cases

### 3. Compose final suggestions

After the loop:

```python
final_labels = high_confidence_subset(state['labels_candidate'], state['iter_traces'])
final_hint   = compose_hint_text(state['hint_fragments'], skin=sk)  # curator style
```

`high_confidence_subset` filters per §6:
- ≥2 iterations confirmed AND no contradiction → include
- 1 iteration mentioned, no contradiction → include with `?` flag in report
- contradicted → drop, list in report under "considered but dropped"

`compose_hint_text` produces curator-style hint text from the fragments — see `<skin>.md` §4 (e.g. `1xlasm.md` §4.4 for giantess hints, `1xlface.md` §4.3 for face-shot hints) for the per-skin curator hint style.

### 4. Persist

```python
simg.set_labels_ng_suggestion(final_labels)
simg.set_hints_suggestion(final_hint)
simg.db_store()
```

**Never** call `set_labels_ng`, `set_hints`, `set_caption_*`, etc. The canonical fields are sacrosanct.

### 5. Report

Print under ~30 lines:

1. **header** — image id, iterations run (1-5), convergence reason
2. **per-iteration trace** — for each iter: probe one-liner + response head (~80 chars) + new labels + new hint fragments
3. **final suggestions**:
   - `labels_ng_SUGGESTION`: list of paths (high-confidence ones plain, medium-confidence flagged with `?`)
   - `hints_SUGGESTION`: composed hint text verbatim
4. **considered but dropped** — labels that were probed but didn't make the cut, with reason
5. one-line summary: `suggest_image <id>: iters=N, labels=N (high=N, ?=N), hint=N chars, status=ok|not-<skin>-shape`

## Re-running

`/img_suggest <id>` is fully idempotent — re-running overwrites the previous `_SUGGESTION` fields. Useful when:
- the MD probe templates were updated (re-run to see if metrics improve)
- the joy LoRA was refreshed
- the curator wants to see if a second pass produces a different first-pass

The canonical fields are never touched.

## Access rights

Read access to canonical fields + write to `FIELD_LABELS_NG_SUGGESTION` / `FIELD_HINTS_SUGGESTION` only. Captioning consumes ~16 GiB VRAM via the joy server; ask before starting if the GPU is contested.

## See also

- `/joy_server start|stop|status` — explicit server lifecycle.
- `/imgs_validate_suggestions count=N` — validate the suggestion process against done images as ground truth.
- `/img_caption <id>` — the next step after the curator promotes `_SUGGESTION` → canonical.
