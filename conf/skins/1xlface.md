# 1xlface — theme briefing

> **JSON / MD split (load-bearing convention)**
>
> This file is the **theme briefing** for the 1xlface captioning skin. It is
> the companion document to `1xlface.json`. The split is intentional and
> load-bearing:
>
> - **`1xlface.json`** is the **machine-readable surface**: entity token /
>   phrase, label-group taxonomy, label expansions, mechanical validators
>   (forbidden vocab — identity / persona / minor / meta), concept stub,
>   model and (eventual) LoRA references. It is checkable, structured, and
>   exhaustive in what it can encode. It should drift toward a stable
>   structural surface.
> - **`1xlface.md` (this file)** is the **theme briefing**: what the genre
>   IS, the principles behind the three load-bearing constraints
>   (ADULT-ONLY, PERSONA WORD BAN, IDENTITY SUPPRESSION), captioner
>   quirks, stylistic intuition. It captures what doesn't compress into
>   rule rows. It is meant to grow as we curate captions and observe new
>   failure modes; new insights about the theme accumulate HERE, not as
>   new JSON `rules` entries.
>
> **Who reads what:**
>
> | consumer | reads |
> | --- | --- |
> | **/img_caption Stage 1** (per-image prompt compile, Claude in the loop) | this MD + applied labels + hint + Skin object — primary input |
> | **Batch captioning** (no Claude composing) | JSON-derived `directive` + static label expansions only |
> | **/v1-status, /todo-ai** | JSON `concepts` block (currently a residual `general` stub) |
> | **Validators** (forbidden vocab, missing-trigger) | JSON-derived lists |
>
> If a rule needs to fire **post-caption** (mechanical check), it lives in
> the JSON. If a rule shapes **what I write** when composing the prompt
> (intuition, style, identity-vs-state discrimination), it lives here.

---

## 1. The theme

This skin captures **closeup face shots of a specific adult woman** as a
captioning recipe for **avatar-LoRA training**. One dataset = one LoRA =
one specific woman. The LoRA learns her face / identity and generalizes
over everything else.

**PERSONA**: she is a dominatrix. Datasets typically include variable
wardrobe across shots — masks, collars, harnesses, gags, sometimes
'civilian' shots without fetish wardrobe. The persona is identity (it is
constant across the dataset), not state.

The single most important thing to internalize is the **avatar-LoRA
decoupling principle**:

> **What is constant across the dataset → the LoRA learns as part of the
> trigger. The captioner must NOT describe it.**
>
> **What varies across the dataset → the LoRA learns to decouple from
> the trigger. The captioner MUST describe it, accurately, for every
> shot.**

Anything in the caption attaches to the variable signal, NOT to the
identity trigger. Captioning a constant feature teaches the LoRA to
recombine that feature away from the trigger — the opposite of what an
avatar LoRA needs.

This principle drives every load-bearing rule below.

---

## 2. Entity

### 2.1 The woman (primary, single entity)

There is no `secondary` and no `interaction` block — this skin is
single-entity by design. The image is **about her face**; whatever else
is in frame (background, props, partial body) is incidental and should
not be foregrounded.

She is referred to as `the woman` at first mention, then `her` / `she`.
**Never** as `the dominatrix` / `domme` / `mistress` / `dominant woman` /
`dominant lady` / `femdom` / `fetish model` — see §3.2.

There is **no trigger phrase** baked into the skin (compare 1xlasm's
`xlgts woman` / `xlasm man`). `require_trigger_presence` is `false`.
The per-dataset trigger word for each specific woman lives at SceneSet
level — one SceneSet per avatar / LoRA, with the trigger word written
into the SceneSet name and woven into the caption by the curator's
local convention.

Practical consequence: until a LoRA is wired, **every caption opens with
`The woman ...`**. When a SceneSet trigger word is added, the curator
swaps the opener to `The <trigger> ...` per their local recipe.

