# xlasm — curator reference (full-content edition)

> One-page consolidation of everything we know about the `1xlasm` skin:
> identity, the entire label catalog with renderings, compose variants,
> forbidden vocabulary, concept matchers, hint and caption corpus samples,
> training/inference directives quoted verbatim, dataset snapshot, slash
> commands and accumulated rules. Companion to the canonical
> `conf/skins/1xlasm.json` (machine surface), `conf/skins/1xlasm.md`
> (theme briefing), `conf/skins/1xlasm_suggestions.md` (suggestion
> briefing) and `conf/skins/_schema.json` (JSON schema). This document
> embeds content, not just structure — when you need the *list*, *quote*,
> or *example*, look here. Synthesised, not load-bearing — cite the
> originals when mechanically applying any rule.

## Identity & purpose

`1xlasm` is the captioning recipe for the giantess theme: a dominant
`xlgts woman` (primary) paired with a smaller `xlasm man` (secondary).
Captions composed via this skin are training data for the Qwen-Image
LoRA family `gts3` (current production checkpoint: epoch 10 =
`xlasm10-test.safetensors`, alongside the base merge experiment
`fbbcool/qwen-2512-snofs-0.65`). The skin owns the per-image discipline
that lets those LoRAs learn the trigger phrases — every fact a curator
flags must appear in the final caption; vocabulary that conflicts with
the trigger semantics is banned.

`1xlasm` is also the first (and currently only) skin migrated to the
JSON/MD architecture under `conf/skins/`. The 15 remaining recipes
(`gts_prompter`, `1pussy_insert`, `1gts`, `1busty-gts`, `1legsemp`,
`1woman`, `1fem`, `1fbb`, `1hairy`, `1man`, `1calves`, `1leggy`,
`1busty`, `1face`, `1tongue`) still live as one-liner system/prompt
strings in `CONTENT_SYSTEM` / `CONTENT_PROMPT` dicts in
`src/ait/caption/joy.py` and run through the legacy `Joy` /
`JoySceneDB` classes (`memory/project_caption_skin_refactor.md`).

## Entity model & trigger phrases

Triggers are nonsense tokens anchored by the captioning LoRA — the
`xlgts` / `xlasm` strings carry the size relationship on their own, so
captions must never reach for size adjectives.

| role | token | phrase used in captions |
| --- | --- | --- |
| primary | `xlgts` | `xlgts woman` |
| secondary | `xlasm` | `xlasm man` |

Source: `src/ait/caption/joy.py` (`TRIGGER_WOMAN_TOKEN = 'xlgts'`,
`TRIGGER_MAN_TOKEN = 'xlasm'`, `TRIGGER_WOMAN = 'xlgts woman'`,
`TRIGGER_MAN = 'xlasm man'`); mirrored verbatim in
`conf/skins/1xlasm.json §entities.primary.phrase` /
`.secondary.phrase`.

Both phrases MUST appear at least once in every caption
(`require_trigger_presence: true` in the JSON, enforced by
`Skin.missing_triggers`). The strong-default style is to introduce both
in the first sentence, but the validator only checks presence — a
two-sentence opener is acceptable when one figure clearly dominates
(`conf/skins/1xlasm.md §4.2`).

**Body-type tokens.** The legacy `joy.py` plumbing carried a roadmap of
named body-type triggers (`xlbusty`, `xlcurvy`, etc.) intended to
become their own LoRA adapters. Today only `xlbusty` corresponds to a
trained adapter; the rest exist only as `primary.attribute.*` labels
controlling caption vocabulary. The fish `ait_caption` quickpick UI
exposes every `primary.attribute.*` label as a body-emphasis choice
for inference but applying any non-`busty` choice does not yet route
through a dedicated LoRA — the emphasis just feeds into the directive
as a surface label.

## Label catalog — full enumerated rendering

All labels are stored on `SceneImage.labels_ng` as structured paths
`<entity>.<group>.<leaf>`. The flat path → rendering map is
`Skin.labels` (built into `_built.labels` by
`python -m ait.caption.skin_build 1xlasm`). Total: **79 labels across
10 groups**.

Every row below pairs the canonical path with the rendered sentence
that joy receives when the label is set on an image. Renderings are
quoted verbatim from `conf/skins/1xlasm.json §_built.labels`.

### primary.attribute (7 labels — body type, woman-side, opt-in)

| path | rendering |
| --- | --- |
| `primary.attribute.muscular` | `The xlgts woman has a muscular bodybuilder physique with visible muscle definition.` |
| `primary.attribute.leggy` | `The xlgts woman has big calves.` |
| `primary.attribute.busty` | `The xlgts woman has prominently large breasts.` |
| `primary.attribute.slim` | `The xlgts woman has a slim athletic build.` |
| `primary.attribute.curvy` | `The xlgts woman has curvy hourglass proportions.` |
| `primary.attribute.bigass` | `The xlgts woman has a big round ass.` |
| `primary.attribute.hairy` | `The xlgts womans pubic area is hairy.` |

Body-type labels are positive-only and opt-in: a caption that names any
gated vocabulary (`busty`, `large breasts`, …) without the
authorizing label triggers `Skin.body_type_warnings`. The legacy
`joy.py` plumbing also reserved `xlbusty`, `xlmuscular`, `xlcurvy`,
`xlslim`, `xlhairy`, `xlbigass`, `xlleggy` tokens for future body-type
LoRAs; only the `xlbusty` adapter exists today.

### primary.pose (12 labels — woman posture / viewing angle)

| path | rendering |
| --- | --- |
| `primary.pose.front` | `The xlgts woman is seen from the front.` |
| `primary.pose.back` | `The xlgts woman is seen from the back.` |
| `primary.pose.side` | `The xlgts woman is seen from the side.` |
| `primary.pose.sitting` | `The xlgts woman is sitting.` |
| `primary.pose.on_back` | `The xlgts woman is on her back.` |
| `primary.pose.all4` | `The xlgts woman is on her all fours.` |
| `primary.pose.tower` | `The xlgts woman stands directly above the xlasm man, with him positioned at her feet or lower leg level.` |
| `primary.pose.standing` | `The xlgts woman is standing upright.` |
| `primary.pose.lying` | `The xlgts woman is lying.` |
| `primary.pose.kneeling` | `The xlgts woman is kneeling.` |
| `primary.pose.arms_spread` | `The xlgts woman has her arms spread wide apart.` |
| `primary.pose.legs_spread` | `The xlgts woman has her legs spread wide apart.` |

A 2026-05-12 migration corrected `on_back`'s pronoun from `his back` to
`her back` (primary is the woman). The original short names
(`woman_front`, `woman_back`, …) live untouched in
`SceneImage.labels`; `labels_ng` carries the prefixed forms.

### primary.action (6 labels — woman-driven verbs, trigger labels)

| path | rendering |
| --- | --- |
| `primary.action.step` | `The xlgts woman is stepping on the xlasm man with her foot.` |
| `primary.action.holding` | `The xlasm man is held by the xlgts woman.` |
| `primary.action.blowjob` | `The xlgts woman is giving the xlasm man a blowjob, with his erect penis inserted into her mouth and her lips closed on his penis. The blowjob is the central content of the image.` |
| `primary.action.handjob` | `The xlgts woman is giving the xlasm man a handjob, stimulating and stroking his penis with her hand. The handjob is the central content of the image.` |
| `primary.action.teasing_hj` | `The xlgts woman is giving the xlasm man a teasing handjob, stimulating and stroking his penis delicately with her fingers. The teasing handjob is the central content of the image.` |
| `primary.action.job` | `The xlgts woman is giving the xlasm man either a handjob or a blowjob.` |

All `primary.action.*` labels are **trigger labels** — their static
expansion always emits in the per-image prompt, even when the hint
covers the mechanics. The expansion contains the load-bearing
training-signal phrase (`blowjob`, `handjob`, `stepping`, `held by`).
The same trigger-label set also includes `secondary.action.masturbating`,
`secondary.action.cum`, and `interaction.act.sex` (`conf/skins/1xlasm.md §4.6`).

### secondary.attribute (1 label — man-side, bidirectional)

| path | rendering |
| --- | --- |
| `secondary.attribute.penis` | `The xlasm man has an erect penis.` |

This is the **only bidirectional label** in the skin: presence asserts
the penis is in the scene; absence asserts *no* penis is in the scene
and any caption mention is a violation
(`memory/feedback_label_semantics_positive_only.md`). The previous
sibling `penis_no` was removed 2026-05-13 (0 uses, redundant under the
bidirectional rule).

### secondary.pose (13 labels — man posture)

| path | rendering |
| --- | --- |
| `secondary.pose.front` | `The xlasm man is seen from the front.` |
| `secondary.pose.back` | `The xlasm man is seen from the back.` |
| `secondary.pose.side` | `The xlasm man is seen from the side.` |
| `secondary.pose.sitting` | `The xlasm man is sitting.` |
| `secondary.pose.on_back` | `The xlasm man is on his back.` |
| `secondary.pose.hanging` | `The xlasm man is in a hanging position.` |
| `secondary.pose.lifted` | `The xlasm man is lifted by the xlgts woman.` |
| `secondary.pose.perched` | `The xlasm man is in a sitting position, typically seated on a body part of the xlgts woman.` |
| `secondary.pose.standing` | `The xlasm man is standing upright.` |
| `secondary.pose.lying` | `The xlasm man is lying.` |
| `secondary.pose.kneeling` | `The xlasm man is kneeling.` |
| `secondary.pose.arms_spread` | `The xlasm man has his arms spread wide apart.` |
| `secondary.pose.legs_spread` | `The xlasm man has his legs spread wide apart.` |

