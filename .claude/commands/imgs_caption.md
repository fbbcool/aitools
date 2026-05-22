---
description: Orchestrator that runs Stage 1 (`/imgs_caption_prompt`) followed by Stage 2+3 (`/imgs_caption_joy`) on the same `$ARGUMENTS`. Saves the curator one round-trip when both stages need to run. Same argument grammar as both subcommands.
argument-hint: "[<image-id> | force | ignore_curated | set=<name> | rating[==|>=|<=|>|<]<n> | limit=<n>]"
---

`$ARGUMENTS` is forwarded verbatim to both subcommands. The grammar is shared with `/imgs_caption_prompt` and `/imgs_caption_joy` — see those specs for the full term list. Quick reference:

- bare 24-char hex ObjectId → single-image mode (skips eligibility, both stages run on just that image)
- `force` — process every eligible image regardless of freshness (skip recency checks) AND bypass the **rating>=3 guard** (both subcommands skip production-grade images otherwise)
- `ignore_curated` — drop the suggestion-non-empty requirement
- `set=<name>` — restrict to a SceneSet's active members
- `rating<op><n>` — relational rating filter (`rating==1`, `rating>=0`, etc.)
- `limit=<n>` — cap the batch at N images

## Pipeline

Run the two subcommands in sequence, forwarding `$ARGUMENTS` to both:

### 1. `/imgs_caption_prompt $ARGUMENTS`

Compile the judgment-mode `caption_prompt` for every eligible image. This is the expensive step — each image consumes ~15-30s of Claude's context for prompt composition. Reads `labels_ng` + `hints` fresh from DB per image (per `feedback_caption_prompt_reread.md`). Persists `FIELD_CAPTION_PROMPT`.

Apply the saved default fluent-prose template from `feedback_caption_prompt_fluent_qwen.md`:

- Required-facts checklist from `skin.render_label_prompts(labels_ng)` (positive-only renderings after the 2026-05-13 skin fix).
- Hint preservation block (preserve verbs verbatim) — UNLESS the hint is the `'none'` sentinel, in which case use the label-only compose path.
- Structure: open with interaction, weave required facts, add distinctive features (hair/skin/beard/scene/etc.), close with high-level scene location.
- Pose-mandate: `'front'`, `'back'`, `'side'`, `'lifted'`, `'lying'`, `'kneeling'`, `'standing'`, `'all fours'`, `'on her back'` must surface as literal words.
- Soft-nudge filler ban (meta-sentences, granular pattern detail, restated nudity) — never hard-ban distinctive features.

If a prompt compile fails for an image, record the failure and continue to Stage 2 only for images that did get prompts written.

### 2. `/imgs_caption_joy $ARGUMENTS`

For every image now with a non-empty `caption_prompt` and matching the filters, run the GPU caption + Stage 3 audit/auto-fix:

- GPU prereq: ≥16 GiB free. If joy_server isn't running, start it. If GPU is contested, ask the user to free ComfyUI (do NOT kill it — see `feedback_never_kill_comfyui.md`).
- Caption via `joy_client.caption()` with the stored prompt + skin directive.
- Stage 3 mechanical fixes: forbidden vocab, body-type unauthorized, `has a build` strip, meta-sentence drop, naked-multi per-figure attribution.
- Persists `FIELD_CAPTION_JOY` (and `FIELD_CAPTION` if it was previously identical to caption_joy).

## Rating>=3 guard

Inherited from both subcommands: images with `rating>=3` are skipped in batch mode unless `force` is passed (or the curator targets a single image by ObjectId, which is an implicit force). See `/imgs_caption_prompt` and `/imgs_caption_joy` for the full clause.

## When NOT to use this

- If the curator just wants to re-run Stage 2 without re-composing prompts (e.g. captioner refresh after a LoRA swap): use `/imgs_caption_joy force` directly.
- If only Stage 1 needs to run (e.g. testing prompt variations without burning GPU): use `/imgs_caption_prompt force` alone.
- For single-image experimentation with finer control between stages: use `/img_caption <id>` (the standalone single-image orchestrator).

## Report

Print the combined two-stage summary:

```
=== Stage 1 (caption_prompt) ===
imgs_caption_prompt [filters: …]: ok=N1, errors=N1err

=== Stage 2 (caption_joy) ===
imgs_caption_joy [filters: …]: ok=N2, flagged=N2f, errors=N2err, skipped_no_prompt=N2sk, total_seconds=Ns

=== imgs_caption: ok=N2, errors_total=N1err+N2err+N2sk ===
```

## Access rights

Same as the two subcommands combined: read canonical collections + write `FIELD_CAPTION_PROMPT`, `FIELD_CAPTION_JOY`, `FIELD_CAPTION`. GPU consumed for the duration of Stage 2 (~16 GiB VRAM, ~5s per image after server warmup).

## See also

- `/imgs_caption_prompt` — Stage 1 only (judgment-mode prompt compile).
- `/imgs_caption_joy` — Stage 2+3 only (GPU caption + audit/auto-fix).
- `/img_caption <id>` — single-image orchestrator (same Stage 1+2+3 pipeline, one image at a time, with on-the-fly judgment).
- `/imgs_suggest [num]` — populates the `_SUGGESTION` fields that gate "curated".
