# 1xlface — suggestion-process briefing

> **Companion document to `1xlface.md`. Distinct role.**
>
> `1xlface.md` (`skin.theme_md`) describes how to *write a final caption*
> from labels + hints — read by `/img_caption` Stage 1 and
> `/imgs_update_caption_prompt`.
>
> **This file** (`1xlface_suggestions.md`, `skin.theme_md_suggestions`)
> describes how to *derive labels + hints from a blank image* by
> iteratively probing JoyCaption — read by `/img_suggest` and
> `/imgs_validate_suggestions`. It accumulates suggestion-process knowledge
> separately from the captioning compile rules.
>
> Neither file is sent to the captioner; both are inputs to Claude's
> per-image judgment at the relevant stage.

---

## 1. Purpose & JSON/MD split fit

The captioning workflow (`/img_caption`) assumes `labels_ng` and `hints`
already exist on the SceneImage. For a fresh imported face image both
are blank. Manually filling them is slow — the curator must walk all 9
label groups (expression, gaze, mouth_state, eye_state, framing,
lighting, hair, accessory, makeup) and author the hint in the curator's
terse style.

**The suggestion step automates a first pass.** Claude composes probing
queries, sends each to the captioner (via `joy_client`), parses the
response into label-candidates and hint-material, refines the next
probe, and converges within 5 iterations. Output goes to
`labels_ng_SUGGESTION` and `hints_SUGGESTION` on the SceneImage. The
curator reviews and promotes to canonical fields.

This MD is the *briefing for the suggestion procedure* for face shots.
It grows as we observe what works and what doesn't via
`/imgs_validate_suggestions`.

**One major difference from 1xlasm-side suggestion**: there is no
trigger phrase to abort on. 1xlasm's iter-1 includes a
`status=not-1xlasm-shape` abort when JoyCaption fails to use
`xlgts woman` and `xlasm man`. This skin has no trigger to anchor that
check. The analogous abort condition here is **`status=not-1xlface-shape`**
when iter-1 reveals the image is NOT a closeup face shot of an adult
woman (e.g. multiple subjects, full-body shot, no person at all,
visibly underage subject). See §3.1 / §4.0 below.

---

## 2. The iteration loop

**Max 5 iterations.** Converge early when the latest probe yields no
new labels and no new hint material. Hard cap at 5 to prevent runaway
on ambiguous images.

**System content** for every probe is `skin.directive` (verbatim). The
directive includes the ADULT-ONLY + PERSONA WORD BAN + IDENTITY
SUPPRESSION rules; the captioner's responses to probes will be
influenced (though not strictly bound) by these directives.

**State held in-process** across iterations:

- `labels_candidate: set[path]` — accumulating label paths
- `labels_dropped: set[path]` — labels probed and ruled out
- `hint_fragments: list[str]` — verbatim-quality observations
- `identity_flags: list[str]` — identity vocabulary spotted in responses
  (for the suggestion-side filter; never used as label evidence)
- `persona_flags: list[str]` — persona vocabulary spotted in responses
  (same — never label evidence)
- `last_iter_added: bool` — convergence check

**Convergence rule (initial; refine via validation findings)**:

```
converged = (iter >= 2) AND (last_iter_added == False) AND (iter_count_since_addition >= 1)
```

Minimum 2 iterations because the first probe is intentionally broad and
almost always adds *something*; convergence-at-1 would skip the
disambiguation probes.

**Iter-5 hint-LoRA note**: 1xlasm-side iter-5 routes through a
hint-specific LoRA (`skin.lora_hint_path`) for terse curator-style hint
extraction. This skin has `lora_hint_path: null` — iter-5 falls back to
the default adapter with degraded hint quality. Document this as a known
limitation; revisit if a face-shot hint LoRA becomes practical.

---

## 3. Probing-query templates by iteration depth

Templates below are **starting points** for the typical sequence. The
probe at each iteration should target the *most uncertain* remaining
aspect — sequence may vary based on what iter 1 returns.

**Initial version (v1)** — narrative probes, no multi-choice (per the
1xlasm-side §3 finding that multi-choice degrades JoyCaption's
classification accuracy — captioning models are trained on narrative,
not classification).

### 3.1 Iteration 1 — broad scene id + adult-only / single-subject check

