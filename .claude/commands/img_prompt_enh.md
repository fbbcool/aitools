---
description: Stateful per-image prompt-enhancement workflow for the gts factored stack. Image required (no initial prompt input). Stage A confirms tone + main aspects + reframe context on fresh starts; Stage B/C composes/persists each iteration. Per-image doc lives in `prompts_enhanced` (scenes_prod).
argument-hint: "<image_path> [action=show|finalize|abandon|reset]"
---

`$ARGUMENTS` parsing:
- First non-keyword token = **REQUIRED** image path (absolute path to an image file).
- `action=<verb>` keyword arg:
  - `iterate` (default if omitted) — fresh start (with Stage A) OR continue iterating existing doc
  - `show` — print iteration history; no new generation
  - `finalize` — mark status finalized; copy last iteration's prompt to `final_prompt` + clipboard
  - `abandon` — mark status abandoned (kept for audit)
  - `reset` — abandon current doc + start fresh (re-enters Stage A)

If no image path → abort with usage. There is no clipboard-prompt input mode.

## Implicit continuation (Stage C without re-invocation)

Once a doc is `in_progress` for a given `image_url` in the current session, the user does NOT need to re-invoke `/img_prompt_enh <path>` for each successive iteration. Any chat-turn message that reads as **feedback-with-continue-intent** (e.g., "refine it", "try again", "make the lighting harsher", explicit redirection on a specific element) is treated as the implicit trigger for iter N+1:

1. Resolve `image_url` from the most recent `/img_prompt_enh` invocation in the session.
2. Re-read STEP 0 memory file (rules may have evolved).
3. Run Stage 3 (vision pass + composition + audit + persist + clipboard) starting at sub-stage 3.3, attaching the user's chat-turn message as `prior_user_feedback` on iter N before composing iter N+1.

Explicit `/img_prompt_enh <path> action=<verb>` invocation is **still required** for:

- `show` / `finalize` / `abandon` / `reset`
- Entering a fresh image (different `image_url`)
- Re-entering after an explicit session-clear or after the doc went to `finalized` / `abandoned`

Ambiguity rule: if the chat turn is pure commentary with no continue-intent ("looks good", "I'll think about it", "nice", off-topic), do NOT fire iter N+1. Ask if unsure rather than spending a wasted iteration.

## STEP 0 — Load the operating rules (MANDATORY, BEFORE ANYTHING ELSE)

Read this memory file IN FULL **before composing anything**:

```
/home/misw/.claude/projects/-home-misw-venv-aitools-aitools/memory/feedback_prompt_enhance.md
```

It is the **single source of truth**. Even after a context clean this command works because Step 0 explicitly recalls the memory. Do not skip it. Do not paraphrase from prior knowledge — re-read every invocation because the rules evolve.

If you cannot read the file (missing, permission error), abort and tell the user — do not improvise rules from prior-session memory.

## Pipeline

### Stage 1 — Parse args + DB lookup

```python
import re
from pathlib import Path
from datetime import datetime, timezone
from aidb import SceneManager

raw = ($ARGUMENTS or '').strip()

action_m = re.search(r'\baction\s*=\s*(\w+)', raw, re.IGNORECASE)
action = action_m.group(1).lower() if action_m else 'iterate'
if action not in ('iterate', 'show', 'finalize', 'abandon', 'reset'):
    abort(f'unknown action: {action}')

remaining = re.sub(r'\baction\s*=\s*\w+', '', raw).strip()

# Clipboard fallback: if no path in args, try wl-paste.
# Supports a local path (with or without `file://` prefix). HTTP(S) URLs are NOT
# auto-downloaded — abort with a clear message if encountered (cache strategy TBD).
clipboard_source = False
if not remaining:
    import subprocess
    try:
        out = subprocess.run(
            ['wl-paste', '--no-newline'], capture_output=True, text=True, timeout=2,
        ).stdout
    except Exception:
        out = ''
    clip = out.strip().splitlines()[0].strip() if out.strip() else ''
    if clip.startswith('file://'):
        clip = clip[len('file://'):]
    if clip.startswith(('http://', 'https://')):
        abort(f'clipboard contains http(s) URL ({clip[:80]}…); only local paths are supported via clipboard fallback')
    if clip:
        remaining = clip
        clipboard_source = True

