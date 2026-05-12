# 1xlasm — theme briefing

> **JSON / MD split (load-bearing convention)**
>
> This file is the **theme briefing** for the 1xlasm captioning skin. It is the
> companion document to `1xlasm.json`. The split is intentional and
> load-bearing:
>
> - **`1xlasm.json`** is the **machine-readable surface**: entity tokens and
>   phrases, label-group taxonomy, compose substitution tables, mechanical
>   validators (forbidden vocab, body-type word gating), concept matchers,
>   model and LoRA references. It is checkable, structured, and exhaustive
>   in what it can encode. It should drift toward a stable structural
>   surface.
> - **`1xlasm.md` (this file)** is the **theme briefing**: what the genre
>   IS, the principles behind anti-patterns, scene archetypes, captioner
>   quirks, stylistic intuition, exemplars. It captures what doesn't
>   compress well into rule rows. It is meant to grow as we learn from
>   curating captions; new insights about the theme accumulate HERE, not
>   as new JSON `rules` entries.
>
> **Who reads what:**
>
> | consumer | reads |
> | --- | --- |
> | **/caption_image Stage 1** (per-image prompt compile, Claude in the loop) | this MD + applied labels + hint + Skin object — primary input |
> | **Batch captioning** (no Claude composing) | JSON-derived `directive` + static label expansions only |
> | **/v1-status, /todo-ai** | JSON `concepts` block |
> | **Validators** (forbidden vocab, body-type, missing-trigger) | JSON-derived lists |
>
> If a rule needs to fire **post-caption** (mechanical check), it lives in
> the JSON. If a rule shapes **what I write** when composing the prompt
> (intuition, style, archetype recognition), it lives here.

---

## 1. The theme

This skin captures the **giantess fantasy** genre as a captioning recipe: a
woman of vastly disproportionate size paired with a small adult-man partner.
The relationship is the central subject of every image — pose, setting,
clothing, lighting all read as supporting context.

The two trigger phrases are nonsense words anchored by the LoRA:

- `xlgts` (woman) — carries the giantess-size concept on its own
- `xlasm` (man) — carries the small-adult-man concept on its own

This is the most important single thing to internalize: **the triggers do the
size work**. A caption should never reach for "tall", "huge", "towering",
"tiny", "little", "miniature", "giantess", or any numerical comparison. The
LoRA was trained to associate the trigger phrases with the size relationship,
so when the model emits `xlgts woman` and `xlasm man`, the size is already
encoded. Adding size adjectives is redundant at best and confusing at worst.

This single principle drives most of the entity-level forbidden vocab.

---

## 2. Entities

### 2.1 xlgts woman (primary)

The giantess. Always referred to in caption text as the literal phrase
`xlgts woman`. Never described with size adjectives.

Body-type adjectives (`muscular`, `busty`, `slim`, `curvy`, `bigass`, `hairy`,
`leggy`) are **opt-in via labels**. The default is to NOT describe her body
type, breast size, or proportions at all. Only when `primary.attribute.<X>` is
set on the image does the corresponding adjective become permitted. This is
enforced post-hoc by the `body_type_words` validator in the JSON.

The rationale: each gts image has a curator-chosen body shape that should be
reinforced in training. Unchecked body-type chatter dilutes that signal.

When she is fully nude, place `naked` **inside the noun phrase at first
mention** — `a naked xlgts woman`. Never as a standalone sentence (`She is
naked.`) and never as an appositive (`The xlgts woman, naked, ...`). Once
nudity is established at intro, do not repeat it.

### 2.2 xlasm man (secondary)

The smaller adult-man partner. Always referred to as the literal phrase
`xlasm man`. Always adult-proportioned, regardless of his apparent size in
the frame.

He must NEVER be diminished: no `tiny`, `little`, `miniature`, `figurine`,
`doll`, `toy`, `puppet`, `child`, `kid`, `boy`, `teenager`, `shrunken`,
`dwarf`. His size *relative to her* is encoded by the trigger; his
*absolute* nature is "adult man".

Do not describe his body build with generic terms (`muscular`, `athletic`,
`fit`, `with a build`, `has a build`, `shirtless`). Describe specific
anatomical details when relevant: erect penis, beard, short hair, eyes
closed, neutral expression. Specifics over abstractions.

Same noun-phrase nudity rule as the woman: `a naked xlasm man` at first
mention; never `is naked, with X` (a recurring captioner habit that
collapses two ideas — nudity + an attribute — into a clumsy joined
clause).