### 2.2 No second entity, no interaction taxonomy

Compared to 1xlasm — which is fundamentally **about how a giantess and
a small adult man interact**, with 4 levels of intimacy taxonomy — this
skin is fundamentally **about a woman's face**. There is no interaction
to capture, no proximity / touch / insertion / act distinction, no
attribute opt-in via `body_type_words`, no second figure to attribute
poses to. The whole machinery simplifies.

What remains is enumerating **the variable state of one face**:
expression, gaze, mouth state, eye state, framing, lighting, hair style,
accessory, makeup. Nine label groups, all under `primary.*`.

### 2.3 Wardrobe is STATE — until a curator says otherwise

A dominatrix dataset will typically include the same handful of masks /
collars / harnesses recurring across shots, plus some shots with no
fetish wardrobe. **The default treatment is: wardrobe is variable** —
the captioner DESCRIBES `mask`, `collar`, `harness`, `gag` whenever
they appear.

**Per-dataset curator override.** If a specific woman ALWAYS wears the
same item (e.g. always wears the same rubber mask, always has the same
collar on), that item is identity for that LoRA. The curator turns off
the relevant label at the SceneSet level so the captioner stops
describing it. The LoRA then learns "trigger comes with that mask."

Same logic applies to hair length / bangs and any other normally-variable
feature that happens to be invariant for a particular subject.

---

## 3. Three load-bearing constraints

All three are enforced both in `entities.primary.forbidden` (hard ban,
caught post-hoc by the `caption_violations()` validator) and in
`entities.primary.rules` (compose-time guidance, baked into the
JSON-derived directive). Both layers matter — the rule shapes what the
captioner writes; the forbidden list catches what slips through.

### 3.1 ADULT-ONLY (safety floor)

The subject is **ALWAYS** an adult woman. Period. No exceptions.

**Banned descriptors** (hard-ban list — partial sample; see JSON `forbidden`
for the full ~37-entry set): `girl`, `young woman`, `young lady`,
`young girl`, `little girl`, `teen`, `teenage`, `teenaged`, `teenager`,
`teens`, `teen girl`, `teenage girl`, `schoolgirl`, `school girl`,
`schoolboy`, `child`, `children`, `kid`, `kids`, `youth`, `minor`,
`underage`, `under age`, `under-age`, `pre-teen`, `preteen`, `tween`,
`juvenile`, `adolescent`, `adolescence`, `pubescent`, `prepubescent`,
`young-looking`, `young looking`, `very young`, `barely legal`,
`legal age`, `baby face`, `babyface`, `infant`, `toddler`, `youthful`,
`youthful glow`.

**The override rule.** If JoyCaption's vision drifts younger than adult,
override it. Render as `woman`. The captioner's visual judgment is NOT
authoritative here — the dataset's labeling and the curator's selection
are. This rule exists to prevent any caption from ever describing a
minor regardless of model behavior.

**Why both `youthful` and `mature woman` are banned**: identity-suppression
(§3.3) bans age descriptors in BOTH directions. `youthful` reads as
under-18-adjacent; `mature woman` / `middle-aged` / `older woman` /
`elderly` are identity claims about a specific woman's age. Either way,
age is identity, not state.

### 3.2 PERSONA WORD BAN

The persona is **constant across the dataset** — every shot in an avatar
dataset for a dominatrix is, by curator intent, of a dominatrix. Naming
the role in captions attaches the role to the variable signal and breaks
LoRA decoupling: the LoRA learns "dominatrix-ness" as a recombineable
attribute instead of as part of the identity trigger.

**Banned persona words**: `dominatrix`, `domme`, `mistress`,
`dominant woman`, `dominant lady`, `femdom`, `fetish model`.

**What to write instead**: describe what is VISIBLE in this particular
shot.

> ❌ "The dominatrix wears a leather mask and a studded collar."
>
> ❌ "She is a domme; her gaze is intense."
>
> ✅ "The woman wears a leather mask and a studded collar; her gaze is
>    intense and locked on the viewer."