if not remaining:
    abort('usage: /img_prompt_enh <image_path> [action=show|finalize|abandon|reset] — or copy an image path to the clipboard and invoke with no args')
p = Path(remaining)
if not (p.exists() and p.is_file()):
    src = 'clipboard' if clipboard_source else 'args'
    abort(f'image path from {src} not found or not a file: {remaining}')
image_path = p.resolve()
image_url_str = str(image_path)
# Mention clipboard_source in the Report so the user can tell where the path came from.

scm = SceneManager(config='prod', verbose=0)
coll = scm._dbc._get_collection('prompts_enhanced')

now = datetime.now(timezone.utc)
doc = coll.find_one(
    {'image_url': image_url_str, 'status': {'$ne': 'abandoned'}},
    sort=[('created_at', -1)],
)
```

### Stage 2 — Handle non-iterate actions

**`action='show'`:**
- If no doc: print `no prior work on this image_url`, stop.
- Else: print summary (status, dynamic, tone, main_aspects, composition_note, total iterations) + per-iteration mini-summaries (n, reframe_context, char_count, user_feedback if any, audit flags). Stop. No DB write.

**`action='finalize'`:**
- Require existing doc with ≥1 iteration.
- Set `status='finalized'`, `final_prompt=last_iteration.enhanced_prompt`, `updated_at=now`.
- Also persist `finalization = {timestamp: now, reason: <free-form from user chat-turn before /cmd, or None>, keeper_iter_n: len(iterations)}`.
- Copy `final_prompt` to clipboard. Print short confirmation. Stop.

**`action='abandon'`:**
- Require existing doc. Set `status='abandoned'`, `updated_at=now`.
- Also persist `abandonment = {timestamp: now, reason: <free-form from user chat-turn before /cmd, or None>}`.
- Stop.

**`action='reset'`:**
- If existing doc: set `status='abandoned'`. Then set `doc = None` and fall through to Stage 3 (fresh start with Stage A).

### Stage 3 — Iterate

#### 3.1 — Vision pass (always)

Use the **Read tool** on `image_path` so the vision pass sees the image. Identify what's in the image: subjects, their poses, spatial relationships, atmosphere. This is used in both Stage A (fresh start) and the audit step (gts-ceiling check) of Stage B.

**JoyCaption hints (optional, on demand).** For ambiguous pose, spatial relationship, anatomy state, or implement-handling details that Claude's vision pass is uncertain about, probe JoyCaption directly via `joy_client.caption(...)` — works on a local path or URL, no SceneImage registration required:

```python
from ait.caption import joy_client
joy_client.ensure_running(skin='1xlasm')   # idempotent; ~23s first time
prompt, caption = joy_client.caption(
    image_url=str(image_path),
    user_content=(
        'Describe this image in detailed natural prose. Focus on: '
        'camera angle/perspective, the two figures and their poses, '
        'spatial relationships (what is touching/squeezing/wedging what), '
        'the implement and how it is held, anatomy state visible.'
    ),
)
```

Do NOT use `/img_suggest` for `/img_prompt_enh` purposes — that path requires the image to be registered as a `SceneImage` and writes `labels_ng_SUGGESTION` / `hints_SUGGESTION`, which is the curator-labeling workflow, not the prompt-enhancement vision-check workflow.

The joy response is **information for Claude to check against, not gospel**. Joy will sometimes surface details Claude missed (fabric pattern, color, micro-feature) and miss details Claude sees (subtle pose, in-frame anatomy state).

**Source-of-truth hierarchy** (HIGHEST → LOWEST): (1) user chat-turn instructions, (2) source-image text-box / in-image narrative caption, (3) Claude's vision read, (4) JoyCaption response. If joy disagrees with the user or the text-box, trust the user / text-box. Joy is a check on Claude, not on the user. See `feedback_prompt_enhance.md` for the worked examples.

Use when: a refinement says "preserve [X]" and Claude is unsure whether [X] is present; or when generations are drifting away from an image-observed pose detail.

Opt-in, not every iter — HTTP-call cost only matters if you're running it on every invocation. Default is Claude's vision pass alone.

Also pull the embedded prompt from PNG metadata (best effort):

```python
embedded_prompt = None
try:
    from PIL import Image
    from ait.tools.images import _image_extract_prompt_from_info_ext
    pil = Image.open(image_path); pil.load()
    embedded_prompt = _image_extract_prompt_from_info_ext(pil.info)