He can be **hard to spot** in busy images. When you compose a per-image
prompt, search the image deliberately for him before claiming he isn't
visible.

---

## 3. The interaction is the central subject

Every 1xlasm image is, fundamentally, **about how she and he interact**.
Describe the interaction first, in greatest detail. Setting, clothing, hair,
makeup, background, lighting, and camera angle come strictly *after* the
interaction is fully described.

### 3.1 Four levels of intimacy

**Important framing.** The label taxonomy below sorts each image into a
bucket — `proximity.mouth`, `touch.thigh`, `insertion.vagina_up`, etc. —
and each bucket has a static `expansion` sentence in the JSON. **These
expansions are coarse approximations of what is actually happening in the
image.** They are scaffolding, not finished prose. The precise content of
the interaction — which body parts touch where, with which verbs, in which
direction — lives in the **curator hint** (see §4.1). At prompt-compile
time, use the hint as the source of truth for the interaction's specifics
and the labels as confirmation that the broad category is correct.

The interaction taxonomy is graded by escalating physical intimacy:

1. **proximity** (`interaction.proximity.*`) — she holds him *near* a body
   part of hers, without contact or insertion. "Held close to her mouth",
   "close to her breasts". Often a lead-up pose. Six body-part variants.
2. **touch** (`interaction.touch.*`) — physical contact without penetration.
   "Interacts with her foot", "between her thighs". The man (subject) makes
   contact with the woman's body part (object). Eleven variants.
3. **insertion** (`interaction.insertion.*`) — partial penetration of one of
   the woman's orifices (vagina, mouth, ass) or her panties. Sub-coded by
   which part of the man is inserted: `head`, `upper body`, `lower body`,
   `body` (whole). Sixteen variants total.
4. **act** (`interaction.act.*`) — named compound acts: blowjob, handjob,
   teasing handjob, masturbation, sex; directional looking
   (`she_look_at_him`, `he_look_at_her`, `look_at_each`,
   `she_look_at_penis`).

When multiple layers apply to one image, **use the most specific**. If
`insertion.vagina_up` is set, that's the dominant fact; proximity to her
vagina is implicit. If `touch.thigh` is set, don't also emit "close to her
thigh".

### 3.2 Scene archetypes

The following archetypes recur enough that recognizing them at prompt-compile
time helps shape the caption:

**Held-to-mouth (the lifted blowjob position).** `proximity.mouth` +
`pose.lifted` (man) + often `pose.standing` (woman) + often
`action.blowjob`. She lifts him close to her face/mouth; his torso or upper
body sticks out from her hands or lips. Frequently in profile (man side
view). The caption should open with the holding gesture, then the blowjob if
applicable.

**Between her thighs.** `touch.thigh` + woman sitting/lying/legs_spread. He
is captured between her thighs; his body is dwarfed by them. Composition:
his torso between her legs, often facing her crotch.

**Inserted into her panties.** `insertion.panties` + often `hairy` +
`standing` (woman). Describe geometry around the waistband: his lower body
hidden below the fabric; his upper body and head visible above, or vice
versa depending on orientation. Don't say `inserted into her panties` and
stop — describe **what is visible above and below the waistband**.

**All-fours position.** `pose.all4` (woman) + insertion/proximity to mouth
or breasts. She is on hands and knees; he is in her hands, in her mouth, or
between her breasts. Often paired with `look_at_him`.

**Standing tower.** `pose.tower` (woman, indicates she stands directly above
him) + man standing or seated near her feet. Classic giantess-size-display
composition.

**Vaginal insertion.** `insertion.vagina_*` (woman often `lying` +
`on_back` + `legs_spread`). He is partly inside her vagina; one of {head,
upper body, lower body} is the inserted part. Caption should lead with the
insertion, then the woman's pose underneath, then setting.

When an image doesn't fit any archetype cleanly, the labels alone usually
suffice — compose from the label expansions and let the captioner handle
specifics.

---

## 4. Captioning style

### 4.1 Hints are the spine; labels confirm

**Read this section first.** The compile model is **NOT** *"render every
label expansion, then append the hint as an addon"*. The hint is the
**primary source of contextual truth**; labels are coarse approximations
that confirm/refine specific aspects of what the hint already describes.