```
Describe this image in detail. Specifically: (1) Is the subject a
single adult woman shown in a closeup face shot? Answer yes or no, and
if no, what is actually in the frame (multiple people, a full-body
shot, no person, a child, etc.)? (2) What is her dominant facial
expression — what emotion or affect does her face read as? (3) Where
is she looking — at the camera, off to one side, up, down, eyes
closed? (4) What is the framing — extreme close-up (face fills the
frame), close-up, headshot (head and top of neck), head and shoulders,
or three-quarter (head to mid-torso)? Describe the dominant features
of state you can see — not her identity, not her age, not her hair
color or eye color or skin tone.
```

Parse the response for:

- **Subject sanity check** (load-bearing): if the response indicates
  the image is NOT a single adult woman in a face shot, abort with
  `status=not-1xlface-shape` and the diagnostic reason. Do NOT persist
  any suggestions in that case — the curator needs to remove the image
  from the SceneSet manually.

  Triggers for abort:
  - Multiple subjects mentioned
  - Full-body shot (no face dominance)
  - No person in frame
  - Any indication of an underage subject (`girl`, `teen`, `child`,
    `young`, `youthful`, etc. used in the description — even if
    JoyCaption's vision is wrong, this image needs curator review
    before being trained on)

- **Initial label candidates** per §5 mapping rules.
- **Identity flags**: any hair-color / eye-color / skin-tone /
  face-geometry vocabulary spotted. Log to `identity_flags` for the
  report; NEVER use as label evidence; NEVER pass to subsequent probes.
- **Persona flags**: `dominatrix`, `domme`, `mistress`, etc. spotted.
  Same — log only.

### 3.2 Iteration 2 — expression + mouth state (the affective pair)

```
Focus on the woman's face. (1) Describe her expression in detail —
what specific emotion or affect does her face convey? Use words like
neutral, smiling (open or closed mouth), laughing, smirking, pouting,
surprised, frowning, sad, angry, focused, sultry, dreamy,
contemplative, serene, dominant / commanding, stern, disdainful,
mocking, cold, or intense / locked gaze. Pick the single best fit.
(2) Describe her mouth state separately from the expression — is her
mouth closed, slightly parted (lips relaxed with a small gap), open
(teeth or interior visible), tongue extended past her lips, or biting
her lower lip? Be precise and use the specific phrasing above.
```

Parse for `primary.expression.*` (1 label, dominant) and
`primary.mouth_state.*` (1 label).

Note: the expression vocabulary listed in the probe matches the label
names verbatim — this maximizes the chance JoyCaption echoes a
recognizable word back. For dominatrix-typical shots the
`dominant` / `stern` / `disdainful` / `mocking` / `cold` /
`intense_gaze` cluster is heavily used; the probe explicitly enumerates
them so JoyCaption is primed to consider those options (without
falling into multi-choice degradation — the probe is still narrative
"pick the best fit", not "answer A/B/C").

### 3.3 Iteration 3 — gaze + eye state

```
Focus on her eyes. (1) Where is her gaze directed — directly at the
camera, off-camera to her left (viewer's right), off-camera to her
right (viewer's left), upward, downward, or are both eyes fully
closed? Pick the single best fit. (2) Separately, describe her eye
openness — fully open, half-closed (lids lowered partway over the
iris), fully closed, or squinting (eyes narrowed)? If her eyes are
fully closed, skip the eye-openness question — eyes_closed for gaze
already covers it.
```

Parse for `primary.gaze.*` (1 label) and `primary.eye_state.*` (0-1
labels, skip if `gaze.eyes_closed`).

### 3.4 Iteration 4 — lighting + hair style

```
Describe the lighting and the woman's hair. (1) Lighting: is it soft
and diffuse (low contrast, minimal hard shadows), hard and directional
(crisp shadow edges), backlit (main light behind her), rim-lit
(narrow bright edge tracing her silhouette), low-key (predominantly
dark frame with selective highlights), high-key (predominantly bright
frame), golden-hour (warm orange-gold), blue-hour (cool blue
ambient), studio with a clean white background, or has dramatic
shadow falling across part of her face? Multiple labels may apply
(backlit and rim_light often co-occur); name all that fit.
(2) Hair STYLE only — do NOT describe hair color or length-related
identity. Is her hair worn up (gathered off the neck), down (loose
around the face), tied back, wet, wind-blown, partly covering her
face, braided, slicked back (tight against the scalp with product),
short (cropped above the shoulders), long (past the shoulders), or
with bangs (fringe across the forehead)? Pick the labels that apply.
```