Note the `sitting` vs `perched` split: a man seated *on a body part of
the woman* is `perched`; a simple seated pose is `sitting`. The
migration on 2026-05-10 renamed the legacy `sitting` (on-body-part) to
`perched` and freed `sitting` for the simple form. Also note that
`secondary.pose.*` is what the `interaction.proximity.*` compose rule
reads when picking its context-aware verb (see compose rules below).

### secondary.action (2 labels — man-driven verbs, trigger labels)

| path | rendering |
| --- | --- |
| `secondary.action.masturbating` | `The xlasm man is masturbating, gripping and stroking his erect penis. This masturbation is the central content of the image.` |
| `secondary.action.cum` | `The xlasm man ejaculates and cums.` |

Both are trigger labels and always render even when the hint covers
the mechanics.

### interaction.proximity (6 labels — held-near, compose-aware)

These are the only labels with **context-aware compose** rendering. The
group carries a `subject_verb_by_secondary_pose` compose rule: when
the image also has `secondary.pose.<leaf>`, the rendering switches
subject and verb to fit the pose. The static expansion is the fallback
used when no matching secondary.pose is on the image, or the image's
secondary.pose is not in the rule map.

| path | static expansion (default) | compose target |
| --- | --- | --- |
| `interaction.proximity.mouth` | `The xlgts woman holds the xlasm man close to her mouth.` | `her mouth` |
| `interaction.proximity.face` | `The xlgts woman holds the xlasm man close to her face.` | `her face` |
| `interaction.proximity.breasts` | `The xlgts woman holds the xlasm man close to her breasts.` | `her breasts` |
| `interaction.proximity.thighs` | `The xlgts woman holds the xlasm man close to her thighs.` | `her thighs` |
| `interaction.proximity.ass` | `The xlgts woman holds the xlasm man close to her ass.` | `her ass` |
| `interaction.proximity.vagina` | `The xlgts woman holds the xlasm man close to her vagina.` | `her vagina` |

**Compose rule table** (rule kind `subject_verb_by_secondary_pose`).
Templates are
`template_primary: 'The xlgts woman {verb} {target}.'` and
`template_secondary: 'The xlasm man {verb} {target}.'`. The rule
iterates the map below in declaration order; the first co-applied
`secondary.pose.<leaf>` wins. Falls back to `default`.

| secondary.pose.* | subject | verb | example for `proximity.mouth` |
| --- | --- | --- | --- |
| `hanging` | secondary | `hangs close to` | `The xlasm man hangs close to her mouth.` |
| `lying` | secondary | `lies close to` | `The xlasm man lies close to her mouth.` |
| `kneeling` | secondary | `kneels close to` | `The xlasm man kneels close to her mouth.` |
| `sitting` | secondary | `sits close to` | `The xlasm man sits close to her mouth.` |
| `perched` | secondary | `sits close to` | `The xlasm man sits close to her mouth.` |
| `standing` | secondary | `stands close to` | `The xlasm man stands close to her mouth.` |
| *(default — no match or no secondary.pose)* | primary | `holds the xlasm man close to` | `The xlgts woman holds the xlasm man close to her mouth.` |

Secondary poses not in the table (`front`, `back`, `side`, `on_back`,
`lifted`, `arms_spread`, `legs_spread`) fall through to the
primary-subject default — by design, since those don't constrain the
verb of approach.

**Known render-content discrepancy.** Older renderings carried a
`without contact or insertion` suffix that explicitly described what is
*not* happening; per `memory/feedback_label_semantics_positive_only.md`
those negative claims should not be in the skin's positive-only
renderings (the only bidirectional label is `secondary.attribute.penis`).
The current `_built.labels` no longer contain the suffix — confirmed
against the JSON dated 2026-05-13. Captions written before that date
may carry the suffix and are corrected by `/imgs_validate_captions`.

### interaction.touch (11 labels — contact, no penetration)

| path | rendering |
| --- | --- |
| `interaction.touch.ass` | `The xlasm man interacts with the xlgts womans ass.` |
| `interaction.touch.body` | `The xlasm man interacts with the xlgts womans body.` |
| `interaction.touch.breast` | `The xlasm man interacts with the xlgts womans breasts.` |
| `interaction.touch.face` | `The xlasm man interacts with the xlgts womans face.` |
| `interaction.touch.foot` | `The xlasm man interacts with the xlgts womans foot.` |
| `interaction.touch.hand` | `The xlasm man interacts with the xlgts womans hand.` |
| `interaction.touch.leg` | `The xlasm man interacts with the xlgts womans leg.` |
| `interaction.touch.mouth` | `The xlasm man interacts with the xlgts womans mouth.` |
| `interaction.touch.pussy` | `The xlasm man interacts with the xlgts womans vagina.` |
| `interaction.touch.thigh` | `The xlasm man is positioned between the thighs of the xlgts woman.` |
| `interaction.touch.tongue` | `The xlasm man interacts with the xlgts womans tongue.` |

Note the deliberate looseness: `interacts with` is a placeholder verb
designed to be replaced by the hint's specific verb when present
(`embraces`, `wraps`, `presses against`, `clings to`, …). The hint is
load-bearing here; the rendering exists primarily to register the body
part as a *required fact*. Special case: `touch.thigh` uses
`positioned between` instead of `interacts with` — that geometry is
the canonical thigh-touch archetype. `touch.pussy` renders the leaf
as `vagina` (not `pussy`) to stay clinical.

### interaction.insertion (16 labels — partial penetration)

| path | rendering |
| --- | --- |
| `interaction.insertion.insert` | `The xlasm man is partly inserted into one of the xlgts womans orifices: her vagina, her anus, or her mouth. When the insertion is vaginal, the inserted body part is his head, his upper body, or his lower body, and that part is concealed inside her body.` |
| `interaction.insertion.panties` | `The xlasm man is partly inserted into the waistband of the xlgts womans panties. His upper body is below the waistband; his lower body and head may be visible above it depending on orientation. Describe what is visible above and below the waistband.` |
| `interaction.insertion.breasts_body` | `The xlasm man is inserted into between the xlgts womans breasts with his body partly obscured by her breasts.` |
| `interaction.insertion.breasts_head` | `The xlasm man is partly inserted into between the xlgts womans breasts. his head is inserted, only the rest of his body is visible.` |
| `interaction.insertion.breasts_low` | `The xlasm man is partly inserted into between the xlgts womans breasts. his lower body is inserted, only his upper body is visible.` |
| `interaction.insertion.breasts_up` | `The xlasm man is partly inserted into between the xlgts womans breasts. his upper body is inserted, only his lower body is visible.` |
| `interaction.insertion.vagina_low` | `The xlasm man is partly inserted into the xlgts womans vagina. his lower body is inserted, only his upper body is visible.` |
| `interaction.insertion.vagina_up` | `The xlasm man is partly inserted into the xlgts womans vagina. his upper body is inserted, only his lower body is visible.` |
| `interaction.insertion.vagina_head` | `The xlasm man is partly inserted into the xlgts womans vagina. his head is inserted, only the rest of his body is visible.` |
| `interaction.insertion.ass_low` | `The xlasm man is partly inserted into the xlgts womans ass. his lower body is inserted, only his upper body is visible.` |
| `interaction.insertion.ass_up` | `The xlasm man is partly inserted into the xlgts womans ass. his upper body is inserted, only his lower body is visible.` |
| `interaction.insertion.ass_head` | `The xlasm man is partly inserted into the xlgts womans ass. his head is inserted, only the rest of his body is visible.` |
| `interaction.insertion.mouth_body` | `The xlasm man is inserted into the xlgts womans mouth with his body partly obscured by her mouth.` |
| `interaction.insertion.mouth_head` | `The xlasm man is partly inserted into the xlgts womans mouth. his head is inserted, only the rest of his body is visible.` |
| `interaction.insertion.mouth_low` | `The xlasm man is partly inserted into the xlgts womans mouth. his lower body is inserted, only his upper body is visible.` |
| `interaction.insertion.mouth_up` | `The xlasm man is partly inserted into the xlgts womans mouth. his upper body is inserted, only his lower body is visible.` |

The `<orifice>_<part>` grid (orifice ∈ {breasts, vagina, ass, mouth} ×
part ∈ {body, head, low, up}) is the canonical schema for directional
insertion. `breasts_body` and `mouth_body` use the `inserted` (no
"partly") phrasing — `body` means most of him is concealed.
`interaction.insertion.panties` was rewritten 2026-05-12 to make the
waistband geometry explicit; the curator rewrote all 3 prior
occurrences after the update.

### interaction.act (5 labels — gaze and combined acts)

| path | rendering |
| --- | --- |
| `interaction.act.she_look_at_him` | `She is looking at him.` |
| `interaction.act.she_look_at_penis` | `She is looking at his penis.` |
| `interaction.act.he_look_at_her` | `He is looking at her.` |
| `interaction.act.look_at_each` | `They are looking at each other.` |
| `interaction.act.sex` | `The xlasm man has sex with the xlgts woman, inserting his erect penis into her vagina.` |

Gaze labels (`she_look_at_him`, `he_look_at_her`, `look_at_each`,
`she_look_at_penis`) use he/she pronouns rather than the trigger
phrases because they always render in the middle of a paragraph where
the antecedent is already introduced — joy bridges the pronoun back to
the trigger noun via context. `interaction.act.sex` is a trigger label.

### Group summary