except Exception:
    pass
```

#### 3.2 — Stage A: direction confirmation (only if `doc is None`)

Per the memory's "Stage A — Direction proposal & confirmation" section:

1. From the image, generate a **vision observations bundle** — captured into `stage_a.image_observations` for the corpus:
   - `subjects_present` — `['xlasm_man','xlgts_woman']` or subset
   - `composition_summary` — one-line spatial/pose description
   - `observed_gts_level` — `'mild' | 'moderate' | 'extreme'`
   - `visual_style_seen` — `'cartoon' | 'photoreal' | 'illustration' | 'painted' | ...`
   - `main_aspects_candidates` — the **full** 4-6 candidates Claude generates
   - `tone_candidates` — the 9 tones offered
   - `reframe_candidates` — the 3-4 reframe candidates
   - `recommended_tone` — Claude's best-fit pick
   - `recommended_reframe` — Claude's best-fit pick
   - `detected_dynamic` — `'female_superior'` (default) or `'other'` if image clearly suggests
2. Ask the user via `AskUserQuestion` (up to 4 questions in one call; if `dynamic` override is also suspected, ask Q1–Q4 first and the dynamic question in a second call). **Order matters** — explicit defaults come right after main aspects, before any mood/setting picks:
   - **Q1** `q1_main_aspects` — multi-select; options = 4-6 candidates
   - **Q2** `q2_explicit_defaults` — multi-select; phrased as **opt-outs** for the MAN's defaults. Empty selection = both defaults stay on (the project default for the user, so the natural "do nothing" answer is correct):
     - `opt_out_nudity` — make him CLOTHED instead of nude → sets `man_naked = False`
     - `opt_out_erection` — no erect penis → sets `man_erect_penis = False`
     - Conversion at persistence: `man_naked = 'opt_out_nudity' not in selected`, `man_erect_penis = 'opt_out_erection' not in selected`. Persisted on doc top-level (`man_naked`, `man_erect_penis`) AND inside `stage_a.resolved`.
   - **Q3** `q3_tone` — single-select; options = 9 tones; recommended first
   - **Q4** `q4_reframe` — single-select; options = 3-4 reframe candidates; recommended first
   - **Q5** `q5_dynamic` — only if dynamic-override suspected; single-select `['female_superior (default)', 'other (describe)']`; asked in a SECOND `AskUserQuestion` call to stay within the 4-question cap.

3. Capture the full Q/A exchange into `stage_a.questions` — for each question:
   ```python
   {
       'id':            'q1_main_aspects' | 'q2_tone' | 'q3_reframe' | 'q4_explicit_defaults' | 'q5_dynamic',
       'question_text': str,
       'multi_select':  bool,
       'options':       [{'label': str, 'description': str, 'recommended': bool}, ...],
       'selected':      list[str],          # multi-select-friendly; single-pick → list of 1
       'notes':         str | None,         # free-form 'Other' text if user used that path
   }
   ```

4. Resolve picks into `stage_a.resolved`:
   ```python
   {
       'main_aspects':                  list[str],
       'tone':                          str,
       'reframe_context_v1':            str,
       'dynamic':                       str,                # 'female_superior' default
       'dynamic_override_description':  str | None,         # if 'other', the user's free-form
       'man_naked':                     bool,               # Q4
       'man_erect_penis':               bool,               # Q4
   }
   ```

5. Also copy the resolved values into top-level doc fields for query convenience (`main_aspects`, `tone`, `dynamic`, `dynamic_override`, `man_naked`, `man_erect_penis`, `image_main_aspects`, `image_composition`). Top-level fields are queryable; `stage_a` sub-doc is the full audit trail.

6. Proceed to 3.3 to compose iter 1 with the chosen direction.

#### 3.3 — Stage B/C: composition

If `doc` exists (Stage C resume): **default = keep the prior iter's reframe_context**. Only change it when the user's chat-turn feedback explicitly asks for a different setting / mood / location. The user's chat-turn message before the /cmd is the steering signal — apply it surgically (see the memory's "Surgical-refinement rule": only change what the user explicitly mentions; every other element carries forward verbatim).

If `doc` was just created in 3.2 (Stage B iter 1): use the reframe_context chosen in 3.2.

Compose `enhanced_prompt` applying all rules from the memory:

- Open with VISUAL TREATMENT (camera + diegetic key light tied to the reframe context).
- Express the chosen `tone` through composition cues per the memory's tone table — never through the tone word itself.
- Express `dynamic` through camera position / gaze / posture / light — never through superiority vocabulary.
- Use the user-selected `main_aspects` as the preserved visual hooks; rebuild setting/palette/mood around them via `reframe_context`.
- Include base triggers verbatim (`xlasm man` / `xlgts woman` as appropriate).
- gts amplifier vocab only if image shows that level of disparity.
- Photoreal style cues required.
- If iter > 1 and user feedback included explicit content (anatomy / actions), preserve every token verbatim.

Capture structured composition choices for the corpus:

```python
composition_choices = {
    'camera':           str,    # e.g., 'three-quarter medium-close shot from below'
    'key_light_source': str,    # e.g., 'oculus moonlight' / 'screen-glow' / 'desk lamp'
    'mood_close':       str,    # e.g., 'painterly chiaroscuro' / 'cinematic still moody'
    'tone_cue_used':    str,    # which composition cue from the tone-table row was leveraged
}