Parse for `primary.lighting.*` (1-2 labels) and `primary.hair.*` (1-2
labels). **Strip any color descriptor from JoyCaption's hair response**
before label-mapping — color is identity, never a label.

### 3.5 Iteration 5 — accessory + makeup + hint material

```
Describe what is visible on and around her face, and her makeup,
literally and precisely. (1) What accessories are visible — glasses,
sunglasses, earrings, necklace, hat, face mask (covering nose / mouth),
headband, facial piercing, neck collar (leather, studded, posture
collar, choker — distinct from a fashion necklace; a deliberate
restraint or fetish accessory), strap harness across the upper chest
or neckline, or a mouth gag (ball gag, bit gag, ring gag, cleave gag)?
List all that are visible. (2) Makeup: pick the dominant style —
none, natural (light, subtle), bold lips (saturated lip color as focal
element), smoky eyes (dark blended eyeshadow), full glamour (defined
brows, lined eyes, contoured cheeks, lip color), glossy finish, matte
finish, or dramatic brows (heavily shaped as a focal feature). Pick
one. (3) If there is any specific micro-detail of state in this shot
that the label vocabulary above does not capture — for example a
specific gaze target ("looking past the camera at something to the
left"), a fleeting micro-expression, a particular item of wardrobe
beyond what's listed, a smoke / breath in the air, mid-blink, mid-
exhale — describe it in one short sentence.
```

Parse for `primary.accessory.*` (0-N labels) and `primary.makeup.*` (1
label). The third part is **hint material** — rewrite into curator
style per §4.2 below.

---

## 4. Joy biases observed during suggestion

Populated by `/imgs_validate_suggestions` findings. Each entry dated and
cites the validation-run metric that surfaced it.

Format for new entries:

```
- **<bias name>** (observed 2026-MM-DD, n=N imgs): <description>.
  Mitigation: <how the probe template or parsing rule was updated>.
```

**No validation runs yet.** A priori expectations follow (to be confirmed
or refuted on first run); each is flagged "expected" until measured.

### 4.0 Expected: identity vocabulary leakage in every iteration

JoyCaption is highly likely to emit `blonde` / `blue eyes` / `pale skin`
/ `high cheekbones` etc. in iter-1's broad description AND in any iter
where it describes the face. The skin's directive (delivered as
system_content) includes the IDENTITY SUPPRESSION rule; this somewhat
reduces but does not eliminate the leakage.

**Mitigation**: at parse time, **scan every response for identity
vocabulary** (the JSON's `entities.primary.forbidden` list provides the
canonical regex). Log spotted vocabulary to `identity_flags` for the
report but NEVER convert into a label and NEVER pass into the
`hint_fragments` list. The suggestion process must not propagate
identity claims into the SceneImage record — `labels_ng_SUGGESTION` and
`hints_SUGGESTION` must be identity-clean.

### 4.1 Expected: persona vocabulary in fetish-wardrobe shots

When iter-5 enumerates wardrobe and the shot has mask + collar + harness
visible, JoyCaption is likely to emit `dominatrix` / `domme` /
`mistress` / `fetish model` in its descriptive prose.

**Mitigation**: same as §4.0 — scan, log to `persona_flags`, NEVER
convert into a label and NEVER let it propagate into hints. The
wardrobe items themselves (mask / collar / harness / gag) ARE labelable
(via `primary.accessory.*`); the role-noun is NOT.

### 4.2 Curator-style hint extraction for face shots

Face-shot hints in this skin will be **terse state observations** that
the labels can't capture. Expected patterns (a priori):

- specific gaze target: *"looking past camera, slightly left"*
- micro-expression / blink: *"mid-blink"*, *"caught between expressions"*
- specific named wardrobe: *"black leather mask"*, *"the metal choker
  collar"* (NB: the *color* `black` here is wardrobe color, not hair /
  eye / skin color — wardrobe is state, so this is OK)
- breath / mid-action: *"mid-exhale"*, *"smoke from her mouth"*
- particular lighting detail: *"single hard light from upper left"*
- fleeting tongue / lip detail: *"tongue tip just visible at the corner"*