| group | entity | count | semantics | notable |
| --- | --- | --- | --- | --- |
| `primary.attribute` | woman | 7 | positive-only, opt-in | gates body-type vocab |
| `primary.pose` | woman | 12 | positive-only | tower is compositional, not size |
| `primary.action` | woman | 6 | trigger labels | always render |
| `secondary.attribute` | man | 1 | **bidirectional** | `penis` only |
| `secondary.pose` | man | 13 | positive-only | feeds proximity compose |
| `secondary.action` | man | 2 | trigger labels | always render |
| `interaction.proximity` | both | 6 | positive-only | compose-aware |
| `interaction.touch` | both | 11 | positive-only | hint replaces verb |
| `interaction.insertion` | both | 16 | positive-only | directional grid |
| `interaction.act` | both | 5 | gaze + sex | sex is trigger |
| **total** | | **79** | | |

(The previous summary listed 80 by counting `secondary.attribute.penis_no`; that
sibling was removed 2026-05-13.)

## Compose / render rules — at runtime

`Skin.labels` (path → rendered sentence) is the flat lookup used by the
non-compose path. For groups with a `compose` rule
(`interaction.proximity.*` today), `Skin._render_one` dispatches to
`Skin._render_compose`, which:

1. Scans `applied_paths` for `secondary.pose.<leaf>` entries.
2. Iterates the rule map in declaration order, picking the first
   matching pose leaf.
3. Falls back to `default` if no match.
4. Picks the `subject` (primary or secondary) and the corresponding
   `template_<subject>`.
5. Substitutes `{verb}` and `{target}` (which is the label's `target`
   field — `her mouth`, `her face`, …).
6. Two-pass interpolation handles `{entities.*.phrase}` references
   inside the verb string first, then the outer template.

If `_render_compose` raises, it logs a warning and falls back to the
static expansion — a broken compose rule degrades gracefully rather
than dropping a label entirely.

**Hint precedence (load-bearing).** Rendered label_prompts are a
**candidate** set. When the curator's hint contradicts a rendering,
the hint wins — drop or rephrase the rendered phrase rather than
emitting both (`memory/feedback_caption_hint_vs_label_render.md`).

**Label coverage discipline.** Every set label must surface as an
identifiable token in the final caption — joy compresses out facts it
considers redundant, so per-image prompts must lead with a
**`Required facts (each must appear):`** checklist of rendered
label_prompts. Without it, joy drops ~30% of labeled facts on
multi-label images (`memory/feedback_caption_label_coverage.md`).

## Forbidden vocabulary — exhaustive lists

`Skin.forbidden` is the deduplicated union of three lists.

### `entities.primary.forbidden` (woman-side size words, 18 entries)

```
giantess, tall woman, large woman, big woman, huge woman, giant woman,
towering, enormous, massive woman, colossal, gigantic, titanic,
monstrous, immense, extremely tall, super tall, incredibly tall, amazon
```

### `entities.secondary.forbidden` (man-side diminutives, 36 entries)

```
tiny, little, small man, miniature, mini, minute, figurine, figure,
doll, action figure, toy, puppet, mannequin, statuette, child, kid,
boy, young man, youth, youngster, teenager, teen, adolescent, juvenile,
dwarf, midget, pygmy, gnome, imp, shrunken man, shrunk man,
shrunken person, shirtless, has a build, with a build, is naked, with
```

### `interaction.forbidden` (clause-level traps, 2 entries)

```
is naked, with
, naked,
```

`Skin._built.forbidden` is the deduplicated union: **55 phrases total**
(`is naked, with` appears in both the secondary and the interaction
list; the union drops the duplicate). Validation regex is anchored at
word boundaries (`\b…\b`, case-insensitive) and matches as a full
substring — so `figure` matches `figure on a base` and `tiny` matches
`a tiny figure`, but `figurine` does NOT match `figure` (different
boundary). Triggered by `Skin.caption_violations`.

### Body-type word gating (`body_type_words`, 4 authorizers)

Maps each authorizing `primary.attribute.*` label to the words that
require it. A caption containing any word without the matching label
is a body-type violation (`Skin.body_type_warnings`).

```json
{
  "muscular": ["muscular", "muscle", "bodybuilder", "ripped", "defined"],
  "busty":    ["busty", "large breasts", "big breasts", "voluptuous"],
  "slim":     ["slim", "slender", "athletic build", "lean"],
  "curvy":    ["curvy", "hourglass", "voluptuous"]
}
```

Note `voluptuous` is authorized by either `busty` OR `curvy`. There is
no entry today for `hairy`, `bigass`, `leggy` — body-type-word gating
covers only the four most-confused vocabulary clusters. The mechanism
is woman-only; man-side body adjectives (`with a muscular build`,
`toned`) slip both this check and the bare `with a build` substring
(adjective insertion). Mitigation: inline prompt guards
(`conf/skins/1xlasm.md §5.4`) and Stage-3 auto-fix.

### Inline directive bans (in the directive prose, not the regex)

The training-mode directive (`_built.directive`, see §directives) also
enumerates ban lists inline as natural-language constraints to anchor
JoyCaption's understanding. These are SOFT bans — they shape generation
but are not validated mechanically (the regex is). Quoted verbatim:

- Woman-side magnitude exemplars: `'tall', 'large', 'giant', 'huge',
  'towering', 'enormous', 'massive', 'colossal'`, plus any numerical
  heights — the trigger phrase carries her size concept.
- Body-type/breast vocabulary the woman-side rule conditionally allows:
  `'muscular', 'bodybuilder', 'busty', 'voluptuous', 'slim',
  'slender', 'lean', 'curvy', 'hourglass', 'cleavage', 'large
  breasts', 'big breasts'`.
- Man-side diminutive exemplars: `'tiny', 'little', 'small',
  'miniature', 'child', 'kid', 'boy', 'figurine', 'doll', 'toy',
  'youth', 'shrunken'`.
- Man-side body-build words (conditional): `'slim', 'muscular',
  'toned', 'athletic', 'lean', 'fit'`.

## Concepts — full enumeration

`conf/skins/1xlasm.json §concepts` defines 7 top-level concepts used
by `/v1-status` and `/todo-ai`. Each concept names labels (matched on
leaf segment, with prefix wildcards) and a `target` count. A label
matches a concept if its leaf is in `concept.labels`, or its leaf
starts with any `concept.label_prefix`. A "done" image is one whose
applied labels match the concept's labels.

### `insertion` (target: 200)

Any insertion-themed scene. Matches labels: `insert`, `panties`, OR
any leaf starting with `breasts_` / `vagina_` / `ass_` / `mouth_`. Four
sub-concepts split by orifice (each is its own counter, but the parent
`insertion` is the headline number).

- `insertion.breasts` — leaves starting `breasts_` (i.e.
  `breasts_body`, `breasts_head`, `breasts_low`, `breasts_up`).
- `insertion.vagina` — leaves starting `vagina_` (4 leaves).
- `insertion.ass` — leaves starting `ass_` (3 leaves).
- `insertion.mouth` — leaves starting `mouth_` (4 leaves).

### `holding` (target: 130)

Matches single label: `holding`. The `holding` action is the most
common interaction in the dataset (68 occurrences at rating ≥ 3 as of
2026-05-14) and the easiest archetype for joy to caption faithfully.

### `stepping` (target: 130)

Matches single label: `step`. Foot-on-body interactions. Currently
under-represented (concept_done=7 vs target=130, the largest deficit).

### `handjob` (target: 130)

Matches both `handjob` AND `teasing_hj`. Curator-discretion split: the
distinction is mostly fingertips-only (teasing) vs full grip (handjob).

### `blowjob` (target: 130)

Matches single label: `blowjob`. The expansion contains the literal
mechanic ("erect penis inserted into her mouth"); joy reliably emits
the full sentence when the label is set.

### `masturbation` (target: 130)

Matches single label: `masturbating`. Note: not `secondary.action.cum`
— `cum` is its own state, not a separate concept.

### `general` (target: 100, **residual: true**)

Catch-all for labeled images that don't match any other concept. The
residual concept is evaluated last in `Skin.matched_concepts`, with
`any_themed_matched` set to whether any non-residual concept matched.
The `general` concept ignores body-type labels when computing
"themed":

```
ignore_labels: ['muscular', 'busty', 'slim', 'curvy', 'hairy']
```

So an image with only `primary.attribute.busty` + `primary.pose.front`
still routes to `general` even though it has applied labels. Rationale:
body-type labels are surface modifiers, not the dominant concept of an
image.

### Concept totals (current snapshot, 2026-05-10 claude_todo run)

| concept | target | done | deficit |
| --- | --- | --- | --- |
| insertion | 200 | 21 | 0.895 |
| holding | 130 | 34 | 0.7385 |
| stepping | 130 | 7 | 0.9462 |
| handjob | 130 | 10 | 0.9231 |
| blowjob | 130 | 14 | 0.8923 |
| masturbation | 130 | 5 | 0.9615 |
| general | 100 | 12 | 0.88 |

Deficits drive `/todo-ai`'s priority scoring; the largest deficit at
the smallest closeness gets the top rank.

## Hint corpus — curator voice samples

Hints are short, terse, verb+bodypart focused. The literal `'none'`
hint is a sentinel that means "no extra hint applies" and triggers the
runtime to drop the user-hint preamble entirely
(`Skin.compile_user_prompt` treats it case-insensitively).

20 representative non-empty hints from rating ≥ 3, sampled across the
length distribution (5–157 chars). Verbatim, with image `_id`:

```
69248d4bc292ff981d09dc6  'none'
69a15a40b4eba93e5a5be5f3  'none'
69924ac7da9f782aa6b027da  'he lies at her feet.'
69ab30ca1acf6dfd69c33b25  'he embraces her left calve.'
69f4b218f94a40ee841afc08  'she holds him close to her mouth.'
69a159eaf7920bcd794912c2  'she has a long tongue and clown makeup.'
69ba761b120ee6e85c53c1b5  'she holds him in her left hand upside down.'
69ab3503a4ea43232af362ab  'she holds him close to her mouth with one hand.'
69924b178bb0e2cd931b4184  'he looks at her index finger which she has raised.'
69a01bbfbedc65ea2f80331c  'she has pulled down her panties, and he is peeking out.'
69ab16c3bf9c6888149df3e1  'she points at his erect penis with her right index finger.'
69abfb423b339211ff4cc2fd  'she lifts him in her left arm, holding him under her breasts.'
69f5b7bf2ace974433a05895  'he has his hands on her buttocks and burries his face in her ass.'
69b496f90613d895b40b90dc  'she holds him close to her breasts with both hands. he sits in her hands.'
6a00d39891745ea668752f1a  'she holds him with her left hand and touches his penis with her right hand.'
69ab32b0677c0f3396fc79e4  'he lies on his back, between her thighs in her crotch. she also lies on her back.'
69abfbe4be8b30e6df2ca05b  'she is holding him by his tie. she flexes her right arm, revealing her hairy armpit.'
69f4ca38f7b7f5b04564e5ff  'she is holding him close to her chest.she touches his erect penis with her index finger.'
699ff1d6fe4c5b5e9428c3d4  'she holds her breasts.his collar is connected to hers.his right arm rests on her right thigh.'
699d726bd3279c7d6d664e29  'he hangs on a chain connected to her golden chain around her stomach. he is close to her pubic hair.'
69b9107b3c7a729beaecb222  'she sits and holds him in her hands by his thighs.\nhe sits in her hands, which are positioned at her lap.'
69abfbcfcbafe0dc4c6c63dd  'he is hanging. \nshe touches his penis with her thumb and index finger.\nshe holds a feather tickler close to his penis.'
```

Patterns to internalise:

- **No vocative or framing.** Hints jump straight to `he` / `she` /
  `they` — no `In this image, …` preface. The runtime preamble
  (`Skin.user_hint_preamble`) supplies that framing.
- **Specific body-parts.** `index finger`, `thumb and index finger`,
  `bicep`, `right arm`, `left calve`, `hairy armpit` — never `hand`
  or `arm` when finer parts are visible. This is the load-bearing
  detail that joy collapses without the hint preamble's
  "preserve every body-part reference verbatim" instruction.
- **Spatial relations stated as verbs.** `embraces`, `wraps`, `lies`,
  `presses`, `points at`, `peeking out`, `worships`, `burries his face
  in`, `flexes`. These are the verbs that joy needs to keep verbatim —
  collapsing `embraces her calve` to `near her calve` loses both the
  active stance and the body-part precision.
- **Multi-sentence hints** are valid and stack mechanically. `\n`
  separators are common; the preamble treats the whole hint as one
  paragraph.
- **Curator typos pass through.** `burries`, `knees` (for `kneels`),
  `BSDM` (for BDSM) — these come through unmodified and joy mostly
  copies them. Stage 3 does not auto-correct curator spelling.

## Sample `caption_joy` outputs — LoRA's prose style

10 representative outputs sampled to span body types, interaction
modes, and hint specificity. The prose is the actual training-data
distribution that `gts3` epochs 1-10 learned from.

### Sample 1 — busty + breast-insertion, multi-fact hint

- `_id`: `69abfa9e20b1857bc02c394c`
- labels: `primary.attribute.busty`, `primary.pose.front`, `primary.pose.standing`, `secondary.attribute.penis`, `secondary.pose.front`, `secondary.pose.on_back`, `interaction.proximity.breasts`, `interaction.touch.breast`, `interaction.insertion.breasts_body`, `interaction.act.she_look_at_him`, `secondary.pose.arms_spread`
- hint: `'he is lying on her breasts streching her shirt fabric.\nhe has his hands over her breasts.\nher breasts are wrapping around his body.'`
- caption_joy:

> The xlgts woman stands front-on, and the xlasm man is lying on her breasts, stretching her shirt fabric. The xlasm man has an erect penis. He has his hands over her breasts. Her breasts are wrapping around his body. The xlgts woman has prominently large breasts. She is looking at him with a smile. The xlasm man has his arms spread wide apart. This image features a xlgts woman and a naked xlasm man. The xlgts woman has long pink hair and is wearing a teal long-sleeve shirt. The background shows a bedroom with a window, green curtains, and a floral painting on the wall. The lighting is natural, coming from the window. The camera angle is slightly low, looking up at the xlgts woman.

### Sample 2 — curvy + holding, mutual gaze

- `_id`: `69f727d89f03180e9df1e28a`
- labels: `secondary.attribute.penis`, `primary.action.holding`, `secondary.pose.front`, `primary.attribute.curvy`, `primary.pose.standing`, `secondary.pose.lifted`
- hint: `'she holds him close to her breasts with one hand. they are looking at each other.she touches his erect penis with her index finger.'`
- caption_joy:

> The xlgts woman holds the naked xlasm man close to her breasts with one hand. She has curvy hourglass proportions and is standing upright. The xlasm man has an erect penis and is seen from the front. They are looking at each other. She touches his erect penis with her index finger. The xlgts woman has long, wavy brown hair and is wearing a deep blue, ruched dress with a low neckline. The xlasm man is lifted by the xlgts woman. The background shows a beige wall with a large, gold-framed mirror on the right and a white lampshade on a table to the left. The xlgts woman's dress is the only clothing visible. The camera angle is slightly below eye level, focusing on the xlgts woman's upper body and the xlasm man's lower body. The lighting is soft and natural, highlighting the xlgts woman's facial features and the texture of her dress. The xlgts woman's expression is calm and focused as she looks at the xlasm man.

### Sample 3 — muscular + tower + thigh-touch

- `_id`: `69b7d8fe9742bf587793ac4d`
- labels: `primary.attribute.muscular`, `primary.pose.front`, `primary.pose.standing`, `primary.pose.tower`, `secondary.attribute.penis`, `secondary.pose.standing`, `secondary.pose.side`, `interaction.proximity.thighs`, `interaction.touch.thigh`, `interaction.act.look_at_each`
- hint: `'he looks up to her and touches her left thigh.'`
- caption_joy:

> This image features a xlgts woman and a xlasm man. The xlgts woman stands in a bedroom, wearing black lace lingerie, including a bra, panties, and garter belt, with black thigh-high stockings and black high-heeled shoes. Her black lace bra has thin straps and a delicate pattern, and her panties match the lace bra. She has a muscular bodybuilder physique with visible muscle definition. Her black lace bra covers her breasts, and she is not wearing any other clothing. The xlasm man is naked and stands between her thighs, looking up at her with his hands touching her left thigh. He has an erect penis. The bedroom has a gray bed with white sheets and two white lamps on dark wooden nightstands. Two large windows with white curtains are in the background, allowing natural light to fill the room. The xlgts woman has short black hair and a confident expression, looking down at the xlasm man. The room is simply decorated, with a focus on the interaction between the two figures. The camera angle is straight-on, capturing the height difference between the two figures.

### Sample 4 — muscular + hairy, perched on bicep

- `_id`: `69b7ce8912e8afd94e30a7aa`
- labels: `interaction.act.look_at_each`, `primary.attribute.muscular`, `primary.attribute.hairy`, `primary.pose.front`, `primary.pose.standing`, `secondary.pose.front`, `secondary.pose.sitting`, `secondary.attribute.penis`
- hint: `'he sits on her bicep.'`
- caption_joy:

> The xlgts woman stands front-on with the xlasm man sitting on her bicep. The xlgts woman flexes her right arm, showing off her bicep. The xlasm man has an erect penis. The xlgts woman has a muscular bodybuilder physique with visible muscle definition. The xlgts woman has a black tank top and her pubic area is hairy. The xlasm man is naked. The xlasm man sits on her bicep, looking at her. The xlgts woman has a confident smile, with pink lipstick and brown hair. Her right arm is raised, and she is flexing her bicep. The background is a dark, industrial setting with a metallic wall. The camera angle is slightly low, focusing on the xlgts woman's face and bicep.

### Sample 5 — handjob, sitting between thighs, she_look_at_penis

- `_id`: `69a1598d1269d78dec20c102`
- labels: `primary.pose.front`, `primary.pose.legs_spread`, `primary.pose.sitting`, `secondary.attribute.penis`, `secondary.pose.front`, `secondary.pose.sitting`, `secondary.pose.on_back`, `primary.action.handjob`, `interaction.act.she_look_at_penis`
- hint: `'she sits on the bed and he sits between her thighs centered in her lap..'`
- caption_joy:

> This image features a xlgts woman and a naked xlasm man. The xlgts woman sits on a bed with her legs spread wide apart and is giving the xlasm man a handjob; the xlasm man sits in her lap between her thighs. The xlgts woman has an erect penis. She is looking at his erect penis. The xlasm man has an erect penis. The xlgts woman has her hands on the xlasm man's erect penis, and her fingers are wrapped around it. The xlgts woman is looking at the xlasm man's erect penis. She is. The xlasm man is seated on the bed between her thighs, centered in her lap. The xlgts woman has her legs spread wide apart, and the xlasm man is positioned between her thighs. The background shows a bedroom with a bed, two lamps on either side of the bed, a framed floral painting on the wall, and a window with white curtains. The bed has a gray comforter, and the room has a carpet with a colorful pattern. The xlgts woman is smiling at the xlasm man's erect penis. The light in the room is natural, coming from the window. The camera angle is slightly above and to the right of the bed, capturing both figures from the front.

Note the **failure modes** in this one: (a) `The xlgts woman has an
erect penis.` — penis attribution drift, joy momentarily attached the
penis to the wrong figure; (b) `She is.` — orphan fragment. Both are
characteristic of multi-label captions and are exactly what Stage-3
auto-fix targets.

### Sample 6 — blowjob, hint='none'