**Why the bare adjective `dominant` is NOT banned**: it's the
`primary.expression.dominant` label's expansion vocabulary ("commanding
expression — brow raised, head tilted slightly up"). The expression
label refers to a transient affect that varies shot-to-shot; some shots
have a soft expression, some have a dominant one. That variation is
state, not identity, so the word is allowed in describing it. The hard
ban is on **role nouns** (`dominatrix`, `domme`, `mistress`, etc.) and
multi-word constructions that name the role (`dominant woman`,
`dominant lady`). The single-word adjective in a sentence about
expression survives the regex (`\bdominant\b` is not in the forbidden
list; `\bdominant woman\b` is).

**Adjacent caption-style note**: even when wardrobe is heavily fetish
(mask + collar + harness + gag), describe each item literally. Don't
editorialize ("looking authoritative", "the dominant figure",
"commanding presence"). Editorial framing leaks the role into the caption
even without using the banned word.

### 3.3 IDENTITY SUPPRESSION (the avatar-LoRA correctness rule)

Identity features are constant across the dataset by definition — that's
what makes them identity. Anything the captioner describes gets
disentangled from the trigger. Therefore: **never describe identity
features.**

**Banned identity vocabulary**, by category:

| category | examples (partial; see JSON `forbidden` for full list) |
|---|---|
| hair color | `blonde`, `brunette`, `redhead`, `ginger`, `black hair`, `brown hair`, `blond hair`, `blonde hair`, `red hair`, `grey hair`, `gray hair`, `white hair`, `auburn`, `dyed hair`, `bleached`, `platinum` |
| eye color | `blue eyes`, `green eyes`, `brown eyes`, `hazel eyes`, `grey eyes`, `gray eyes`, `dark eyes`, `light eyes` |
| skin tone | `pale skin`, `fair skin`, `tanned`, `tan skin`, `olive skin`, `dark skin`, `light skin`, `ebony skin` |
| skin marks | `freckles`, `freckled`, `mole`, `moles`, `birthmark`, `scar` |
| face geometry | `high cheekbones`, `sharp jawline`, `soft jawline`, `square jaw`, `full lips`, `thin lips`, `plump lips`, `aquiline nose`, `button nose`, `round face`, `oval face`, `heart-shaped face`, `angular face` |
| age (both ways) | see §3.1; both `young*` AND `mature*` / `middle-aged` / `elderly` |
| ethnicity / nationality | `asian`, `caucasian`, `european`, `african`, `latina`, `hispanic`, `mediterranean`, `nordic`, `slavic` |

**The describe-vs-omit decision tree.** When composing a per-image
caption_prompt and looking at the image (or processing JoyCaption's
response), ask:

1. **Could this feature change across the dataset?** (e.g. different
   shoots, different days, different lighting moods.)
   - **No** → identity → DO NOT describe. Drop the JoyCaption phrasing.
   - **Yes** → state → describe per the label taxonomy.

2. **Edge cases — hair length and bangs.** Length is *technically* state
   (hair grows, can be cut), but for a specific woman it tends to be
   stable across a single shoot or a season's worth of shoots. Default:
   describe length and bangs via the labels (`short`, `long`, `bangs`).
   If a curator notices their specific dataset has invariant length /
   bangs across all shots, they can turn the labels off at the SceneSet
   level (see §2.3).

3. **Edge case — skin texture / glow.** `youthful glow` is banned (age
   leak). Generic "glowing skin" or "skin is smooth" is identity-adjacent
   and should be dropped. Skip skin descriptors entirely; they live in
   the no-go zone.