**Rewrite iter-5's third-part response** (the micro-detail sentence)
into curator style:

- One or two sentences max.
- Subject = `she` / `her` (not `the woman`).
- Specific verb or state.
- No setting / mood-narrative filler.
- No identity vocabulary.
- No persona vocabulary.

If iter-5's response doesn't naturally collapse to a short observation,
**drop the hint** rather than synthesize one. Empty hint is correct
when the labels already cover everything; fabricating a hint adds
noise.

### 4.3 Expected: `hairstyle` ambiguity around length and color

`primary.hair.short` / `primary.hair.long` are length labels that we
treat as state by default (see `1xlface.md` §3.3 edge case). JoyCaption
will routinely emit both hair color and hair length. The parser must:

- Strip color (identity) — never label evidence.
- Keep length as `short` / `long` label evidence.
- Keep style (up / down / tied / wet / wind-blown / covering_face /
  braided / bangs / slicked_back) as label evidence.

The probe is worded to ask for STYLE explicitly, but JoyCaption's
response will still mention color; the parser handles the filtering.

### 4.4 Expected: framing ambiguity (close-up vs headshot)

The six framing labels (`extreme_close_up`, `close_up`, `headshot`,
`head_and_shoulders`, `three_quarter`, `off_center`) have nearby
boundaries — `close_up` and `headshot` differ on whether the neck is
visible; `headshot` and `head_and_shoulders` differ on shoulder
visibility. JoyCaption may use these terms loosely.

**Mitigation**: parse iter-1's framing answer literally, but cross-check
against iter-5's accessory answer — if `necklace` or `collar` or
`harness` is mentioned, the framing must be at least `headshot` (neck
visible) or `head_and_shoulders` / `three_quarter`. Adjust upward when
the visibility evidence contradicts the framing label.

`off_center` is composition (not crop) and can co-occur with any of the
others if JoyCaption notes the subject is distinctly off the vertical
centerline. Allow it as a second framing label when explicitly
mentioned.

### 4.5 Expected: accessory under-call when the shot is busy

Iter-5 enumerates accessories explicitly, but if the shot has multiple
accessories visible JoyCaption may miss one (e.g. earrings half-hidden
behind hair, a small piercing). Expect lower recall on accessory than
on expression / gaze / framing.

**Mitigation deferred until measured** — if validation surfaces this as
a systematic miss, add a follow-up probe that targets accessories
specifically.

### 4.6 Expected: makeup over-call on natural lighting

`primary.makeup.natural` vs `primary.makeup.none` is a subtle
distinction — `none` means bare skin and bare lips; `natural` means
subtle product visible. JoyCaption may over-call `natural` for any
visibly groomed face. Default to `none` when JoyCaption's response is
ambiguous; only set `natural` when the response explicitly mentions
visible product (foundation, gloss, light eyeliner, etc.).

`glamour` and `dramatic_brows` and `bold_lips` are easier to
discriminate — they have specific visual markers JoyCaption can name.

*(Add more cases as `/imgs_validate_suggestions` surfaces them.)*

---

## 5. Mapping joy responses to skin labels

The tricky cases. JoyCaption emits prose; the suggestion step has to
map prose to `skin.labels` keys.

### 5.1 Identity vocabulary → DROP

Any occurrence of hair color, eye color, skin tone, face geometry,
ethnicity, freckles, moles, age descriptors (both `young*` and
`mature*`) in JoyCaption's response is **dropped at parse time**.
- Never converted into a label.
- Never propagated into `hint_fragments`.
- Logged to `identity_flags` for the report (so the curator knows the
  captioner is leaking and can choose to add periphrasis guards at
  Stage-3 caption time).

The complete forbidden list lives in `entities.primary.forbidden` —
compile it into a regex once per suggest run and apply to every probe
response.

### 5.2 Persona vocabulary → DROP

Same treatment as §5.1, for the persona word list: `dominatrix`,
`domme`, `mistress`, `dominant woman`, `dominant lady`, `femdom`,
`fetish model`.

Note: the bare adjective `dominant` (without `woman` / `lady`) IS
evidence for the `primary.expression.dominant` label — the
forbidden-vocab regex is on the multi-word phrases, not the single
word. The parser should:
- See `dominant woman` / `dominant lady` → drop (persona).
- See `dominant expression` / `dominant gaze` / `looking dominant` → set
  `primary.expression.dominant` label.