**Why this matters.** Labels sort each image into a bucket. The bucket
has a generic `expansion` sentence ("The xlasm man is positioned between
the thighs of the xlgts woman."). But the actual image is *more
specific* than the bucket — the man may be *immersed in her pubic hair*,
*wrapping his arms around her thigh*, *facing her crotch*, etc. — and
those specifics live ONLY in the hint. The curator wrote the hint
precisely because the labels couldn't capture what mattered.

**The compile workflow.** When composing a per-image caption_prompt:

1. **Read the hint first.** Treat it as the spine of the interaction
   description. The hint's verbs, body parts, and spatial relationships
   are the precise content; whatever the labels say in their generic
   expansions is approximate.

2. **Pull `render_label_prompts(labels_ng)` second.** For each rendered
   sentence: ask *"does the hint already say this, possibly with different
   wording?"*
   - **Hint covers it**: drop the label expansion. Keep the hint's
     phrasing. (E.g. label = *"The xlasm man is positioned between the
     thighs..."*; hint = *"he stands between her thighs..."* — keep the
     hint phrasing, drop the label expansion. The label served its
     purpose by confirming the broad category.)
   - **Hint is silent on it**: include the label expansion. (E.g. pose
     labels and attributes the hint doesn't mention — `primary.attribute.hairy`
     → include "Her pubic area is hairy" as its own short clause.)
   - **Hint contradicts the label expansion** (rare): trust the hint;
     the label is a coarse bucket and may have miss-fit the specific
     geometry. Flag for follow-up if it recurs.

3. **Compose interaction sentences using hint vocabulary.** Fuse hint
   phrases with label-confirmed details into one or two fluent
   sentences. The hint provides the verb structure and specific
   observations; the labels validate that those observations fall under
   the right category.

   > Hint: "he stands between her thighs. he is immersed in her pubic hair."
   >
   > Labels: `touch.thigh`, `secondary.pose.standing`, `primary.attribute.hairy`
   >
   > **Wrong** (label-spine, hint-as-addon):
   > "The xlasm man is positioned between the thighs of the xlgts woman.
   > The xlasm man is standing upright. Her pubic area is hairy.
   > Additionally: he stands between her thighs. he is immersed in her
   > pubic hair."
   >
   > **Right** (hint-spine, labels confirm):
   > "The xlasm man stands between the xlgts woman's thighs, immersed in
   > her hairy pubic area." — one sentence; uses the hint's `stands` verb
   > (confirmed by `secondary.pose.standing`); uses the hint's `immersed`
   > verb (uniquely the hint's contribution); uses `hairy` from the
   > attribute label.

4. **Preserve hint verbs and body-part references verbatim.** Don't
   paraphrase: keep `thumb and index finger` as is (don't collapse to
   `hand`); keep `wrapping around` as is (don't collapse to `between`);
   keep `inserted` as is (don't soften to `positioned`); keep `palm` as
   is (don't generalize to `hand`). Downgrading the language loses
   signal.

5. **Hint absence is meaningful.** A `hints` value of `'none'`
   (case-insensitive) is the explicit *"no extra detail beyond the
   labels"* sentinel. In that case, fall back to a label-driven
   compose — the labels are all you have. Drop the user-hint preamble
   entirely.

**Hint-threading pattern — don't duplicate the hint.** When threading
the hint into the per-image prompt, pick ONE pattern to carry it. Either:

- **Verbatim pattern — hint as input cue.** Include the hint sentences
  verbatim with a *"Preserve every verb and body-part reference exactly:
  …"* lead-in. Let the captioner compose its own integrated sentence
  using the hint vocabulary. Do NOT also pre-write the integrated
  sentence — the model will treat your pre-written version as a
  paraphrase target and produce multiple variants in the output.

- **Prefused pattern — pre-composed integrated sentence.** Write the
  integrated sentence yourself in the prompt (hint vocabulary woven with
  label-confirmed details). In this case, OMIT the verbatim hint line —
  the integrated sentence already carries the vocabulary you want
  preserved. You may still keep a short *"Use the hint vocabulary
  verbatim"* directive, but don't quote the hint sentences again.

**Including both — verbatim hint AND a pre-composed paraphrase of the
same content — invites the model to produce many paraphrases and triggers
a repetition spiral.** Pick one pattern and stick with it for this image.

Heuristic for choosing:

- If the hint phrasing is **clean and complete on its own** (full
  sentences with subject + verb + object, no missing detail the labels
  need to fill in), use the **verbatim pattern** — let the model
  integrate. The hint vocabulary is already a usable sentence template.
- If the hint is **terse, fragmentary, or needs label-driven gap-filling**
  to read fluidly (e.g. *"between thighs, head close"*; or hint plus
  3+ labels that the captioner needs help fusing), use the
  **prefused pattern** — write the integrated sentence yourself, drop
  the verbatim.
- If the hint **contains obvious typos or word-break errors** (e.g.
  *"he stands on he rknee."* with `rknee` for `her knee`), use the
  **prefused pattern** and silently fix the typo in the pre-composed
  sentence. The verbatim pattern passes the typo through, and the
  captioner may **silently drop the affected phrase rather than
  reconstruct it** — observed (2026-05-12) on image
  `69ba8248d29e12c318936f4d`, where the "he stands on her knee" detail
  was completely omitted from the caption_joy because the hint had a
  word-break typo. The curator's caption fixed the typo and the detail
  survived; the prefused pattern at compile time has the same effect.

Observed failure (2026-05-12): hint *"he stands between her thighs. he
is immersed in her pubic hair."* with prompt containing BOTH the
verbatim hint AND a pre-composed sentence *"The xlasm man stands between
the xlgts woman's thighs, immersed in her hairy pubic area."* → the
captioner produced 5 paraphrases of the same scene plus an `is naked,
with` violation. Either pattern alone would have produced a clean
caption. The forbidden-vocab validator caught the §5.1 violation at
Stage 3, but the bloated prose was not auto-fixable.

**What this means for curators.** Hints should capture *what isn't
already a label*: precise hand placement, specific verbs, spatial
nuances, body-part level (palm vs hand, arm vs hand), expressions,
gaze direction, etc. Common/recurring patterns ("she holds him close
to her mouth") were promoted to labels (the `proximity` group) so that
they can be sanctioned mechanically; the hint slot reserves itself for
the per-image specialty.

### 4.2 Opener pattern

Every caption opens with a **single complete sentence naming BOTH trigger
phrases together**. The default opener is:

> This image features a [naked] xlgts woman and a [naked] xlasm man.

`naked` is included only for the figure(s) that are actually fully nude. If
neither is, drop both adjectives. If both are, include both.

Never open with a noun-phrase fragment. Never open with a description of
setting or clothing.

**Strong-default, not hard rule.** Both trigger phrases MUST appear in the
caption — that's enforced by the `missing_triggers` validator. The
"BOTH in one sentence" requirement is a strong stylistic default but not
hard. Observed in practice: the model sometimes produces a tighter caption
by opening directly with the dominant figure's action (e.g.
*"The naked xlgts woman lies on her back with her legs spread wide
apart."*) and introducing the second trigger in the very next sentence
(*"The naked xlasm man is partly inserted into her vagina..."*). When the
labels strongly favor one figure as the immediate subject (e.g.
`insertion.vagina_*` with the woman in a lying pose), this two-sentence
opener can read better than forcing both into one. Accept it; both phrases
are present, the validator is satisfied, and the prose is cleaner.

The default literal opener stays the right choice when both figures are
prominently visible and equally subjects of the interaction (e.g.
`proximity.*` or `holding` archetypes).

### 4.3 Interaction first, ambient second

After the opener, describe the interaction in detail using the **hint
vocabulary** (§4.1) and the **specific verbs** the hint provides. Only
after the interaction is fully captured should the caption mention
setting, clothing, hair, makeup, background, lighting, or camera angle.

This ordering matches what a giantess-genre LoRA needs to learn from each
training image: the interaction is the signal; the ambient context is
secondary noise that should be present (for grounding) but not
foregrounded.

### 4.4 Pose combination

When multiple pose labels apply to the same figure (e.g. `lying` +
`on_back` + `legs_spread` on the woman), **combine them into one fluent
compound sentence** rather than emitting each as a standalone clause.

> Good: "The xlgts woman is lying on her back with her legs spread wide apart."
>
> Bad: "The xlgts woman is lying. The xlgts woman is on her back. The xlgts woman has her legs spread wide apart."

Same for the man: `lying` + `on_back` + `arms_spread` → "lying on his back
with his arms spread wide apart."

The compose mechanism in the JSON handles this for proximity verbs
automatically (selecting between "stands close to", "lies close to", "sits
close to", etc., based on the man's postural pose). For other groups the
combination is done at prompt-compile time by writing a fused sentence
manually.

When the hint already describes a pose (e.g. *"she lies on her back
between his legs"*), defer to the hint's phrasing per §4.1 and drop the
matching label expansions.

### 4.5 Action-domain fusion

The same principle as §4.4 (pose combination) extends to **action-domain**
labels. When multiple labels from the same action domain describe one
compound scenario, fuse them into one or two compact sentences in the
per-image prompt rather than emit each label expansion as its own line.

Without action-fusion the captioner dutifully emits each label as a
separate clause, producing 50-70% length inflation vs the curator's tight
phrasing.

**Canonical compounds — drop the listed redundancies and emit one fused
sentence:**

| domain | label combo | fused sentence | redundancies to drop |
|---|---|---|---|
| blowjob | `primary.action.blowjob` + `primary.action.holding` + `secondary.pose.lifted` | *"She gives the xlasm man a blowjob, holding him lifted close to her mouth."* | the bare `holding` and `lifted` expansions are absorbed |
| handjob | `primary.action.handjob` + `interaction.touch.hand` | *"She gives the xlasm man a handjob, stimulating his penis with her hand."* | the bare `touch.hand` expansion is absorbed |
| held / lifted | `primary.action.holding` + `secondary.pose.lifted` (no further action) | *"She holds the xlasm man lifted in her hand(s)."* | one or the other label can be dropped; the lifted expansion already implies she holds him up |
| insertion | `interaction.insertion.X` + `secondary.attribute.penis` | *"He is inserted into her X with his erect penis."* (or omit "with his erect penis" entirely — implicit) | the bare `penis` expansion is redundant when an active insertion is described |
| handjob + cum | `primary.action.handjob` + `secondary.action.cum` | *"She gives him a handjob; he ejaculates."* | two separate sentences are acceptable here since cum is a distinct event |

**Observation that motivated this rule** (2026-05-12 baseline, 30-img
test): the deterministic compose without action-fusion produced
caption_joy outputs 47%-72% longer than the curator's tight phrasing on
5/30 images — all of them blowjob/handjob/holding/lifted scenarios with
4-7 same-domain labels. None had repetition spirals; the captioner was
faithfully emitting each label expansion as its own sentence because the
prompt stacked them.

**Heuristic.** Before writing label-expansion sentences in the per-image
prompt, group labels by domain:

- pose labels by figure → fuse per §4.4
- action labels (blowjob, handjob, holding, teasing_hj, masturbating) +
  closely-related interaction labels (touch.\*, insertion.\*) → fuse per
  §4.5 (this section)
- attribute labels (penis, hairy, busty etc.) → standalone short clauses,
  no fusion needed
- act labels (look-at-X) → standalone short clauses, no fusion needed

---

## 5. Anti-patterns (with the reasoning)

The following patterns recur as joycaption failure modes. Each rule has a
*why* — understanding the principle helps me catch novel variants at
prompt-compile time and produces less brittle behavior than chasing each
new symptom with a new rule row.

### 5.1 `"is naked, with X"`

> ❌ "The xlasm man is naked, with an erect penis."
>
> ❌ "The xlasm man is naked, with his arms spread wide."
>
> ✅ "The xlasm man has an erect penis." (nudity in noun phrase at intro)

**Principle:** nudity is a property of the figure, established once at first
mention via the noun phrase. After that, the figure can have body parts,
poses, attributes — but those should be expressed as `has X` /
`<verb> X`, not as appositives to `is naked`. The "is naked, with X"
construction conflates two unrelated assertions and reads as awkward.

### 5.2 The comma-appositive `", naked,"`

> ❌ "The xlgts woman, naked, lies on her back."
>
> ✅ "The naked xlgts woman lies on her back."

**Same principle**: nudity binds to the noun, not as a side comment in a
later sentence.

### 5.3 Repeated `naked` descriptions of the same figure

> ❌ "The xlgts woman holds the naked xlasm man. The naked xlasm man smiles."
>
> ✅ "The xlgts woman holds the naked xlasm man. The xlasm man smiles."

**Principle:** the first mention establishes nudity; subsequent mentions take
it as given. Repeating it makes the prose redundant.

### 5.4 `"is shirtless"` / `"has a build"` / `"with a build"`

> ❌ "The xlasm man has a beard and is shirtless, with his arms crossed."
>
> ❌ "The xlasm man is naked, with a build."
>
> ❌ "The xlasm man is naked, with a muscular build and light skin." (adj variant)
>
> ✅ "The xlasm man has a beard, with his arms crossed."

**Principle:** generic body-build adjectives don't describe anything
specific. The man is already established as `xlasm man` (adult); body-shape
chatter dilutes that. Either drop or replace with a specific anatomical
detail.

**Adjectival variant — `with a <adj> build`.** Joycaption sometimes
emits *"with a muscular build"*, *"with a slim build"*, *"with a
toned build"* about the man. Same anti-pattern as bare `with a build`
with an adjective inserted. The current JSON `forbidden` regex
`with a build` does NOT match the adjectival form (different substring),
so this slips the post-hoc validator. Observed 2026-05-12 on image
`69f4b1c4f94a40ee841afc04` — *"…is naked, with a muscular build and
light skin."* (the §5.1 anti-pattern and the §5.4 adjectival variant
combined into one clause).

When composing a per-image prompt for an image where the man is fully
nude AND his torso is visible, add an explicit guard alongside the §5.1
guard: *"and do not describe the xlasm man's body build (no `muscular
build`, `slim build`, `toned build`, etc.); describe specific anatomical
details only."*

**Note on man-side body adjectives more broadly.** The
`body_type_words` mechanical validator gates the **woman's** body
adjectives (busty/muscular/slim/curvy) via the
`primary.attribute.<X>` labels. There is no parallel mechanism for the
man — `muscular`/`slim`/`toned` applied to him slip both the woman-side
check (because the authorizing label is on a different entity) and the
bare `with a build` regex (because of adjective insertion). For now,
the workflow's safety on this leak relies on (a) the inline prompt
guard above, and (b) any explicit Stage-3 auto-fix the curator chooses
to apply. A schema bump adding per-entity body_type_words is
deferred — the JSON should stay close to a stable surface per the
JSON/MD split convention.

### 5.5 Watermarks, logos, brand text

> ❌ 'The image has a watermark in the bottom right corner that reads "BRAZZERS.COM".'

**Principle:** overlaid text is artifact of the image source, not part of
the depicted scene. The training signal should be about the scene, not the
provenance. Treat watermarks as invisible.

### 5.6 Filler verbs

> ❌ "His head is positioned between her pubic area and the waistband."
>
> ❌ "The xlgts woman's breasts are visible."
>
> ❌ "The xlgts woman's skin is light, and the xlasm man's skin is also light."
>
> ✅ "His head is between her pubic area and the waistband."
>
> ✅ (if the breasts are doing something) "She squeezes her breasts." — or just drop the sentence.

**Principle:** `is positioned`, `is visible`, `is centered`, `is also` are
filler verbs that don't carry information. Pick a specific verb that
describes what is happening, or omit the clause entirely. "Is visible" in
particular adds nothing — if a body part is described, the reader already
knows it's visible.

**Adjacent-property restatement (the `is also <adjective>` pattern).**
A recurring joycaption habit is the symmetric restatement of an ambient
property across two figures: *"the xlgts woman's skin is light, and the
xlasm man's skin is also light"*, or *"the lighting is soft. the
background is also soft."* This is low-information filler — the second
clause repeats the same adjective without adding anything observable.
When both figures share a generic adjective (skin tone, light level,
background quality), describe it once or drop it. NOT a hard ban — the
curator-kept rate for `is also` in the gts_v3 dataset is ~82%, so the
phrase has legitimate uses (e.g. *"she is also wearing X"* introduces a
new property). The anti-pattern is specifically `X is also <flat
adjective>` with no new content.

Why this stays in MD instead of JSON `forbidden`: a flat regex on
`is also` would over-fire on the 82% of cases where the curator keeps
it. The judgment of *"does this clause add information?"* is intuition,
not a mechanical rule.

---

## 6. Captioner quirks (Joycaption + gts LoRA)

The base model is `fancyfeast/llama-joycaption-beta-one-hf-llava` with
`fbbcool/joy-gts-lora` (variant `capjoy/common`). Known tendencies (observed
across 119 done images in `gts_v3`):

- **Adds `is naked, with X`**: deeply learned anti-pattern in the base
  joycaption weights. Without inline prompt guards: ~15% of captions
  (18/119 in the unconstrained baseline). **With explicit inline guards
  in the per-image prompt: still ~7% (2/30 in the 2026-05-12 hint-spine
  baseline).** Treat as a Stage-3 auto-fix concern — the JSON forbidden
  validator catches it post-hoc, and the workflow's safety on this leak
  relies on that backstop, not on the prompt-time guard being 100%
  effective. Heuristically rewrites to noun-phrase nudity or `has X`.
- **Adds generic body builds**: `has a build`, `with a build`, `shirtless`
  ~13× across 119 (unconstrained); 0/30 with inline §5.4 guards
  (2026-05-12) — but adjectival variant `with a <adj> build` slips the
  validator (see §5.4). Rewrite to specific anatomy or drop.
- **Repeats `naked`**: emits `naked xlasm man` and later `He is naked.`
  redundantly. First mention only.
- **Describes watermarks** when present: ~5/119. Strip.
- **Over-describes setting**: tends to add a sentence on lighting,
  camera angle, composition, often as filler. Curator-final captions
  trim these to one-line maximum.
- **Pose labels get emitted as separate sentences**: even when 3 woman-pose
  labels are set, joy emits them as 3 standalone sentences instead of one
  fused sentence. Same behaviour for same-action-domain labels
  (blowjob + holding + lifted + side → 4 separate sentences instead of
  1 fused). Compose-time intervention is needed; see §4.4 (pose-fusion)
  and §4.5 (action-domain fusion).
- **Length inflation when 4+ same-domain labels apply**: observed
  +47%-+72% inflation on 5/30 imgs (2026-05-12 baseline) when the
  per-image prompt stacks each label expansion as its own sentence
  instead of fusing the same-domain ones. No repetition spirals — just
  faithful over-emission. §4.5 is the mitigation.
- **Silently drops typo'd hint phrases**: if a hint contains an obvious
  typo (word-break errors like `he rknee` for `her knee`), the
  verbatim pattern preserves the typo verbatim and the captioner may
  omit the affected phrase from the caption entirely rather than
  reconstruct it. Observed 2026-05-12 on `69ba8248d29e12c318936f4d`.
  See §4.1 ("typo'd hints → prefused pattern").
- **`primary.pose.on_back` had a JSON bug** ("is on his back" for the
  woman). The model is robust enough to flip the pronoun in context, but
  the bug was fixed; future labels should be sanity-checked for pronoun
  agreement before being added.

Joycaption is otherwise reliably good at:

- Following the trigger phrases (100% compliance across 119)
- Respecting the body-type opt-in (0 unauthorized leakage)
- Following hints (~87% verbatim word overlap)
- Producing structurally sound, grammatical English

So the model is *capable*; it just has stylistic habits we need to compose
around.

---

## 7. When to put MD context into the per-image caption_prompt

The MD doesn't reach the captioner directly. Only the directive (from the
JSON) + the per-image `caption_prompt` (composed at /caption_image Stage 1)
do. So the practical workflow is:

1. Read this MD at Stage 1 to recognize the archetype + theme principles.
2. Identify which anti-patterns are likely for this specific image (e.g.
   if the man is fully nude and the image is busy, the `is naked, with`
   risk is elevated — bake an inline note into the per-image prompt).
3. Identify which compose decisions matter (e.g. if `secondary.pose.lying`
   is set with a proximity label, mention the expected verb form in the
   per-image prompt).
4. Write a tight ~400-1000 char per-image prompt that includes the
   hint verbatim, the applied label expansions, and any inline guidance
   pulled from this MD.

The MD is for *me*; the per-image prompt is what *I write down* after
reading the MD, distilled to what matters for this one image.

---

## 8. Maintenance

This document is the **iterative theme record**. As we curate more captions
and observe new failure modes, the corrections go here (as anti-patterns
with reasoning) before they go into the JSON. Once an MD principle is
mature enough to mechanize (a hard forbidden phrase, a `compose` table
substitution), it can be lifted into the JSON; otherwise it lives here
as guidance.

**Do not** add to the JSON's `rules` arrays without first asking whether
the new entry is genuinely mechanical (i.e. catchable by a post-hoc
validator or a substitution table) or actually intuition (in which case
it belongs here). The JSON should drift toward a stable structural surface
over time.

Updates to this document should be **dated** and **brief**. New
anti-patterns under §5; new captioner quirks under §6; new archetypes
under §3.2. The JSON's `migration` log captures schema-shape evolution;
this MD captures theme-shape evolution.
