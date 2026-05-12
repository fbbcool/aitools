# 1xlasm — suggestion-process briefing

> **Companion document to `1xlasm.md`. Distinct role.**
>
> `1xlasm.md` (`skin.theme_md`) describes how to *write a final caption*
> from labels + hints — read by `/img_caption` Stage 1 and
> `/imgs_update_caption_prompt`.
>
> **This file** (`1xlasm_suggestions.md`, `skin.theme_md_suggestions`)
> describes how to *derive labels + hints from a blank image* by
> iteratively probing JoyCaption — read by `/img_suggest` and
> `/imgs_validate_suggestions`. It accumulates suggestion-process knowledge
> separately from the captioning compile rules.
>
> Neither file is sent to the captioner; both are inputs to Claude's
> per-image judgment at the relevant stage.

---

## 1. Purpose & JSON/MD split fit

The captioning workflow (`/img_caption`) assumes `labels_ng` and
`hints` already exist on the SceneImage. For a fresh imported image
both are blank. Manually filling them is the slowest step in the
curator's loop — the curator must mentally walk the 80-label taxonomy
plus the four interaction levels (proximity / touch / insertion / act)
plus author the hint in the exact verb-and-bodypart style the
captioning workflow expects.

**The suggestion step automates a first pass.** Claude composes
probing queries, sends each to the captioner (via `joy_client`), parses
the response into label-candidates and hint-material, refines the
next probe, and converges within 5 iterations. Output goes to
`labels_ng_SUGGESTION` and `hints_SUGGESTION` on the SceneImage. The
curator reviews and promotes to canonical fields.

This MD is the *briefing for the suggestion procedure*. It grows as
we observe what works and what doesn't via `/imgs_validate_suggestions`.

---

## 2. The iteration loop

**Max 5 iterations.** Converge early when the latest probe yields
no new labels and no new hint material. Hard cap at 5 to prevent
runaway on ambiguous images.

**System content** for every probe is `skin.directive` (verbatim).
The LoRA was trained on it; switching to a different system_content
risks trigger-phrase non-compliance. Probes inhabit the same context
as final captioning; only the user_content differs.

**State held in-process** across iterations:

- `labels_candidate: set[path]` — accumulating label paths
- `labels_dropped: set[path]` — labels probed and ruled out
- `hint_fragments: list[str]` — verbatim-quality observations
- `archetype_guess: str | None` — best match against §3.2 of
  `1xlasm.md` (held-to-mouth, panties-insertion, etc.)
- `last_iter_added: bool` — convergence check (false on consecutive
  iterations → stop)

**Convergence rule (initial; refine via validation findings)**:

```
converged = (iter >= 2) AND (last_iter_added == False) AND (iter_count_since_addition >= 1)
```

Minimum 2 iterations because the first probe is intentionally broad;
it almost always adds *something*, and convergence-at-1 would skip the
disambiguation probes.

---

## 3. Probing-query templates by iteration depth

Templates below are **starting points** for the typical sequence. The
probe at each iteration should target the *most uncertain* remaining
aspect — sequence may vary based on what iter 1 returns.

**Updated 2026-05-12 (v2 / v4 sequence — CONFIRMED narrative style)**.

After 4 training cycles (v1/v2/v3/v4), the empirically best probe
shape is **narrative requests, not structured (multi-choice / yes/no)
answers**. v3 tested multi-choice and regressed F1 by 0.09 because
joy mis-classifies under forced choice (§4.10).

The 5-step sequence below uses narrative probes that elicit prose
descriptions; the parser then pattern-matches the prose. This is
v2's design preserved through v4. **Do not change to structured
answer formats without strong evidence — multi-choice was tested and
failed.**

### 3.1 Iteration 1 — broad scene id

```
Describe this image in detail. Identify whether a xlgts woman and a
xlasm man are visible. Describe specifically: (1) what the xlgts
woman is doing, (2) what the xlasm man is doing, (3) how they relate
physically. Use specific verbs and body-part references. Distinguish
between "held close to" (no contact), "touching", "pressed against",
and "inserted into".
```