### 5.3 Adult-only check at iter-1

The most important load-bearing check. If iter-1's response uses ANY
of `girl`, `teen*`, `schoolgirl`, `child`, `kid`, `youth*`, `minor`,
`underage`, `pre-teen`, `tween`, `juvenile`, `adolescent`, `pubescent`,
`young-looking`, `young woman`, `young lady`, `young girl`, `little
girl`, `barely legal`, `baby face`, `youthful` → **abort with
status=not-1xlface-shape** and the diagnostic flag `subject_age_concern`.

Do NOT persist suggestions. The curator needs to manually inspect the
image — JoyCaption's age-perception is unreliable but if it reads as
underage, the image should not silently end up in an avatar dataset.

The check is one-way: JoyCaption saying "adult woman" is required.
JoyCaption saying any age word is the abort signal. If JoyCaption says
neither, default to continuing (the directive's ADULT-ONLY override
takes effect at caption time).

### 5.4 Expression vocabulary → expression label

Direct keyword matching:

| JoyCaption phrasing | label |
|---|---|
| neutral / relaxed / no expression | `expression.neutral` |
| closed-mouth smile / soft smile / gentle smile | `expression.smile_closed` |
| open-mouth smile / smiling with teeth / wide smile | `expression.smile_open` |
| laughing / mid-laugh / caught laughing | `expression.laugh` |
| smirk / asymmetric smile / one-sided smile | `expression.smirk` |
| pout / pouting / lips pushed forward | `expression.pout` |
| surprised / shocked / brows raised / eyes wide | `expression.surprised` |
| frowning / brows drawn / brows together | `expression.frowning` |
| sad / sorrowful / melancholy | `expression.sad` |
| angry / furious / hardened gaze / set jaw | `expression.angry` |
| focused / attentive / concentrated | `expression.focused` |
| sultry / seductive / sensual | `expression.sultry` |
| dreamy / faraway / distant gaze | `expression.dreamy` |
| contemplative / pensive / thoughtful / introspective | `expression.contemplative` |
| serene / calm / peaceful | `expression.serene` |
| dominant / commanding / authoritative (but NOT `dominant woman`) | `expression.dominant` |
| stern / hard / severe | `expression.stern` |
| disdainful / contemptuous / disapproving | `expression.disdainful` |
| mocking / derisive / cruel smile | `expression.mocking` |
| cold / icy / unfeeling / no warmth | `expression.cold` |
| intense gaze / locked stare / unbroken eye contact | `expression.intense_gaze` |

Pick **one** dominant expression. If two apply, prefer the more specific
(e.g. `stern` over `serious`; `intense_gaze` over `focused` when eye
engagement is the load-bearing feature).

### 5.5 `intense_gaze` vs `gaze.at_camera` overlap

`primary.expression.intense_gaze` is an **expression** label (it's about
affect — the intensity, the locked-on quality). `primary.gaze.at_camera`
is a **gaze direction** label (about where the eyes point).

These can co-occur: a sultry expression directed at the camera should
set BOTH `expression.sultry` AND `gaze.at_camera`. An intense locked
gaze at the camera should set BOTH `expression.intense_gaze` AND
`gaze.at_camera`.

When in doubt, the gaze label (direction) is mechanical and easy; the
expression label (affect) is the judgment call.

### 5.6 Accessory: `necklace` vs `collar`

This is the most important accessory discrimination for this skin.

- **`necklace`** is fashion jewelry — a chain or pendant resting at the
  collarbone, ornamental.
- **`collar`** is a deliberate neck restraint or fetish accessory —
  leather collar, studded collar, posture collar, choker (when worn as
  a fetish piece rather than a fashion choker). Distinct visual signal:
  width, hardware (rings, studs, buckles), tightness against the neck.

JoyCaption may use `choker` ambiguously. Heuristic:
- Thin metal chain / pendant → `necklace`.
- Thick leather strap / visible buckle / studs / rings → `collar`.
- "Choker" with no further detail → check iter-5's full description for
  hardware mentions; if none, default to `necklace` (fashion);
  conservative skip is OK.

Similarly: `harness` is a strap arrangement crossing the upper chest;
do NOT confuse with `necklace` (a single chain). Multiple straps
visible → `harness`.