- `_id`: `69fcdab1fa205eb4e836a737`
- labels: `primary.action.blowjob`, `secondary.pose.on_back`, `secondary.attribute.penis`, `secondary.pose.side`, `secondary.pose.lying`
- hint: `'none'` (sentinel — preamble dropped)
- caption_joy:

> The xlgts woman is giving the xlasm man a blowjob. The xlgts woman has her face close to the xlasm man's erect penis, which is inserted into her mouth. She has her lips closed around his erect penis. The xlasm man is lying on his back with his erect penis visible. The xlgts woman has her right hand on the xlasm man's leg. The xlgts woman is wearing a white veil and pearl earrings, and she has red nail polish. The xlasm man is naked. The background includes a white veil and a bouquet of flowers on a wooden surface to the right. The xlgts woman's face is in the foreground, while the xlasm man's face is in the background.

### Sample 7 — panties insertion, hairy

- `_id`: `69a0635afd45b4547fefcec5`
- labels: `primary.attribute.hairy`, `primary.pose.front`, `primary.pose.standing`, `secondary.pose.front`, `interaction.insertion.panties`
- hint: `'he is inserted into her panties.\nhis lower body is visible through the see-through fabric of her panties.'`
- caption_joy:

> This image features a xlgts woman and a naked xlasm man. The xlgts woman stands front-on and the xlasm man is inserted into the waistband of her panties. The xlgts woman's hands are pulling her panties slightly down, revealing her pubic area, which is hairy. The xlasm man is partly inserted into the waistband of her panties. His lower body is visible through the see-through fabric of her panties. The xlgts woman has red painted fingernails. The background is a blurred indoor setting.

### Sample 8 — bigass + proximity, behind-pose

- `_id`: `69a0765f0d5143e686c44db2`
- labels: `primary.attribute.bigass`, `primary.pose.all4`, `primary.pose.side`, `secondary.attribute.penis`, `secondary.pose.side`, `secondary.pose.standing`, `interaction.proximity.ass`, `interaction.touch.ass`
- hint: `'he stands behind her ass, worshipping it.'`
- caption_joy:

> This image features a xlgts woman and a xlasm man. The xlgts woman is on all fours seen from the side. The naked xlasm man stands behind her ass, worshipping it. The xlasm man has an erect penis. The xlgts woman has a big round ass. The xlgts woman is smiling at the camera, looking over her shoulder. She is with her breasts visible. The xlasm man is positioned behind her, his erect penis close to her ass. The bed has white sheets, and the background includes a gray headboard and a white lamp on a nightstand. The room has a neutral color palette with light gray walls and wooden accents. The xlgts woman's skin is fair, and her brown hair is shoulder-length.

### Sample 9 — sex (the only `interaction.act.sex` example in the cohort)

- `_id`: `69b6870a99919a8dfea1c575`
- labels: `primary.pose.front`, `primary.pose.legs_spread`, `primary.pose.sitting`, `secondary.attribute.penis`, `secondary.pose.side`, `secondary.pose.kneeling`, `interaction.act.she_look_at_him`, `interaction.act.sex`
- hint: `'he knees between her thighs in her crotch.\nhis penis is inserted into her vagina.'`
- caption_joy:

> This image features a xlgts woman and a xlasm man. The xlgts woman sits on a bed with her legs spread wide apart. The naked xlasm man has sex with her, inserting his erect penis into her vagina. He kneels between her thighs in her crotch. The xlgts woman looks at him. The bed has a white sheet and a dark blue blanket. The room has patterned wallpaper, two lit lamps on either side of the bed, and two framed portraits on the wall. A bouquet of flowers is in a vase on a table to the right. The xlgts woman has long black hair and is. The xlasm man has an erect penis. The room is lit by natural light from a window with white curtains. The xlgts woman has her hands on her thighs. The camera angle is slightly above and to the left of the xlgts woman. The setting is a bedroom with ornate furniture.

(Note the second `She is.` orphan fragment — same Stage-3 target as
Sample 5.)

### Sample 10 — teasing handjob on a BDSM cross (plain — no body type)

- `_id`: `69a02284b5f1df6db04bd2a9`
- labels: `secondary.pose.front`, `secondary.attribute.penis`, `secondary.pose.hanging`, `secondary.pose.arms_spread`, `secondary.pose.legs_spread`, `primary.action.teasing_hj`
- hint: `'she touches his erect penis with her index finger. he is tied to a wooden bsdm cross.'`
- caption_joy:

> This image features a xlgts woman and a naked xlasm man. The xlgts woman is giving the xlasm man a teasing handjob. The xlasm man has an erect penis. The xlgts woman touches the xlasm man's erect penis with her index finger. The xlasm man hangs tied to a wooden bsdm cross. The xlgts woman has her arms raised and secured to the cross with black leather straps, and her mouth is open in an expression of pleasure or surprise. The wooden cross is made of light brown wood and has black leather straps securing the xlasm man's wrists and ankles. The background is a solid light blue color. The xlgts woman has short, silver-gray hair, and is otherwise naked, with no clothing visible. Her nails are painted red. The camera angle is straight-on, capturing the entire scene from a slightly elevated perspective.

Observations across the 10 samples:

- Fluent prose, not bullet sentences — Qwen2.5-VL rewards prose
  (`memory/feedback_caption_prompt_fluent_qwen.md`).
- 4-6 short complete sentences for the central interaction, then
  background / clothing / camera as a closing paragraph.
- Triggers `xlgts woman` and `xlasm man` are reintroduced almost in
  every sentence (rather than substituting `she` / `he` after first
  mention). Reading awkward to a human; ideal for LoRA training.
- The opener is often the literal default
  `This image features a xlgts woman and a [naked] xlasm man.` when
  the hint doesn't suggest a more specific compound — that fallback
  is required (`conf/skins/1xlasm.md §4.2`).

## Training-mode directive — `_built.directive`

Single source of truth, quoted verbatim from
`conf/skins/1xlasm.json §_built.directive` (assembled by
`ait.caption.skin_build`):

```
This image features two figures together: a xlgts woman and a xlasm man.

The giantess woman, the larger figure. Trigger phrase: 'xlgts woman'.
Identify her ONLY as 'xlgts woman'. Do not use 'tall', 'large',
'giant', 'huge', 'towering', 'enormous', 'massive', 'colossal', or any
numerical heights — the trigger phrase carries her size concept. Do
not use these words unless an explicit instruction later in this prompt
authorizes them: 'muscular', 'bodybuilder', 'busty', 'voluptuous',
'slim', 'slender', 'lean', 'curvy', 'hourglass', 'cleavage', 'large
breasts', 'big breasts'. Default to omitting body-type and breast
descriptions entirely.

The adult man, the smaller figure. Trigger phrase: 'xlasm man'. Always
adult-proportioned regardless of apparent size. Identify him ONLY as
'xlasm man'. Do not use 'tiny', 'little', 'small', 'miniature',
'child', 'kid', 'boy', 'figurine', 'doll', 'toy', 'youth', 'shrunken',
or any diminutive, age-reductive, or object-comparison term — he is
always an adult man. Search carefully for him in the image; he can be
hard to spot. Do not describe his body build (no 'slim', 'muscular',
'toned', 'athletic', 'lean', 'fit') unless an explicit instruction
later in this prompt authorizes it.

The interaction between the xlgts woman and the xlasm man is the
central subject of every image. Open every caption with a single
COMPLETE sentence (subject + verb + object) that explicitly names BOTH
'xlgts woman' AND 'xlasm man' together — e.g. 'This image features a
xlgts woman and a xlasm man.', 'The xlgts woman holds the xlasm man in
her palm.'. If unsure how to combine the two, default to the literal
opener 'This image features a xlgts woman and a xlasm man.' as the
first sentence. Never a noun-phrase fragment. Setting, pose, clothing,
hair, breasts, background, lighting, and camera angle come strictly
AFTER this opener. Each figure's clothing state is independent and
must be evaluated from the image directly. A figure is "naked" ONLY
when no clothing at all is visible on them. If a figure is wearing any
of: dress, skirt, top, shirt, tank top, blouse, lingerie, bra,
panties, thong, stockings, tights, hosiery, gloves, robe, gown,
harness, jacket, coat, leotard, corset, swimsuit — that figure is NOT
naked, even if much skin is exposed. Apply "naked" sparingly, only to
a fully unclothed figure, ONCE at the figure's first reference (e.g.
"The naked xlasm man …"). Never repeat "naked", "nude", "undressed",
or "unclothed" for that same figure afterward. Anti-pattern: image
shows the xlgts woman wearing a dress or lingerie → "The xlgts woman,
naked, …" is WRONG; she is clothed. Anti-pattern (repetition): "The
xlgts woman holds the naked xlasm man. The naked xlasm man smiles." is
WRONG — the second sentence must say "The xlasm man smiles." Describe
the interaction in detail using specific verbs. Use compositional
position references ('at her ankle', 'at her hip level', 'in her
palm', 'on her shoulder') — composition, not size. Do not invent
details that are not visible. Preserve every verb and body-part
reference the user hint names verbatim — do NOT collapse 'thumb and
index finger' to 'hand', 'palm' to 'hand', 'arm' to 'hand', 'wrapping
around' to 'between', or 'inserted' to 'positioned'. Use the same
body-part level (arm vs hand, palm vs hand) the hint gives. Hint
sentinel: a SceneImage whose `hints` field is the literal string
'none' (case-insensitive) means no hint applies — the runtime drops
the user-hint preamble entirely for that image. Treat it as if no
hint were provided. Never emit the construction 'is naked, with ...'
(e.g. 'The xlasm man is naked, with an erect penis'). When indicating
nudity, place 'naked' inside the noun phrase at first mention ('a
naked xlasm man', 'a naked xlgts woman'). For attributes or body
parts, use 'has' ('The xlasm man has an erect penis'). Never emit the
comma-bracketed appositive 'X, naked, Y' either; bind nudity to the
noun phrase or drop it. Never describe watermarks, logos, studio
names, brand names, captions, subtitles, or any overlaid text present
in the image. Ignore them as if they were not there. When introducing
the entities for the first time, prefer the opener 'This image
features a xlgts woman and a [naked] xlasm man.' (or '... and a
[naked] xlgts woman.' when she is the nude one) — bundle the nudity
adjective with the noun rather than asserting it later as a standalone
sentence. Use 'naked' here only if the figure is fully unclothed. When
multiple pose labels apply to the same figure (e.g. 'lying' +
'on_back', or 'sitting' + 'legs_spread'), combine them into one
fluent compound sentence ('lying on her back with her legs spread
wide apart') rather than emitting each pose as its own standalone
sentence. Avoid 'is positioned' as a filler verb; use a concrete
spatial verb or omit.
```