4. **Edge case — body / shoulders / collarbone in three-quarter framing.**
   In `framing.head_and_shoulders` or `framing.three_quarter`, partial
   body is visible. Describe wardrobe (the collar / harness / clothing
   visible there). Do NOT describe body shape, breast size, body
   contour. The skin has no body-type opt-in (no `body_type_words`); all
   body-shape descriptors are off-limits by default. Body shape is also
   identity-adjacent (consistent across the dataset).

**Why this is asymmetric with 1xlasm.** 1xlasm's body-type adjectives
(`busty`, `muscular`, `curvy`) are gated by per-image opt-in labels —
the curator authorizes describing the woman's body shape on a per-image
basis. This skin has no such mechanism because **there is no per-image
authorization to give**: the body shape doesn't vary across an
avatar-LoRA dataset. The same woman appears in every shot. Per-image
opt-in would be incoherent.

---

## 4. Captioning style

### 4.1 Opener pattern

Every caption opens with a **single complete sentence introducing the
subject**:

> The woman <state-clause>.

The state-clause is one of:

- the dominant expression (`The woman wears a stern expression ...`)
- the framing (`The woman is shown in close-up, ...`)
- the gaze (`The woman looks directly at the camera, ...`)

Choose whichever is the most visually load-bearing fact for this
particular shot. Generally: if `framing` is dramatic (extreme close-up,
off-center), lead with that. If `gaze` is engaged (looking at camera,
direct eye contact), lead with that. Otherwise, lead with the dominant
expression.

**Never** open with:
- A noun-phrase fragment.
- A description of the medium (`A close-up portrait of ...` is acceptable
  if it carries information; `A professional photograph of ...` is
  forbidden — meta-photography filler, see §3 of `entities.primary.rules`).
- Identity vocabulary (`A blonde woman ...` — banned by §3.3).
- Persona vocabulary (`A dominatrix ...` — banned by §3.2).
- Age vocabulary (`A young woman ...` / `A mature woman ...` — banned
  by §3.1 / §3.3).

When a SceneSet trigger word is added later (one per LoRA), the opener
becomes `The <trigger> <state-clause>`. Until then, plain `The woman`.

### 4.2 State first, ambient second

After the opener, describe the variable state in this rough priority:

1. Expression (1 label)
2. Gaze + eye state (1-2 labels)
3. Mouth state (1 label)
4. Framing if not already in opener (1 label)
5. Lighting (1-2 labels)
6. Hair style (1-2 labels)
7. Accessory (0-N labels)
8. Makeup (1 label)

This roughly matches reading-order priority for a face shot: emotion
first, where she's looking second, mouth state third, then composition,
then surface qualities.

**Fuse compatible labels into single fluent sentences** rather than
emitting each as a standalone clause. Bad:

> The woman has a stern expression. The woman looks directly at the
> camera. The woman's mouth is closed. The woman's eyes are fully open.

Good:

> The woman wears a stern expression, mouth closed and eyes fully open,
> looking directly at the camera.

Same principle as 1xlasm §4.4 (pose combination): the compose model is
fluent prose, not bulleted assertions. (See the project-wide preference
in memory: **`feedback_caption_prompt_fluent_qwen`**.)

### 4.3 Hint policy

Hints for face shots are typically about **fine-grained state** that
doesn't fit cleanly into the 9 label groups:

- micro-expressions ("left eye twitched closed", "small genuine
  half-smile that the curator wants preserved")
- specific gaze targets ("looking past the camera at something to the
  left")
- the specific identity of a recurring accessory ("the rubber mask, not
  the leather one")
- a subtle lighting detail ("the highlight on the cheekbone is
  unusually sharp" — but careful, "cheekbone" is in the forbidden list
  as face geometry; the hint may need rephrasing)
- the woman's specific in-shot action that the labels don't have a slot
  for ("she is mid-blink", "she just exhaled smoke")

**Treat the hint the same way as for 1xlasm** (per the project-wide
hint-handling memory):
- Hint is the source of contextual truth for whatever specific state
  it captures.
- Hint verbs and body-part references are preserved verbatim.
- Hint absence (`'none'` sentinel, case-insensitive) means no extra
  detail beyond the labels — drop the user-hint preamble.
- **Hint overrides label rendering** when they conflict — see memory
  entry `feedback_caption_hint_vs_label_render`.

**One face-specific twist.** Some hints will SAY identity features
(e.g. "her eyes flash blue under the rim light"). The IDENTITY
SUPPRESSION rule takes priority: rewrite the hint at compile time to
drop the identity vocabulary while keeping the state observation
("her eyes catch the rim light"). The hint is curator intent, but the
load-bearing safety/correctness rule is identity suppression — never
let the hint smuggle in a forbidden identity claim.

### 4.4 No trigger labels (yet)

1xlasm has a class of **trigger labels** (`blowjob`, `handjob`, `sex`,
etc.) whose expansion contains a LoRA-anchor word that MUST appear in
the caption verbatim. This skin has **none** — no LoRA is wired yet
(`lora: null`), so no labels carry training-signal words to defend.

All 1xlface labels are currently **descriptive**: their expansion
strings are scaffolding for prose generation, freely paraphraseable,
freely dropped when the hint covers the same ground. The §4.1 hint-spine
discipline from 1xlasm — "hint covers it, drop the expansion" — applies
without exception here.

If / when an avatar LoRA is trained with specific concept anchors (e.g.
a label `expression.stern` becomes the anchor word `stern` in caption
training), this section gets updated and that label graduates to
trigger status. Until then: no anchors.

---

## 5. Anti-patterns (with the reasoning)

The following are the failure modes most likely from JoyCaption on
closeup face shots. Each has a *why* — understanding the principle
helps catch novel variants at prompt-compile time.

### 5.1 Spontaneous identity vocabulary

> ❌ "The blonde woman wears a stern expression, her blue eyes locked
>    on the camera."
>
> ✅ "The woman wears a stern expression, her eyes locked on the camera."

**Principle**: JoyCaption is trained to describe what it sees. Hair
color and eye color are highly salient in face shots, so it WILL emit
them unprompted. The forbidden-vocab validator catches the explicit
words, but it doesn't catch all the variants — e.g. *"her hair is the
color of straw"* (descriptive periphrasis avoiding the word `blonde`)
slips through.

**Mitigation at compile time**: in the per-image prompt, write the
explicit guard *"DO NOT describe the woman's hair color, eye color,
skin tone, face shape, or any identity feature, even via descriptive
periphrasis — describe only the variable state listed in the labels."*

**Mitigation at Stage 3**: forbidden-vocab regex catches the literal
words. The periphrasis cases can only be caught by review — flag and
report rather than auto-fix.

### 5.2 The persona slip ("dominatrix" / "fetish model")

> ❌ "The dominatrix wears a leather mask and a studded collar."
>
> ❌ "She poses as a fetish model in a leather harness."
>
> ✅ "The woman wears a leather mask and a studded collar."

**Principle**: JoyCaption recognizes fetish wardrobe and produces the
genre-typical role-noun. Same problem as identity vocabulary — the
caption then attaches the role to the variable signal.

The hard-ban list catches `dominatrix` / `domme` / `mistress` /
`dominant woman` / `dominant lady` / `femdom` / `fetish model` literally.
Variants like *"She has the look of a domme"* are caught (`domme` is
present); *"She has the look of someone in charge"* is editorial
periphrasis that slips the list.

**Mitigation**: in the per-image prompt for any shot with fetish
wardrobe present, add the inline guard *"DO NOT name the woman's role
or persona, even in editorial periphrasis — describe wardrobe items
literally (leather mask, studded collar, strap harness, ball gag) and
expression / gaze literally; do not editorialize about authority,
command, or fetish-genre framing."*

### 5.3 The age slip (in either direction)

> ❌ "The young woman has a soft expression."
>
> ❌ "The mature woman looks contemplative."
>
> ❌ "Her face has a youthful glow."
>
> ✅ "The woman has a soft expression." / "The woman looks contemplative."

**Principle**: JoyCaption emits age vocabulary as a baseline descriptive
move. Banned in BOTH directions per §3.1 / §3.3. Override at compile
time and rely on the forbidden-vocab validator as backstop.

`youthful glow` is the most common slip and is in the hard-ban list.

### 5.4 Meta-photography filler

> ❌ "A professional photograph of the woman, highly detailed and
>    breathtaking."
>
> ❌ "The portrait is a masterpiece of high quality."
>
> ✅ "The woman wears a stern expression in soft, diffuse light."

**Principle**: JoyCaption's training data includes Instagram-style
captions and stock-photo metadata, both of which heavily editorialize
about the medium ("masterpiece", "professional", "stunning",
"breathtaking"). For LoRA training these words are noise — they describe
the source corpus's editorial bias, not the depicted scene.

Banned: `professional photograph`, `professional photography`,
`highly detailed`, `high quality`, `masterpiece`, `stunning portrait`,
`breathtaking`, `flawless`.

### 5.5 Editorial framing of the wardrobe

> ❌ "She looks authoritative in her studded collar."
>
> ❌ "Her commanding presence is enhanced by the leather mask."
>
> ✅ "The woman wears a studded collar; her gaze is intense."

**Principle**: even when the banned word `dominatrix` is avoided,
editorial framing of fetish wardrobe leaks the persona into the
caption. The fix is literal description: "she wears X", "Y is visible",
"Z covers the nose and mouth". Let the wardrobe items speak for themselves
without authorial commentary.

### 5.6 The "is positioned" / "is visible" filler verbs

> ❌ "Her lips are positioned slightly parted."
>
> ❌ "Earrings are visible at her earlobes."
>
> ✅ "Her lips are slightly parted." / "Earrings hang at her earlobes."

**Same principle as 1xlasm §5.6**: `is positioned`, `is visible`,
`is centered`, `is shown` are filler verbs that don't carry information.
Pick a specific verb that describes the state, or omit the clause
entirely. "Is visible" in particular adds nothing — if a feature is
described, the reader already knows it's visible.

### 5.7 Repeating `the woman` in every sentence

> ❌ "The woman wears a stern expression. The woman looks at the camera.
>    The woman has dark eyeshadow."
>
> ✅ "The woman wears a stern expression, looking at the camera, eyes
>    framed by dark smoky eyeshadow."

**Principle**: same as 1xlasm §5.3 (repeated `naked`) — first mention
establishes the subject; subsequent mentions use `her` / `she` / drop
the subject in compound sentences. Caption length should be tight,
not inflated by subject repetition.

This rule is explicitly stated in `entities.primary.rules[0]`. It
matters more for this skin than for 1xlasm because the single-entity
setup has no second figure to alternate with — without discipline,
every sentence gets `the woman` as its subject.

---

## 6. Captioner quirks (Joycaption with no LoRA, baseline)

**Important**: this skin runs JoyCaption with `lora: null` — no
captioning LoRA wired yet. All observations below are about JoyCaption's
**base behavior** on closeup face shots. They will need re-validation if
a captioning LoRA gets wired in later (the LoRA shifts the distribution).

**Initial state (no validation runs yet)**: this section is mostly a
priori expectations based on 1xlasm-side observations and general
JoyCaption habits. Update with dated observations as `/validate_captions`
runs accumulate.

A priori expectations to watch for:

- **Identity vocabulary leakage** — JoyCaption WILL emit `blonde` /
  `blue eyes` / `pale skin` etc. unprompted on every face shot. The
  forbidden-vocab validator catches the canonical words; expect ~10-30%
  of unconstrained captions to leak them. The inline §5.1 guard plus the
  validator backstop is the mitigation.

- **Persona slippage** — on shots with strong fetish wardrobe (mask +
  collar + harness), JoyCaption may produce `dominatrix` / `mistress` /
  `fetish model` in the caption. Frequency unknown until first
  validation run. The inline §5.2 guard plus the validator backstop is
  the mitigation.

- **Age slippage** — JoyCaption is sensitive to soft / dewy makeup and
  may produce `young woman` / `youthful` for shots with natural
  makeup. The forbidden-vocab validator catches the literal forms.

- **Meta-photography filler** — JoyCaption frequently editorializes
  about photographic quality. The forbidden list catches the literal
  forms (`professional photograph`, `highly detailed`, etc.); rarer
  variants will need to be added as observed.

- **Over-describes setting / background** — face shots often have a
  background of some kind (studio, environment, etc.). JoyCaption may
  add a sentence on it. Acceptable in moderation (one short clause
  max); cut aggressively when it inflates length without informing
  the LoRA.

- **Fused-label compliance** — JoyCaption is reliably good at producing
  fused fluent sentences when the per-image prompt models them. When
  the prompt stacks label expansions as separate clauses, JoyCaption
  faithfully emits them as separate sentences (same pattern as 1xlasm
  §4.5 length-inflation observation). The §4.2 fusion discipline is the
  mitigation.

Things JoyCaption is generally good at (transferable from 1xlasm
observations):
- Following explicit prompt directives.
- Producing structurally sound, grammatical English.
- Respecting hints (~87% verbatim word overlap, per 1xlasm validation).

---

## 7. When to put MD context into the per-image caption_prompt

The MD doesn't reach the captioner directly. Only the directive (from
the JSON) + the per-image `caption_prompt` (composed at /img_caption
Stage 1) do. So the practical workflow is:

1. Read this MD at Stage 1 to recognize the constraints — the three
   load-bearing rules, the variable-state-only discipline.
2. Identify which anti-patterns are likely for this specific image:
   - Strong fetish wardrobe visible → §5.2 (persona slip) inline guard.
   - Soft / dewy makeup → §5.3 (age slip) inline guard, especially the
     `youthful glow` variant.
   - Hair / eyes prominent in the framing → §5.1 (identity vocabulary)
     inline guard, including a periphrasis warning.
   - Three-quarter or head-and-shoulders framing → §3.3 edge-case
     reminder: no body / breast / shoulder shape descriptors.
3. Identify which compose decisions matter:
   - Which fact leads the opener (§4.1)?
   - Which labels fuse into the opening sentence (§4.2)?
   - Does the hint cover any label such that the label expansion gets
     dropped (§4.3)?
4. Write a tight per-image prompt that includes the relevant inline
   guards, the applied label expansions, the hint verbatim (if
   present), and the opener instruction.

Target length per the project-wide convention: ~400-1000 chars (same
as 1xlasm).

The MD is for *me*; the per-image prompt is what *I write down* after
reading the MD, distilled to what matters for this one image.

---

## 8. Maintenance

This document is the **iterative theme record**. As we curate captions
and observe new failure modes, the corrections go here (as anti-patterns
with reasoning) before they go into the JSON. Once an MD principle is
mature enough to mechanize (a hard forbidden phrase), it can be lifted
into the JSON's `forbidden` list; otherwise it lives here as guidance.

**Do not** add to the JSON's `rules` arrays without first asking whether
the new entry is genuinely mechanical (catchable by a post-hoc validator)
or actually intuition (in which case it belongs here). The JSON should
drift toward a stable structural surface over time.

Updates to this document should be **dated** and **brief**. New
anti-patterns under §5; new captioner quirks under §6. The JSON's
`migration` log captures schema-shape evolution; this MD captures
theme-shape evolution.

**Particular maintenance trigger for this skin**: when the first real
avatar dataset is processed end-to-end (first `/img_caption` and
`/img_suggest` runs hit it), §6 and the suggestion-side MD should both
get dated observations. The a priori expectations above are placeholders
until then.