### 5.7 Mouth state: `open` vs `tongue_out` vs `biting_lip`

`mouth_state.open` is the umbrella; `tongue_out` and `biting_lip`
are specializations. If tongue is extended past the lips → `tongue_out`
(do not also set `open`). If teeth are pressing into the lower lip →
`biting_lip` (do not also set `open` or `slightly_parted`).

`mouth_state.slightly_parted` is for relaxed lips with a small gap,
no teeth visible.

### 5.8 Lighting can have 1-2 labels

Most lighting labels are mutually exclusive (`high_key` vs `low_key`,
`golden_hour` vs `blue_hour`), but several pair naturally:

- `backlit` + `rim_light` (back-light producing a silhouette rim)
- `low_key` + `dramatic_shadow` (dark frame with hard shadow play)
- `studio_white` + `soft_diffuse` (clean white background with even
  light) or `studio_white` + `hard_directional` (clean background, hard
  beauty light)
- `golden_hour` + `soft_diffuse` (warm golden + diffuse from a low sun
  through atmosphere)

Allow up to 2 lighting labels when JoyCaption's response evidences
both. More than 2 is over-call — drop the less-specific one.

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

- High: the observation appeared verbatim in ≥2 iterations or once with
  no contradicting paraphrase.
- Medium: appeared once.
- Low: contradicted or only implied.

**Extra category for this skin**: identity / persona vocabulary flags
are **always reported** regardless of confidence (they're not labels;
they're informational warnings that the captioner is leaking — useful
for the curator to see when they review the suggestion and again at
caption time).

---

## 7. Validation harness

Run `/imgs_validate_suggestions count=N [set=<scene-set>]` to validate
the suggestion process against curator-authored labels+hints on done
images. See the active validation plan (when one is established for
this skin) for full methodology, metrics, and refinement-loop pattern.

**No validation runs yet for 1xlface.**

**Initial acceptance criteria** (set 2026-05-25; refinable):

- Labels F1 ≥ 0.70 over 30 done imgs
- Hint key-token overlap ≥ 0.60 mean (likely unattainable without a
  face-hint LoRA — same structural issue as 1xlasm's iter-5 hint
  ceiling)
- Iter-to-converge median ≤ 3
- Per-label-group recall ≥ 0.60 for all 9 groups
- Identity-leak rate ≤ 5% of suggestions (identity vocabulary in either
  `labels_ng_SUGGESTION` or `hints_SUGGESTION` after parsing)
- Persona-leak rate ≤ 5% (same)
- Adult-only check fires correctly on edge cases (test set should
  include a couple of borderline-young faces and verify abort)

**A priori expectation ceilings** (based on 1xlasm-side experience):

- Per-group recall above ~0.60 is achievable with narrative probing
  when the taxonomy is well-defined (this skin's taxonomy is simpler
  than 1xlasm's, so should be easier).
- `accessory` is likely to have lower recall (more easily missed in
  busy frames — see §4.5).
- `expression` has 21 leaves; subtle discriminations
  (`stern` vs `cold` vs `disdainful`) may have lower per-leaf recall
  even if group-level recall is high.
- Hint jaccard above ~0.10 without a face-hint LoRA is unlikely — same
  structural mismatch as 1xlasm.

These ceilings will be re-estimated after the first validation run.

---

## 8. Maintenance

Same iterative-knowledge accumulation pattern as `1xlface.md` §8.

Update §4 (joy biases) and §5 (mapping ambiguities) when
`/imgs_validate_suggestions` surfaces a systematic miss. Edit §3 (probe
templates) when a template change measurably improves a metric;
re-run validation to confirm.

Don't add to JSON `rules` or `forbidden` based on suggestion-process
observations — those govern caption *output*, not suggestion *input*.
The split is the same as for `1xlface.md`.

Dated observations are load-bearing — every claim about joy's behavior
should cite the validation run that produced the evidence. Format:
`(observed YYYY-MM-DD, N imgs, metric=value)`.

**Particular maintenance trigger for this skin**: replace each
"expected" / "a priori" claim in §4 with a dated, measured observation
as soon as the first validation run hits the relevant pattern. The
current §4 entries are scaffolding to guide the first runs; they should
mutate into evidence-backed claims (or be deleted) as data arrives.