Parse the response for:
- **Trigger compliance**: does joy use `xlgts woman` and `xlasm man`?
  If neither: abort with `status=not-1xlasm-shape`.
- **Initial label candidates**: per §5 mapping rules + §4 anti-bias
  filters.
- **Setting context**: noted but discarded — settings have no
  taxonomy in 1xlasm.

### 3.2 Iteration 2 — interaction discrimination (was iter-4)

```
Focus on the interaction. Pick ONE: (a) the xlasm man is held close
to the xlgts woman but NOT touching her (then name which body part
he is near), (b) the xlasm man is in direct physical contact with
one of her body parts (then name which), (c) the xlasm man is partly
inserted into one of her orifices — mouth, vagina, anus, or panties
(then say which part of HIM is the inserted part: his head, his
upper body, his lower body, or his whole body).
```

This is the proximity / touch / insertion disambiguation — the most
important single discrimination, and the one with the lowest baseline
recall (§7). Promoted to iter-2 so its findings inform later probes.

### 3.3 Iteration 3 — poses and gaze (combined; was two iters)

```
Two questions: (1) Pose: what is the xlgts woman's posture (standing,
sitting, lying on her back, on all fours, kneeling)? What is the
xlasm man's posture (standing, sitting, lying on his back/side,
lifted by her, hanging, kneeling)? Are any limbs spread wide apart
(arms/legs)? Is each figure seen from the front, side, or back?
(2) Gaze: who is looking at whom? Is the xlgts woman looking at
the xlasm man, at his penis, or elsewhere? Is the xlasm man looking
at her or elsewhere?
```

Combined pose + gaze to free a slot. Includes explicit view-angle
question per §5.5 (previously a high-FN area).

### 3.4 Iteration 4 — body attributes

```
Body details: is the xlgts woman visibly busty (very large breasts),
curvy (hourglass figure), slim (slender), or muscular (visible
muscle definition like a bodybuilder)? Does she have visible pubic
hair? Does she have a notably big ass? Is the xlasm man's penis
visible, and if so, is it erect? Answer each question briefly.
```

Probe forces joy to ANSWER each attribute explicitly (yes/no/which),
giving the parser/judgment clean signal. Per §4.2 — body-type
attributes are opt-in; only set the label when the response is
unambiguous *and* uses emphatic adjectives.

### 3.5 Iteration 5 — hint-detail capture

```
In one or two short sentences, describe ONLY the central interaction
between the xlgts woman and the xlasm man. Use the most specific
verbs and body-part references you can. What is each figure's hand
doing? Where exactly is each body part positioned? Use "thumb and
index finger" not "hand" if that's what you see. Use "wrapping
around" not "between" if that's what you see. Skip setting, clothing,
hair, and lighting — only the interaction.
```

Per §4.8: iter-5 response is RAW MATERIAL for hint composition, NOT
a direct hint. Rewrite into curator style:

- 1-2 short sentences, terse.
- Subject = `she` / `he` (not full trigger phrases).
- Specific verb (`holds`, `strokes`, `inserts`, `steps on`).
- Body-part object.
- No setting / clothing / lighting / camera-angle.
- No appearance adjectives.

If iter-5 response is too verbose, extract the 2-3 most specific
clauses and reconstruct in curator style.

---

## 4. Joy biases observed during suggestion

Populated by `/imgs_validate_suggestions` findings. Each entry dated and
cites the validation-run metric that surfaced it.

Format for new entries:

```
- **<bias name>** (observed 2026-MM-DD, n=N imgs): <description>.
  Mitigation: <how the probe template or parsing rule was updated>.
```

### 4.1 Entity attribution drift (observed 2026-05-12, n=15)

Joy frequently uses pronouns or describes both figures in adjacent
clauses, making keyword attribution unreliable. v1's bare keyword
matching on `"standing"`, `"lying"`, `"holding"`, `"muscular"` produced
many FPs because the words landed in the wrong entity's clause:

| pattern        | v1 FPs | v1 explanation |
|----------------|--------|----------------|
| `secondary.pose.standing` | 9 | "the xlgts woman is standing" → matched "standing" without checking it referred to the man |
| `primary.attribute.muscular` | 4 | "muscular man" attributed to woman |
| `primary.pose.lying` | 4 | "she is lying down" overclaimed when she's reclining or semi-upright |