iteration_rationale = str  # one-line: why THIS reframe + composition for this iter (esp. relative to prior user_feedback)
```

For iter > 1, also capture user feedback as a structured sub-doc to attach to the **previous** iteration before composing the new one:

```python
prior_user_feedback = {
    'text':                str,             # the user's chat-turn message verbatim
    'timestamp':           datetime,        # now (when this command runs and reads it)
    'source':              str,             # 'chat_message' (default) | 'clipboard' if pulled from there
    'interpreted_intent':  str,             # Claude's read: e.g., "wants industrial instead of religious setting"
}
```

#### 3.4 — Audit (gate-keeping)

Per the memory's "Audit checks" section:

```python
new_lower = enhanced_prompt.lower()

# P1: base triggers
required_triggers = []
if 'man' in scene_subjects: required_triggers.append('xlasm man')
if 'woman' in scene_subjects: required_triggers.append('xlgts woman')
missing_base = [t for t in required_triggers if t not in new_lower]
base_triggers_present = len(missing_base) == 0

# P3: superiority vocabulary ban
SUPERIORITY_VOCAB = [
    'goddess', 'queen', 'empress', 'sovereign', 'ruler', 'mistress', 'his queen',
    'matriarch', 'domina',
    'supreme', 'dominant', 'superior', 'commanding', 'imperious',
    'servant', 'supplicant', 'slave', 'devotee', 'worshipper', 'her pet', 'acolyte',
    'commands', 'rules over', 'lords over', 'dictates', 'subjugates', 'owns him',
]
superiority_vocab_detected = [w for w in SUPERIORITY_VOCAB if w in new_lower]

# P2: gts amplification ceiling — judgment call (compare prompt amplifier vocab vs image-visible disparity)
GTS_AMPLIFIERS = [
    'minuscule', 'extremely minuscule', 'dwarfed', 'monumental', 'looming',
    'towering over', 'looking up the length of', 'low-angle from floor level',
]
amplifiers_in_prompt = [a for a in GTS_AMPLIFIERS if a in new_lower]
# Judgment: for each amplifier in prompt, does the image visibly justify it?
# If image shows him at thigh-height but prompt says 'minuscule' → excess.
# Cannot be fully automated; rely on Claude's vision judgment from Stage 3.1.
gts_amplifiers_excess = [...]  # set per vision-pass judgment

# P4: photoreal style cues
style_cues_ok = any(s in new_lower for s in [
    'photoreal', 'photorealistic', 'maximum realism'
])

# P5: explicit-content preservation — only applicable if prior iterations or current
# user feedback included explicit tokens. Walk the doc's iteration history + current
# feedback for known explicit tokens (handjob, ejaculating, etc.) and confirm each
# is verbatim in the new prompt.
explicit_tokens_in_history = collect_explicit_tokens(doc, current_user_feedback)
missing_explicit = [t for t in explicit_tokens_in_history if t not in new_lower]
explicit_content_preserved = len(missing_explicit) == 0

