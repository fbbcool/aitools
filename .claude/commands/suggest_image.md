---
description: Iteratively probe JoyCaption to suggest labels_ng + hints for an image. Persists labels_ng_SUGGESTION / hints_SUGGESTION on the SceneImage. Never mutates canonical labels_ng, hints, or caption fields. Max 5 iterations, converge early.
argument-hint: "<image-id>"
---

`$ARGUMENTS` must be a 24-char hex MongoDB ObjectId (regex `^[0-9a-f]{24}$`). Anything else (empty, filter expression, multiple ids) is rejected with a short error — this command is explicitly single-image.

## Why this exists

The captioning workflow assumes `labels_ng` and `hints` are already populated. For a fresh imported image both are blank, and manually filling them is the slowest curator step. This command produces a **first-pass suggestion** by iteratively probing JoyCaption (acting as Claude's "eyes") and parsing each response into label-candidates and hint-material. Output goes to dedicated `_SUGGESTION` fields so the curator can review and edit before promoting.

**Primary input for compose** is `skin.theme_md_suggestions` (the briefing in `conf/skins/1xlasm_suggestions.md`) plus the image itself (via joy probes). Read the MD before composing probes — §3 has the probe templates, §5 has the response→label mapping rules.

## Pipeline

### 1. Pre-state check

```python
from aidb import SceneDef, SceneManager
from ait.caption.skin import SkinRegistry
from ait.caption import joy_client

scm = SceneManager(config='prod', verbose=0)
sim = scm.scene_image_manager()
sk = SkinRegistry().get('1xlasm')
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
          'Running /suggest_image will populate the _SUGGESTION fields '
          'but will NOT touch the canonical fields.')
```

Ensure the joy server is running:

```python
joy_client.ensure_running()
```

GPU prereq: at least 16 GiB free for the server's startup. If `ensure_running` raises, surface the same "free the GPU" guidance as `/caption_image` Stage 2.

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

    # First probe also checks for not-1xlasm-shape:
    if i == 0 and not is_1xlasm_shape(response, sk):
        # Joy didn't identify either trigger; image likely isn't this theme.
        # Abort early — do NOT persist anything.
        abort('status=not-1xlasm-shape — joy did not identify the trigger phrases')

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

`compose_hint_text` produces curator-style hint text from the fragments — see `1xlasm.md` §4.4 for the curator hint style (verbatim verbs + body parts, no setting filler, terse).

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
5. one-line summary: `suggest_image <id>: iters=N, labels=N (high=N, ?=N), hint=N chars, status=ok|not-1xlasm-shape`

## Re-running

`/suggest_image <id>` is fully idempotent — re-running overwrites the previous `_SUGGESTION` fields. Useful when:
- the MD probe templates were updated (re-run to see if metrics improve)
- the joy LoRA was refreshed
- the curator wants to see if a second pass produces a different first-pass

The canonical fields are never touched.

## Access rights

Read access to canonical fields + write to `FIELD_LABELS_NG_SUGGESTION` / `FIELD_HINTS_SUGGESTION` only. Captioning consumes ~16 GiB VRAM via the joy server; ask before starting if the GPU is contested.

## See also

- `/joy_server start|stop|status` — explicit server lifecycle.
- `/validate_suggestions count=N` — validate the suggestion process against done images as ground truth.
- `/caption_image <id>` — the next step after the curator promotes `_SUGGESTION` → canonical.