Length: 4,825 characters. Used verbatim as the system-prompt body in
`JoyNG.caption` and `JoySceneDBNG.caption`. Built by
`ait.caption.skin_build` from `entities.primary.description`,
`entities.primary.rules`, `entities.secondary.description`,
`entities.secondary.rules`, `interaction.description`, and
`interaction.rules` (interpolated with `{entities.primary.phrase}` /
`{entities.secondary.phrase}` substituted).

The legacy hand-written `_XLASM_DIRECTIVE` in `joy.py` (also referenced
in `CONTENT_SYSTEM['1xlasm']` and `CONTENT_PROMPT['1xlasm']`) is kept
only for the non-NG legacy `Joy` class invocations; the JSON-built one
is the canonical training-time directive today.

## User-hint preamble

When a hint is present and is not the sentinel `'none'`, the runtime
prepends this preamble before the rendered label_prompts (verbatim
from `conf/skins/1xlasm.json §user_hint_preamble`):

```
 In this image, the central interaction is: {hint} Describe this
interaction first and in full detail, reflecting every verb and
spatial relationship it names (do not collapse "wrapping around" into
"between", do not collapse "inserted" into "positioned", do not
collapse "squeeze" into "cup"). Use the same body-part references it
gives you (arm vs hand, palm vs hand). Do not quote, restate, or
comment on this note - just write the caption.
```

`{hint}` is substituted by `Skin.compile_user_prompt`, which also
suppresses the entire preamble when the hint is empty or equals
`'none'` (case-insensitive).

`default_prompt` is the short literal
`'Write a detailed description of this image.'`; `post_prompt` is
empty.

## Inference-mode directive — `xlasm_gen_directive`

For `script/img_caption.py` (the fish `ait_caption` quickpick), the
directive is **not** the training-mode directive. The function
`xlasm_gen_directive(emphases, hint)` in `src/ait/caption/joy.py`
produces a description-mode directive that re-frames the task as scene
description rather than image-generation prompt
(`memory/feedback_caption_prompt_inference_framing.md`). It also
inserts anti-cross-figure rules that don't appear in the training
directive (training-time captions have one ground truth; inference
needs explicit guards because the input image may not have any xlasm
elements).

### Rendered example: `emphases=['The xlgts woman has prominently large breasts.']`, `hint='she holds him close to her breasts with both hands.'`

```
Describe this image in vivid narrative prose, the way a human would
describe a scene out loud. Theme: xlasm — the xlgts woman is the
dominant focus; the xlasm man, when present, is her counterpart.
Amplify the visually striking xlasm-relevant elements (her body, her
dominance, the man's position, their interaction) and SKIP incidental
detail (mundane props, photo-meta, generic clothing, irrelevant
background). Capture the essence — do not transcribe every visible
thing. ALWAYS refer to the woman as 'xlgts woman' — the 'xlgts' token
must sit directly next to 'woman', with no words between them. Always
call the man 'xlasm man'. NEVER write 'xlasm woman' or 'xlgts man' —
'xlgts' is for women ONLY, 'xlasm' is for men ONLY. There is exactly
ONE male figure in any xlasm scene: the xlasm man. If you see ANY
small male-presenting figure (whether it looks like a statue,
figurine, doll, toy, statuette, miniature, or anything else), that
figure IS the xlasm man — describe him as 'xlasm man' and nothing
else. NEVER describe a second male figure separately. NEVER call him
'tiny', 'little', 'small', 'miniature', 'shrunken', 'child', 'boy',
'figurine', 'doll', 'statue', 'figure on a base' — he is an adult man
and the 'xlasm' token carries the scale concept. Body attributes below
apply ONLY to the entity each description names. NEVER cross-apply
between figures (e.g. NEVER say 'muscular xlasm man' — muscularity is
the xlgts woman's trait; the xlasm man is always the weaker, smaller
counterpart). Must surface: The xlgts woman has prominently large
breasts. User intent: she holds him close to her breasts with both
hands.. Reflect this naturally in the generated prompt. Write a single
fluent paragraph of complete English sentences (subject-verb-object),
~60-90 words, action-forward. ABSOLUTELY NO comma-separated tag
lists, attribute lists, or sentence fragments — this is narrative
prose, not Danbooru tags.
```

Key distinctions from the training directive:

- Framed as *describe* / *narrative prose*, NOT *generate*. The
  `image-generation prompt` / `INSPIRED by` framing forces JoyCaption
  into Danbooru tag-soup regardless of any `OUTPUT STYLE` rule
  appended later (memory file above).
- Phantom-figure guards: explicitly tells the model that any small
  male-presenting figure IS the xlasm man, never a separate doll /
  statue.
- Hint placement: inline ahead of the recency `OUTPUT STYLE` rule via
  the `User intent: …` block, bypassing the training-flavor
  `USER_HINT_PREAMBLE`.
- Word-count constraint (`~60-90 words`) — inference captions are
  much shorter than training captions because the user is reading
  them, not feeding them to a LoRA.

The empty-emphases / empty-hint render is identical minus the
`Must surface: …` and `User intent: …` blocks.

## Sets — the canonical training sets in `scenes_prod.sets`

The `sets` collection holds **2 sets** today. Set membership is
modeled at the **scene** level: a scene carries the label
`set___<set_name>`, and the set's `query` selects scenes by that
label. Image counts are derived from scenes in the set (the per-image
filter applies on top via `rating` etc).

| set | query (scenes) | imgs_exclude | scenes_exclude | ratios | resolutions |
| --- | --- | --- | --- | --- | --- |
| `gts_v3` | `{'labels': 'set___gts_v3'}` | 37 imgs | 2 scenes | `[1.0, 0.75, 0.6667, 0.6]` | `[1024]` |
| `test` | `{'labels': 'set___test'}` | none | none | (default) | (default) |

### `gts_v3` (production training set)

- 444 scenes carry `set___gts_v3`, 2 explicitly excluded → 442
  effective scenes.
- Aspect ratios trained: `1.0` (square), `0.75` (3:4 portrait),
  `0.6667` (2:3 portrait), `0.6` (3:5 portrait) — no landscape today.
- Resolution: `1024` only (Qwen-Image default).
- Suppressed images (`imgs_exclude`): 37 entries by `_id`, typically
  duplicates or low-quality variants kept around for traceability but
  not exported to the HF dataset.

### `test` (development cohort)

- 4 scenes carry `set___test`, 0 image excludes.
- Default ratios / resolutions (whatever the trainer infers from the
  imgs themselves).
- Used as the pytest fixture for `JoySceneDBNG` integration tests.

## `ait-caption-log` — inference-mode usage corpus

`ait-caption-log` is the MongoDB collection where every
`ait_caption` quickpick invocation logs its `user_input`,
`caption_prompt`, and `caption_joy` (`script/img_caption.py`).
**19 entries** to date (was 17 at the previous snapshot).

5 representative entries:

```
_id=6a05a9e87ec774098b6690b3
  user_input: {body_label: 'busty', penis: False, hint: 'she sits on a bed.he stands between her thighs, looking up to her.'}
  caption_joy[0:200]: 'xlgts woman with large breasts sitting on a bed, green crop hoodie and matching panties, very muscular abs, long wavy brown hair, looking down at xlasm man, xlasm man standing between her thighs, look'

_id=6a05aae79cf3d7c786980dba
  user_input: {body_label: None, penis: True, hint: 'she knees and he worships her leg.'}
  caption_joy[0:200]: 'digital art, xlgts woman with long red hair, red cardigan, black top, purple skirt, black boots, kneeling in a dimly lit library room, xlasm man with black suit, standing in front of her leg, she hold'

_id=6a05cf197f63ce8511cdb295
  user_input: {body_label: 'muscular', penis: False, hint: 'he looks up to her'}
  caption_joy[0:200]: 'A photograph of a giantess bride and a tiny man. The xlgts woman has a muscular bodybuilder physique with visible muscle definition, wearing a white, sleeveless, lace wedding dress with a high slit, a'

_id=6a05c7e530d42bad98999137
  user_input: {body_label: 'busty', penis: False, hint: ''}
  caption_joy[0:200]: 'A digital illustration shows a xlgts woman with extremely large breasts standing naked in a room, looking down at a small, vulnerable xlasm man. The xlasm man stands in the background, looking up at h'

_id=6a05c8d2e0732d2bb2cc8361
  user_input: {body_label: 'muscular', penis: True, hint: 'he stands behind her and masturbates, looking up to her. she flexes her biceps.'}
  caption_joy[0:200]: 'A digital rendering of a muscular xlgts woman with visible muscle definition, standing naked in front of a staircase. She flexes her biceps, showing off her strength. In front of her, a small, vulnerable'
```