**Mitigation**: at suggest time, attribute every pose/attribute keyword
to the entity it actually describes. Look at the **subject** of the
clause containing the keyword, not just keyword presence. Joy often
writes *"The xlgts woman stands; the xlasm man, by contrast, is lying
on his back"* in a single sentence — you must split on `;` and `.`
to find which subject owns which verb.

When in doubt, drop the label rather than guess. Per §5.3 the
attribute group is opt-in; false positives there are worse than misses.

### 4.2 Body-type adjective over-fire (observed 2026-05-12, n=15)

Even after entity attribution, joy often emits body-type adjectives
descriptively for either figure when the curator did NOT set the
corresponding opt-in label:

| adjective | v2 FPs |
|-----------|--------|
| `busty` / `large breasts` | 7 |
| `curvy` / `hourglass` | 6 |
| `muscular` (about either figure) | 6 |

The curator only sets `primary.attribute.*` for **emphasis**, not
mere body-visibility. *"She has prominently large breasts"* in joy's
output does NOT mean `primary.attribute.busty` should be suggested —
joy describes anatomy as a baseline, the label is reserved for the
curator's authorization of *describing this attribute in the final
caption*.

**Mitigation**: at suggest time, body-type attribute labels are
opt-in ONLY when joy emits the adjective with **clear emphasis**
(*"prominently"*, *"notably"*, *"unusually"*, *"unmistakably"*).
Conservative skip is the default.

### 4.3 `pubic hair` ≠ `primary.attribute.hairy` (observed 2026-05-12, n=15)

11 FPs on `primary.attribute.hairy` because joy mentions pubic hair
whenever it's visible, but the curator only sets `hairy` for **emphasis
on unshaven / natural look**. *"She has pubic hair"* is not enough.

**Mitigation**: only set `hairy` when joy uses one of: *"hairy pubic
area"*, *"unshaven"*, *"natural / untrimmed"*, *"dense pubic hair"*.
Plain *"pubic hair visible"* is descriptive, not authorizing.

### 4.4 Gaze over-claim (observed 2026-05-12, n=15)

9 FPs on `interaction.act.she_look_at_him`, 8 on `he_look_at_her`.
Joy describes gaze in nearly every caption, but the curator only
labels gaze when it's the **central narrative element** — making
eye contact, a directed gaze toward a specific body part, etc. A
person looking generally in the other's direction does NOT warrant
a gaze label.

**Mitigation**: only set gaze labels when joy explicitly says one of:
*"making eye contact"*, *"looking directly at X"*, *"gazing at"*,
*"her eyes are focused on his X"*. Generic *"she is looking at him"*
is not enough.

### 4.5 Insertion-vs-touch confusion (observed 2026-05-12, n=15)

v1 had 7 FPs on `interaction.touch.mouth` because the parser saw
*"her mouth"* in joy's response and tagged touch, even when the
actual interaction was *"his lower body is inserted into her mouth"*.

**Mitigation (already in v2 parser, document for judgment too)**:
when joy describes insertion at a body part, the same-body-part
touch label is SUPPRESSED. The four levels are exclusive — pick the
deepest one applicable.

### 4.6 `holds` ≠ `lifted` (observed 2026-05-12, n=15)

v2 had 5 FPs on `secondary.pose.lifted` from joy's *"she holds him"*
in handjob/blowjob scenarios. *"Holds"* means primary action; *"lifted"*
specifically means *raised off a surface, suspended in her hand(s)*.

**Mitigation**: set `secondary.pose.lifted` only when joy says one
of: *"lifted in her hand"*, *"holding him aloft"*, *"raised off the
ground"*, *"suspended"*, or describes him in her palm/hand with
clearance below. *"She holds him"* alone defaults to NO `lifted`
label.

### 4.7 Iter 4-5 yield diminishes sharply (observed 2026-05-12, n=15)

Across all 15 v1 images, the iteration label-detection profile:

| iter | labels detected (sum across imgs) |
|------|-----------------------------------|
| 1    | 76 |
| 2    | 7  |
| 3    | 14 |
| 4    | 2  |
| 5    | 2  |

Iter 1 (broad scene id) captures most of the signal. Iter 3 (poses
when targeted) adds a meaningful tail. Iters 4-5 mostly produce no
new label info — they exist to capture hint material and disambiguate
gaze, NOT to find more labels.

**Mitigation**: relax the convergence rule so iter-5 ALWAYS runs
for hint extraction even when no new labels added in iters 3-4.
The hint capture is the iter-5 job; convergence on labels can
happen at iter 2-3 without ending the loop.

### 4.8 Terse hint extraction is fragile (observed 2026-05-12, n=15)

Curator hints are **very short** (22-95 chars in the test set) and
written in a specific terse style: *"she steps on his back"*, *"he
is inserted in her panties"*, *"she holds him in her left hand"*.

Joy's iter-5 response describes the interaction in flowing prose
that doesn't directly map to curator-style hints. v2's regex-based
sentence extraction caught only the cosmetic flourishes (*"thumb
and index finger of both hands"*) and missed the central
verb-object pattern.

**Mitigation**: at suggest time, treat the iter-5 response as raw
material and **rewrite** in curator style:

- One or two sentences max.
- Subject = `she` or `he` (not full trigger phrase).
- Verb = specific action (`holds`, `inserts`, `strokes`, `steps on`).
- Object = body part / position phrase.
- Drop all setting / clothing / lighting / camera-angle filler.
- Drop adjectives describing appearance.

If iter-5 response doesn't naturally collapse to that form, look for
the **2-3 most specific clauses** and reconstruct.

### 4.9 Action-step is a distinct verb (observed 2026-05-12)

The F1=0.00 case on `699fefda7488868ef9fff6c5` was caused by the
parser missing `primary.action.step` — the curator-tagged label for
*"she steps on his back"*. v1's keyword table didn't include "step".

**Mitigation**: include explicit step-action recognition:
*"she steps on"*, *"stepping on"*, *"her foot on his body"*. The
action is rare (~9/119 imgs in gts_v3) but distinctive.

### 4.10 Multi-choice probes degrade discrimination (observed 2026-05-12 v3)

Hypothesis going into v3: forcing joy to pick `(a)/(b)/(c)` for
proximity/touch/insertion would clean up the discrimination. Result:
**F1 regressed from 0.45 (v2) to 0.36 (v3) — a 0.09 drop.**

What joy actually does when given multi-choice: it tends to pick
**`(a) "held close to"`** because that's the safest, most visible
interpretation. When the actual interaction is insertion or contact,
joy frequently mis-classifies as proximity under multi-choice
pressure. Examples (2026-05-12 v3 run):

- `69f4d3d3f7b7f5b04564e60f`: truth = `insertion.mouth_body`; joy
  answered `(a) mouth` (proximity).
- `69f5b7ab2ace974433a05894`: truth = `insertion.ass_head`; joy
  answered `(b) leg` (touch — wrong body part too).
- `69f4f1ccf7b7f5b04564e618`: truth = `insertion.panties`; joy
  answered `(a) thighs`.

**Principle**: joy is trained on captioning, which is **narrative**,
not classification. When forced to act as a classifier, it picks
locally-confident answers and the deeper-intimacy levels
(contact/insertion) get under-called. Joy's narrative descriptions
are MORE accurate than its forced choices — the regex parser should
match narrative phrasing, not structured answers.

**Mitigation**: probe templates stay **narrative** (v2 / v4 style).
Don't ask joy to pick a letter; ask joy to describe and use parser
patterns on the description. v4 confirmed this: reverting to narrative
recovered to F1 0.44.

---

## 5. Mapping joy responses to skin labels

The tricky cases. Joy emits prose; the suggestion step has to map
prose to `skin.labels` keys. Common ambiguities:

### 5.1 Proximity vs touch

Joy says *"the xlasm man is between her thighs"* — this could be:
- `interaction.proximity.thighs` (held close to her thighs, no contact)
- `interaction.touch.thigh` (positioned between her thighs, contact)

Disambiguator: does joy describe contact (skin-on-skin) or just
position? Probe iter-4 explicitly asks for the contact-vs-no-contact
discrimination.

### 5.2 Pose: "lying" overclaim

Joy tends to call any reclined or semi-reclined pose "lying". For
the woman in a partly-upright or back-leaning pose, this can
spuriously add `primary.pose.lying`. Mitigation: in iter-3, ask
joy to choose specifically from the listed pose taxonomy; cross-check
against `on_back` / `sitting` for consistency.

### 5.3 Body-type opt-in

`primary.attribute.busty` / `curvy` / `slim` / `muscular` are
**opt-in** in the captioning workflow (per `1xlasm.md` §2.1 — set
only when the curator wants to authorize the description). The
suggestion step should be **conservative**: only set these when joy
emits an unambiguous body description. False positives here add
unwanted body adjectives to the final caption.

### 5.4 Look-at relationships

`interaction.act.she_look_at_him` / `she_look_at_penis` / `he_look_at_her`
are subtle and joy often omits gaze details unless asked. Iter-3
(combined poses + gaze probe) explicitly asks about gaze direction.

**Override**: per §4.4, joy describes gaze in nearly every caption
descriptively. Only flag the gaze label when joy says something
**specific** about the gaze (*"making eye contact"*, *"looking
directly at"*, *"her eyes are focused on his X"*). Generic *"she is
looking at him"* is descriptive, not labelable.

### 5.5 View-angle labels for the man (front/back/side)

Curator-tagged view-angles for the man (e.g. `secondary.pose.front`,
`secondary.pose.side`, `secondary.pose.back`) have HIGH FN rate
(observed 2026-05-12: 10 FNs across 15 imgs). Joy describes the
man's pose and action but rarely emits an explicit view-angle phrase
unless probed.

**Mitigation**: at iter-3 (poses-and-gaze probe), add an explicit
question about view-angle for both figures: *"Is each figure seen
from the front, side, or back?"* — and capture the response.

### 5.6 Insertion directionality (head / upper / lower / body)

The 16 insertion variants split each orifice into 4 directional
sub-labels (`_head`, `_up`, `_low`, `_body`). v1 had 20% recall on
the insertion group because joy says *"inserted into her vagina"*
without specifying which part of HIM is inserted.

**Mitigation**: at iter-2 (interaction-discrim probe), explicitly
ask *"which part of HIM is the inserted part — his head, his upper
body, his lower body, or his whole body?"* and use the answer to
pick the right `_head/_up/_low/_body` variant.

### 5.7 `she holds him` is NOT touch.hand or lifted by default

Joy's most common interaction phrase is *"she holds him"*. This
specifically maps to `primary.action.holding`, NOT:

- `secondary.pose.lifted` — only if explicitly *raised in air*
- `interaction.touch.hand` — only if joy says *"on her hand"*
   referring to his BODY ON HER HAND (rare phrasing)

The default `she holds him` (e.g. holding in a fist, in cupped hands,
against her body) is just `primary.action.holding` + maybe a
`proximity.*` label if she's holding him near a specific body part.

*(Add more cases as `/imgs_validate_suggestions` surfaces them.)*

---

## 6. Confidence / uncertainty markers

Each suggested label carries an implicit confidence based on how many
iterations confirmed it:

- **High confidence** (≥2 iterations confirmed, no contradictions):
  include in `labels_ng_SUGGESTION` without marker.
- **Medium confidence** (1 iteration mentioned, no contradictions):
  include in `labels_ng_SUGGESTION`. Flag in the slash-command
  report with `?` so the curator double-checks.
- **Low confidence** (mentioned but contradicted by another iteration):
  DO NOT include in `labels_ng_SUGGESTION`. Mention in the report
  as "considered but dropped: X (reason: Y)".

Same scale for hint material:

- High: the verb appeared verbatim in ≥2 iterations or once with
  no contradicting paraphrase.
- Medium: appeared once.
- Low: contradicted or only implied.

---

## 7. Validation harness

Run `/imgs_validate_suggestions count=N [set=gts_v3]` to validate the
suggestion process against curator-authored labels+hints on done
images. See the active plan file
(`/home/misw/.claude/plans/elegant-brewing-dawn.md`) for the full
methodology, metrics, and refinement-loop pattern.

**Most recent validation runs**:

| date | n | F1 | recall | precision | hint-jacc | notable |
|------|---|----|--------|-----------|-----------|---------|
| 2026-05-12 v1 (baseline)             | 15 | 0.41 | 0.46 | 0.39 | 0.09 | bare keyword matching; entity attribution failures |
| 2026-05-12 v2 (entity-aware regex)   | 15 | 0.45 | 0.64 | 0.35 | 0.08 | entity-scoped patterns; insertion-suppresses-touch; **+0.17 recall**, no hint gain |
| 2026-05-12 v3 (multi-choice probes)  | 15 | 0.36 | 0.59 | 0.27 | 0.07 | **regressed** — forced (a)/(b)/(c) made joy pick easy proximity over correct contact/insertion |
| 2026-05-12 v4 (narrative + tighter)  | 15 | 0.44 | 0.62 | 0.36 | 0.10 | reverted to narrative; **plateaued** at v2 level despite group-specific patterns |

**Plateau confirmed (2026-05-12)**: prompt-engineering alone on the
existing `fbbcool/joy-gts-lora` ceilings at **F1 ≈ 0.45**. Closing the
gap to acceptance (F1 ≥ 0.70) requires a different intervention — see
`/home/misw/.claude/projects/.../memory/project_hint_lora.md` for the
parked hint-LoRA plan that targets the structural hint-distribution
gap.

Persistent ceilings across all 4 versions:
- `interaction.act` (gaze) group: **0% recall** consistently. Joy
  doesn't volunteer gaze details no matter how the probe is phrased.
  Probable cause: the captioning LoRA was trained to make gaze a
  background detail; can't be coaxed into foregrounding it.
- `interaction.insertion`: **20% recall** consistently. Joy describes
  insertion but rarely with the `head`/`upper`/`lower`/`body`
  directionality the skin taxonomy needs.
- Hint jaccard: **0.07-0.10**. Joy's response distribution doesn't
  include curator-style 22-95 char hints.

v2 per-group recall (15 imgs):

| group | recall |
|---|---|
| secondary.attribute | 100% |
| primary.attribute | 83% |
| primary.action | 75% |
| primary.pose | 67% |
| secondary.pose | 57% |
| interaction.act | 50% |
| interaction.insertion | 20% |
| interaction.touch | 0% |
| secondary.action | 0% |

**Initial acceptance criteria** (set 2026-05-12 baseline; refinable):

- Labels F1 ≥ 0.70 over 30 done imgs
- Hint key-token overlap ≥ 0.60 mean
- Iter-to-converge median ≤ 3
- Per-label-group recall ≥ 0.60 for all groups

**Gap analysis vs current acceptance**:

- F1 0.45 vs target 0.70: gap of -0.25. Closing this requires
  reducing FPs (§4.2, §4.3, §4.4, §4.6) and improving touch /
  insertion / secondary-pose recall.
- Hint jaccard 0.08 vs target 0.60: huge gap. The current
  parser-driven hint extraction fundamentally can't match curator
  terseness. The judgment-driven `/img_suggest` should rewrite
  iter-5 response into curator style (§4.8) — measure this in v3.
- Per-group recall: `interaction.touch` at 0% needs new patterns;
  `interaction.insertion` at 20% needs the directionality probe
  per §5.6.

---

## 8. Maintenance

Same iterative-knowledge accumulation pattern as `1xlasm.md` §8.

Update §4 (joy biases) and §5 (mapping ambiguities) when
`/imgs_validate_suggestions` surfaces a systematic miss. Edit §3 (probe
templates) when a template change measurably improves a metric;
re-run validation to confirm.

Don't add to JSON `rules` or `forbidden` based on suggestion-process
observations — those govern caption *output*, not suggestion *input*.
The split is the same as for `1xlasm.md`.

Dated observations are load-bearing — every claim about joy's
behavior should cite the validation run that produced the evidence.
Format: `(observed YYYY-MM-DD, N imgs, metric=value)`.