audit = {
    'required_base_triggers':       required_triggers,
    'base_triggers_present':        base_triggers_present,
    'missing_base_triggers':        missing_base,
    'superiority_vocab_detected':   superiority_vocab_detected,
    'gts_amplifiers_in_prompt':     amplifiers_in_prompt,
    'gts_amplifiers_excess':        gts_amplifiers_excess,
    'style_cues_ok':                style_cues_ok,
    'explicit_tokens_required':     explicit_tokens_in_history,
    'missing_explicit_tokens':      missing_explicit,
    'explicit_content_preserved':   explicit_content_preserved,
}

# P6 + P7: Stage A explicit-content defaults (sticky)
NUDE_TOKENS = ['naked', 'nude', 'bare body', 'bare-bodied']
audit['man_naked_required']        = bool(doc.get('man_naked', True))
audit['man_naked_present']         = any(t in new_lower for t in NUDE_TOKENS) if audit['man_naked_required'] else True
audit['man_erect_penis_required']  = bool(doc.get('man_erect_penis', True))
audit['man_erect_penis_present']   = ('erect penis' in new_lower) or ('his erection' in new_lower) if audit['man_erect_penis_required'] else True
# For erect_penis: if the pose makes the penis fully out-of-frame, mark `man_erect_penis_waived=True`
# in the audit and skip the missing-token failure for that iter. Note the waiver in the rationale.
```

If any check fails (`base_triggers_present == False`, `superiority_vocab_detected != []`, `gts_amplifiers_excess != []`, `style_cues_ok == False`, `explicit_content_preserved == False`, `man_naked_required AND NOT man_naked_present`, `man_erect_penis_required AND NOT man_erect_penis_present AND NOT man_erect_penis_waived`): **fix the prompt and re-audit**. Do not save a known-bad iteration.

#### 3.5 — Persist

```python
iteration = {
    'n':                    (len(doc['iterations']) + 1) if doc else 1,
    'timestamp':            now,
    'reframe_context':      reframe_context_chosen,
    'iteration_rationale':  iteration_rationale,
    'composition_choices':  composition_choices,
    'enhanced_prompt':      enhanced_prompt,
    'char_count':           len(enhanced_prompt),
    'user_feedback':        None,                    # filled by next invocation
    'audit':                audit,
}

if doc is None:
    # Stage A fresh-start: build skeleton + first iteration in one insert
    new_doc = {
        'image_url':          image_url_str,
        'image_id':           image_id,                       # SceneImage id if registered
        'created_at':         now,
        'updated_at':         now,
        'status':             'in_progress',
        'image_main_aspects': stage_a_resolved['main_aspects'],
        'image_composition':  composition_note,
        'embedded_prompt':    embedded_prompt,
        'dynamic':            stage_a_resolved['dynamic'],
        'dynamic_override':   stage_a_resolved.get('dynamic_override_description'),
        'tone':               stage_a_resolved['tone'],
        'man_naked':          stage_a_resolved.get('man_naked', True),
        'man_erect_penis':    stage_a_resolved.get('man_erect_penis', True),
        'stage_a':            stage_a,                        # full sub-doc with observations + Q/A
        'iterations':         [iteration],
        'final_prompt':       None,
        'finalization':       None,
        'abandonment':        None,
        'notes':              None,
    }
    coll.insert_one(new_doc)
else:
    # Stage C resume: append; flush prior-iter user_feedback first if applicable.
    # MUST be two sequential updates — `$set iterations.N.field` and `$push iterations`
    # both touch the path `iterations` and Mongo rejects them in one update with
    # error 40 "Updating the path 'iterations' would create a conflict at 'iterations'".
    if prior_user_feedback is not None:
        prev_n = len(doc['iterations'])
        coll.update_one(
            {'_id': doc['_id']},
            {'$set': {f'iterations.{prev_n - 1}.user_feedback': prior_user_feedback}},
        )
    coll.update_one(
        {'_id': doc['_id']},
        {'$set': {'updated_at': now}, '$push': {'iterations': iteration}},
    )