Patterns:

- `user_input` is always `{body_label, penis, hint}` — three slots.
- Three observed `hint='xlgts only, no xlasm'` invocations: curators
  use the inference path to caption woman-only images by suppressing
  the xlasm-figure expectation.
- Curators routinely leave `body_label=None` (no emphasis applied) —
  the body emphasis is opt-in even at inference.
- Even with the anti-diminutive guards, `_id=6a05cf197f63ce8511cdb295`
  produced "A photograph of a giantess bride and a tiny man" — both
  forbidden words. This is the kind of leak the post-training-mode
  Stage-3 validator does not catch (since the inference path doesn't
  run Stage-3). TODO: extend `/imgs_validate_captions` to optionally
  scan `ait-caption-log` entries too, or run a one-off audit.

## `claude_*` collections — Claude scratch state

The codebase explicitly reserves `claude_*` collection names for
AI-side scratch state (`CLAUDE.md §Cross-cutting`). Claude may freely
create/read/write these alongside the canonical `scenes`/`images`/`sets`.
Today **1 collection** is active.

### `claude_todo` (1 doc)

Backs the gradio "todo ai 20" button on the scene-rating app
(`src/aidb/app/tab_search_and_rate.py`). Schema written by
`/todo-ai`:

```json
{
  "_id": ObjectId(...),
  "set_name": "gts_v3",
  "kind": "caption_priority",
  "generated_at": ISODate("2026-05-10T08:23:05Z"),
  "version": 1,
  "concept_deficits": {"insertion": 0.895, "holding": 0.7385, ...},
  "concept_done": {"insertion": 21, "holding": 34, ...},
  "items": [
    {"image_id": "699ff102c5eecd82740823b3", "score": 0.895, "concepts": ["insertion"], "closeness": 0},
    {"image_id": "699ff2e6336cef263024f35b", "score": 0.895, "concepts": ["insertion"], "closeness": 0},
    ...19 entries total
  ]
}
```

The `items` array is the ranked priority queue: each
non-`rating==3` image is scored by
`concept_deficit × (1 - closeness)`, where closeness is
`labels_ng_size / 6` (a proxy for "how close to done" — labels are
typed first, hints next, rating last). Higher score = higher
priority. The gradio button reads the top 20 and displays their
thumbnails for curator triage.

The collection is overwritten by every `/todo-ai` run — there is no
history. The version 1 schema documents itself at the top of the
`/todo-ai` slash command markdown.

No other `claude_*` collections exist today (no `claude_scratch`,
no `claude_index`, etc.). Future caption-priority cache, scoring
artifacts, etc. would live here.

## Slash command inventory

All slash commands related to the 1xlasm captioning pipeline. Source
files live in `/home/misw/venv/aitools/aitools/.claude/commands/`;
each one-line description is quoted from its front-matter
`description` field.

### Stage 1 — caption_prompt composition

| command | source | purpose |
| --- | --- | --- |
| `/img_caption` | `img_caption.md` | Run the full caption pipeline (compose prompt → caption → validate) for ONE image by ObjectId. No batch mode — single-image only. |
| `/imgs_caption_prompt` | `imgs_caption_prompt.md` | Run the per-image judgment-mode caption_prompt compile (the same Stage 1 as /img_caption) on curated images. Default scope: stale prompts. |
| `/imgs_update_caption_prompt` | `imgs_update_caption_prompt.md` | Compile a focused caption_prompt for one image (with id) OR bulk-refresh many images with optional scope filters. |

### Stage 2 — caption_joy (JoyCaption inference)

| command | source | purpose |
| --- | --- | --- |
| `/imgs_caption_joy` | `imgs_caption_joy.md` | Caption curated images whose caption_joy is stale wrt caption_prompt. Uses stored caption_prompt verbatim. |
| `/imgs_update_caption_joy` | `imgs_update_caption_joy.md` | Run JoySceneDBNG('1xlasm') against one image (with id) OR a filtered batch. Only images whose caption_prompt is newer than caption_joy are captioned. |

### Stage 3 — validation + auto-fix

| command | source | purpose |
| --- | --- | --- |
| `/imgs_validate_captions` | `imgs_validate_captions.md` | Audit caption_joy in a scope against the skin's rules (forbidden vocab, body-type authorization, missing triggers, naked-multi, opener) and auto-fix the mechanically tractable issues. |
| `/imgs_fix_captions` | `imgs_fix_captions.md` | Audit and fix captions where hints/labels are not correctly integrated. |

### Orchestration

| command | source | purpose |
| --- | --- | --- |
| `/imgs_caption` | `imgs_caption.md` | Orchestrator that runs Stage 1 (`/imgs_caption_prompt`) followed by Stage 2+3 (`/imgs_caption_joy`) on the same `$ARGUMENTS`. |

### Suggestion (pre-curation)

| command | source | purpose |
| --- | --- | --- |
| `/img_suggest` | `img_suggest.md` | Iteratively probe JoyCaption to suggest labels_ng + hints for an image. Max 5 iterations, converge early. Persists labels_ng_SUGGESTION / hints_SUGGESTION; never canonical. |
| `/imgs_suggest` | `imgs_suggest.md` | Batch /img_suggest. Picks the newest active image from each scene that has no done image. Top N. |
| `/imgs_validate_suggestions` | `imgs_validate_suggestions.md` | Validate the /img_suggest process against curator-authored labels+hints on done images. Picks N random done images, runs the loop blind, reports aggregate metrics. |

### Infrastructure

| command | source | purpose |
| --- | --- | --- |
| `/joy_server` | `joy_server.md` | Lifecycle control for the persistent JoyCaption server (start/stop/status/restart). Server loads the captioner model once, serves over HTTP, avoiding the ~23s model-load cost per call. |

### Reporting / planning

| command | source | purpose |
| --- | --- | --- |
| `/v1-status` | `v1-status.md` | Report v1 dataset progress for the gts LoRA against the editable plan. Concept map and per-concept targets are sourced from the skin JSON. |
| `/todo-ai` | `todo-ai.md` | Score every potential image by concept-deficit weighted by closeness-to-done and persist the ranked list to the `claude_todo` collection so the gradio "todo ai 20" button can read it. |

## Models & LoRAs in production

**Captioning** (`Skin.model_key`, `Skin.lora_key`, `Skin.lora_hint_path`):

- Base: `fancyfeast/llama-joycaption-beta-one-hf-llava` (HF, no
  install — declared `no_install` in
  `conf/models/models_capjoy.json`). `Skin.model_key` =
  `('capjoy', 'common', 'model')`.
- Adapter `capjoy/common/lora`: `fbbcool/joy-gts-lora-jp` — the
  captioning LoRA fine-tuned on the curated 1xlasm caption
  distribution.
- Adapter `Skin.lora_hint_path`:
  `/home/misw/Workspace/joy_hint_lora_gts_v3_v3/adapter` — the rank-32
  / 8-epoch hint LoRA from 2026-05-12, used at `/img_suggest` iter-5
  only (`memory/project_hint_lora.md`). Note: this is a **local path**,
  decoupled from `AInstallerDB` because the LoRA is curator-private
  and not on HF.

**Image generation** (downstream consumer of the captions):

- `gts3` — current production family. Epoch-10 snapshot is
  `xlasm10-test.safetensors`, published at
  `fbbcool/qwen-2512-snofs-0.65` alongside the base merge
  `qwen-image-2512-snofs0.65-fp8.safetensors`
  (`conf/models/models_train_qwen.json §2512-snofs`).
- The fish `ait_caption` quickpick exposes every
  `primary.attribute.*` label; only the `busty` emphasis maps to a
  distinct trained LoRA today (`xlbusty`).

## Accumulated rules — one-line index

Each cites the memory file for full context.

- **Hint > label rendering** — drop / rephrase any rendered
  label_prompt the hint contradicts. The
  `proximity.* without contact or insertion` suffix was a known bug
  fixed 2026-05-13 (`memory/feedback_caption_hint_vs_label_render.md`).
- **Label coverage** — every set label must surface as a caption
  token; lead the prompt with a required-facts checklist of rendered
  label_prompts; joy drops ~30% otherwise
  (`memory/feedback_caption_label_coverage.md`).
- **Soft-nudge, never hard-ban** — asymmetric cost: dropped info >>
  clutter. Prompts SOFT-nudge against filler; Stage 3 mops up
  mechanical violations. Hard bans cost ~30% completeness
  (`memory/feedback_caption_background_grounding.md`).
- **Re-read labels per compose** — every per-image prompt heredoc
  must re-read `labels_ng` + `hints` from the DB; curators edit
  between iterations and stale mental state corrupts later prompts
  (`memory/feedback_caption_prompt_reread.md`).
- **Fluent prose default** — Qwen2.5-VL text encoder rewards prose;
  bullet captions embed in a non-natural region. Per-image prompt
  asks for prose with structural guidance + required-facts checklist
  (`memory/feedback_caption_prompt_fluent_qwen.md`).
- **Minimal per-image prompt** — required facts + hint verbs +
  structure + low-level filler ban; no anti-hallucination text. Trust
  the JP LoRA, let Stage 3 catch residuals
  (`memory/feedback_caption_prompt_minimal.md`).
- **Positive-only labels (except `penis`)** — presence = concept in
  scene; absence = no info. `secondary.attribute.penis` is the sole
  bidirectional label (absence = no penis in scene, must omit
  mention). Renderings must not contain negative claims (except
  penis-related). PENIS_AUTH = `{penis}` only; no transitive
  authorization from action labels
  (`memory/feedback_label_semantics_positive_only.md`).
- **Inference framing — "describe", not "generation prompt"** — for
  `ait_caption`, the directive must frame the task as scene
  description. `"image-generation prompt"`, `"INSPIRED by"`,
  `"feed back into an image generator"` force JoyCaption into
  Danbooru tag-soup regardless of any `OUTPUT STYLE` rule appended
  later (`memory/feedback_caption_prompt_inference_framing.md`).
- **Rare-position hint corner case** — hints placing the man in
  positions rare in the capjoy LoRA prior (`behind her`) trigger
  phantom-second-figure hallucinations. Accept; don't pile more
  anti-statue / anti-figurine guards into the directive
  (`memory/feedback_caption_hint_position_conflict.md`).
- **Always reply in English** (`memory/feedback_language_english.md`).
- **Never kill ComfyUI** — never kill ComfyUI to free GPU; report
  contention and wait (`memory/feedback_never_kill_comfyui.md`).

## Known failure modes

- **`is naked, with X` / `is nude, with X`** — base-joycaption habit;
  ~15% rate in the unconstrained baseline, ~7% with inline guards.
  Stage-3 regex `is\s+(naked|nude),\s*with\b` auto-fixes
  (`1xlasm.md §5.1`).
- **`with a <adj> build`** — slips the bare `with a build` regex via
  adjective insertion. Inline prompt guard plus optional Stage-3
  rewrite (`1xlasm.md §5.4`).
- **Repeated `naked`** — first-mention establishes nudity; later
  mentions are redundant. Stage-3 strips
  (`memory/project_caption_skin_refactor.md` summarises a session
  that took naked-multi 30/78 → 0/78).
- **Watermark / logo descriptions** — ~5/119 baseline. Stage-3 drops
  the sentence (`1xlasm.md §5.5`).
- **Tag-soup output at inference** — caused by `"generation prompt"`
  framing in the directive. Fixed by reframing as `"describe in
  prose"` (memory file above).
- **JoyCaption drops ~30% of labeled facts without a required-facts
  checklist** — fix is the explicit checklist
  (`feedback_caption_label_coverage.md`).
- **Phantom-second-figure on rare-position hints** — accepted corner
  case (memory file above).
- **`her penis` attribution drift** — joy occasionally attaches the
  penis to the woman when the man is partly hidden or when many
  labels stack. Visible in Sample 5 above; Stage-3 drops the
  offending sentence; domain invariant: the penis is always the xlasm
  man's (`1xlasm.md §5.8`).
- **Orphan fragment "She is."** — joy emits a sentence-starter then
  flushes mid-sentence (visible in Samples 5 and 9). Stage-3 drops the
  fragment.
- **Trigger leakage to wrong figure** — historic (handled by inline
  anti-confusion rule in `xlasm_gen_directive`).
- **Length inflation on 4+ same-domain labels** — joy faithfully
  emits each label expansion as its own sentence: +47-72% inflation
  observed. Mitigation: same-domain fusion in the per-image prompt
  per `1xlasm.md §4.5`.
- **Suggestion ceilings** — `/img_suggest` plateaued at F1 ≈ 0.45
  on the captioning LoRA alone; `interaction.act` (gaze) stuck at
  0% recall, `interaction.insertion` directionality at 20% recall;
  hint jaccard climbed to 0.39 (3.9× baseline) with the hint LoRA on
  the 15 held-out validation pairs (`memory/project_hint_lora.md`).
- **Forbidden vocab still escapes inference path** — Sample
  `_id=6a05cf197f63ce8511cdb295` ("giantess bride", "tiny man") shows
  the inference-mode directive isn't strong enough to suppress those
  base-vocabulary draws when the user picks `muscular` body emphasis.
  No Stage-3 on the inference path. TODO: extend
  `/imgs_validate_captions` to optionally scan `ait-caption-log`.

## Current dataset snapshot

Queried 2026-05-14 against `scenes_prod`.

**Image counts**

- Total images in `scenes_prod.images`: **837**
- With non-empty `labels_ng`: **264**
- With non-empty `hints`: **264**
- With `rating >= 3` (the curated training cohort): **225** — and all
  225 also have non-empty `labels_ng` AND non-empty `hints`.
- Rating distribution: rating −1 = 610, rating 1 = 2, rating 3 = 225,
  rating ≥ 4 = 0 (no quality tier above 3 in current use).

**Sets** (canonical training cohort lives in `gts_v3`)

- `gts_v3`: 444 scenes (2 excluded → 442 effective), 595 imgs total
  via scene membership; 225 of those at `rating >= 3`. Suppressed: 37
  imgs.
- `test`: 4 scenes, 13 imgs. The dev set used by `pytest`.

**Hint stats among rating ≥ 3 (n=225)**

- All 225 have non-empty hints.
- `hints == 'none'` sentinel (case-insensitive): **15** (~6.7%).
- Remaining hints (n=210): mean length **73 chars / 14 words**, median
  **72 chars / 14 words**, range 5-157 chars / 1-31 words. Curator
  style is verifiably terse.

**Caption coverage (rating ≥ 3)**

- `caption_prompt` non-empty: 225 / 225 (100%).
- `caption_joy` non-empty: 225 / 225 (100%).
- `caption` non-empty: 225 / 225 (100%).
- `labels_ng_SUGGESTION` non-empty: **107** / 225 (suggestion run
  partially through the cohort; curator promotions canonicalised the
  rest).
- `hints_SUGGESTION` non-empty: **107** / 225.

**Label distribution (rating ≥ 3, 74 distinct paths used out of 79)**

Per-group totals (n_tags counts each label occurrence across images):

| group | total tags | distinct labels |
| --- | --- | --- |
| `secondary.pose` | 533 | 13 |
| `primary.pose` | 339 | 12 |
| `secondary.attribute` | 169 | 1 (only `penis`) |
| `primary.attribute` | 142 | 7 |
| `primary.action` | 127 | 5 |
| `interaction.act` | 118 | 5 |
| `interaction.touch` | 90 | 10 |
| `interaction.insertion` | 66 | 13 |
| `interaction.proximity` | 54 | 6 |
| `secondary.action` | 29 | 2 |

Top 15 individual labels: `secondary.attribute.penis` (169),
`secondary.pose.side` (108), `primary.pose.standing` (100),
`secondary.pose.lying` (74), `primary.pose.front` (70),
`primary.action.holding` (68), `secondary.pose.front` (67),
`secondary.pose.on_back` (66), `secondary.pose.lifted` (61),
`primary.attribute.busty` (49), `interaction.act.she_look_at_him`
(39), `secondary.pose.standing` (38), `primary.attribute.curvy` (37),
`secondary.pose.arms_spread` (33), `interaction.act.look_at_each`
(32).

Long tail (< 5 images each, 16 labels):
`interaction.insertion.mouth_low` (4), `vagina_head` (4),
`mouth_body` (4), `interaction.touch.pussy` (3),
`insertion.mouth_head` (2), `touch.mouth` (2),
`secondary.pose.perched` (2), `insertion.breasts_up` (2),
`vagina_up` (2), `primary.attribute.leggy` (2),
`interaction.proximity.face` (1), `touch.body` (1), `touch.leg` (1),
`insertion.ass_low` (1), `primary.pose.arms_spread` (1),
`interaction.act.sex` (1).

**Body-type coverage among rating ≥ 3**: 112 / 225 images have at
least one `primary.attribute.*` label (49.8%). Breakdown: `busty` 49,
`curvy` 37, `hairy` 22, `bigass` 16, `muscular` 11, `slim` 5,
`leggy` 2.

**`ait-caption-log` usage**: 19 inference-mode runs logged to date.

**`claude_*` collections**: 1 active — `claude_todo` (1 doc), used by
`/todo-ai`.

**Notable gaps**

- `interaction.touch.*` and `interaction.insertion.*` long tails are
  thin (under 5 imgs for ~14 of 24 variants). These are also the
  groups where `/img_suggest` recall is weakest; growing the cohort
  here would both improve LoRA coverage and validate suggestion
  fixes.
- `interaction.act.sex` has only 1 image — the canonical "vaginal
  insertion with both visible" archetype is under-represented vs the
  proximity / touch lead-ups.
- 5 labels (out of 79) have no images at rating ≥ 3.

## Pointers / further reading

| topic | file |
| --- | --- |
| machine-readable skin (entities, labels, compose, forbidden, models) | `conf/skins/1xlasm.json` |
| theme briefing (archetypes, anti-patterns, captioner quirks) | `conf/skins/1xlasm.md` |
| suggestion-process briefing (probes, joy biases, validation) | `conf/skins/1xlasm_suggestions.md` |
| JSON schema | `conf/skins/_schema.json` |
| skin runtime (Skin / SkinRegistry) | `src/ait/caption/skin.py` |
| derived-block composer | `src/ait/caption/skin_build.py` |
| pure captioning runtime | `src/ait/caption/joy_ng.py` |
| training-pipeline orchestrator | `src/ait/caption/joy_scenedb_ng.py` |
| legacy directives + `xlasm_gen_directive` | `src/ait/caption/joy.py` |
| inference entrypoint | `script/img_caption.py` |
| persistent JoyCaption server | `/joy_server` (slash command) |
| caption + suggest workflow commands | `/img_caption`, `/imgs_caption`, `/imgs_caption_prompt`, `/imgs_caption_joy`, `/imgs_validate_captions`, `/img_suggest`, `/imgs_suggest`, `/imgs_validate_suggestions`, `/imgs_update_caption_prompt`, `/imgs_fix_captions` |
| status / planning commands | `/v1-status`, `/todo-ai` |
| caption-skin refactor end-state | `memory/project_caption_skin_refactor.md` |
| hint-LoRA training plan | `memory/project_hint_lora.md` |
| accumulated feedback memories | `memory/feedback_caption_*.md`, `memory/feedback_label_*.md` |