```

#### 3.6 — Output

Copy `enhanced_prompt` to system clipboard via `wl-copy` (Wayland — pyperclip is unreliable here, do NOT use it):

```sh
printf '%s' "$enhanced_prompt" | wl-copy
```

Same for `action=finalize` — pipe `final_prompt` to `wl-copy`.

## Report (~25 lines)

1. **status** — fresh start (Stage A → B iter 1) OR resumed iter N
2. **image_url** + image_id if registered
3. **direction** — dynamic, tone, main_aspects (the 1-3 picked), composition_note
4. **iter N** — reframe_context_v_N chosen + 1-line rationale (why this context, what user feedback led to it)
5. **audit summary** — `base_triggers=✓/MISSING [...]`, `superiority_vocab=✓/FLAGGED [...]`, `gts_amplifiers=✓/EXCESS [...]`, `style_cues=✓/MISSING`, `explicit=✓/MISSING [...]`
6. **enhanced prompt** — full text verbatim
7. one-line summary: `/img_prompt_enh: iter=N, tone=X, reframe=Y, audit=ok|FLAGGED, chars=N, clipboard=ok, doc=<oid>`

## Access rights

- Read: memory file + image file + clipboard + scenes_prod canonical collections (image_id lookup).
- Write: clipboard + `prompts_enhanced` collection in scenes_prod.
- No mutation of canonical SceneImage / Scene / SceneSet documents.
- No model invocations, no GPU usage.
- Reversible at the document level (set `status='abandoned'` to retire a workflow).

## Resume semantics — important details

- **Implicit continuation.** Within a session, once a doc is `in_progress`, chat-turn feedback-with-continue-intent triggers iter N+1 directly (no need to re-invoke `/img_prompt_enh`). See the "Implicit continuation" section near the top of this file. Non-iterate verbs and new images still require explicit invocation.
- **Clipboard path fallback.** If `/img_prompt_enh` is invoked with NO image path in args, Stage 1 falls back to `wl-paste` and accepts a local path there (with or without `file://` prefix). HTTP(S) URLs are rejected with a clear error — clipboard fallback is local-path-only. Report should note `image_source=args|clipboard`.
- **Doc per image_url, not per session.** Same image across many sessions accumulates into one doc until finalized/abandoned.
- **Stage A choices are sticky.** `dynamic`, `tone`, `main_aspects`, `man_naked`, `man_erect_penis`, `composition_note`, and `stage_a` sub-doc are set once at fresh start and never overwritten by later iterations. They DO change via explicit refinement instructions in chat ("make him clothed", "drop the erection", "swap the setting to X") — that is a normal in-loop edit, not a Stage A reset. `action=reset` is reserved for re-entering Stage A from scratch.
- **`user_feedback` attaches to the iteration it critiques.** Iteration N's `user_feedback` is the user's comment on iter N (filled by iter N+1's invocation, or by `finalize` if N was the keeper).
- **Audit is gate-keeping, not post-hoc.** Failed audits MUST be fixed before persisting. The audit logic exists so future sessions can trust the iteration history is rules-compliant.
- **Record everything structured.** Every Stage A vision observation, every Q/A option set, every user pick, every composition choice, every interpretation of user feedback is persisted. The corpus grows into a queryable record of "what did Claude see → what did Claude propose → what did the user pick → which choice produced which output → what did the user say next → did it converge". Future analysis on this corpus is the feedback loop for evolving the rules.

## See also

- Memory file: `feedback_prompt_enhance.md` — full rules; **always read first**
- `feedback_prompts_to_clipboard.md` — clipboard delivery convention
- `feedback_gts_production_prompt_recipe.md` — production size-emphasis recipe (used inside rewrites, not as the output framing)
- CLAUDE.md "claude_* MongoDB collections" — same access pattern (`_dbc._get_collection`); `prompts_enhanced` is the agreed exception that drops the `claude_` prefix per user spec

## Invocation examples

```
/img_prompt_enh /path/to/img.png                             # fresh start (Stage A → iter 1) OR resume
/img_prompt_enh /path/to/img.png action=show                 # print iteration history
/img_prompt_enh /path/to/img.png action=finalize             # mark done; final_prompt = last iter; copy to clipboard
/img_prompt_enh /path/to/img.png action=abandon              # retire this workflow
/img_prompt_enh /path/to/img.png action=reset                # abandon current + Stage A fresh again
```
