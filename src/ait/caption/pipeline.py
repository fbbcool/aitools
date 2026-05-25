"""
Integrated captioning pipeline for the 1xlasm giantess LoRA training flow.

Pipeline per image:
  1. JoyCaption produces caption using trigger + labels (joy.py)
  2. Three validators check the caption:
       - forbidden vocabulary (magnitude words, diminutives, base-vocab collisions)
       - body-type words used without their authorizing label
       - presence of both required trigger phrases
  3. Clean captions are written directly. Flagged captions are sent through
     Lexi-Uncensored-V2 rewriter to be fixed against the 1xlasm directive.
  4. Rewritten captions are re-validated. Still-flagged captions are
     written with a status marker so you can hand-fix them.

Scale tags (s_small_gts, s_mid_gts, s_large_gts, s_mega_gts) are CSV-only
metadata - they are NOT passed to JoyCaption. They are used here only for
dataset balance auditing. The pipeline prints scale distribution at the end
so you can verify each scale tier has enough training images.

Usage:
    python pipeline.py \\
        --csv manual_tags.csv \\
        --images ./dataset/ \\
        --output captions.jsonl \\
        --write-txt
"""

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

import torch
from PIL import Image
from transformers import (
    AutoModelForCausalLM,
    AutoProcessor,
    AutoTokenizer,
    BitsAndBytesConfig,
    LlavaForConditionalGeneration,
)

# Import the directive, labels, triggers, and validators from the legacy
# xlasm helpers module (formerly joy.py — renamed after the Joy class was
# replaced by the NG pipeline).
# NOTE: `SCALE_TAGS` was historically defined here but isn't currently
# present in xlasm.py; pipeline.py's existing reference to it pre-dates
# the rename and is a known dead-import (this file is a standalone script
# not imported by anything else in the codebase).
from .xlasm import (
    CONTENT_PROMPT,
    CONTENT_SYSTEM,
    DEFAULT_PROMPT,
    DEFAULT_SYSTEM,
    LABEL_PROMPT,
    POST_PROMPT,
    TRIGGER_MAN,
    TRIGGER_WOMAN,
    _BODY_TYPE_WORDS,
    _FORBIDDEN_IN_XLASM,
    _XLASM_DIRECTIVE,
    caption_has_xlasm_violations,
    validate_body_type_consistency,
    validate_trigger_presence,
)


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

JOYCAPTION_MODEL = "fancyfeast/llama-joycaption-beta-one-hf-llava"
LEXI_MODEL = "Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2"

# CSV columns for manual tags. Edit if your CSV has different boolean columns.
# Note: scale is NOT in this list - scale lives in its own column and is
# handled separately as CSV-only metadata.
BOOLEAN_TAG_COLUMNS = [
    "b_muscular", "b_busty", "b_slim", "b_curvy",
    "pos_at_feet", "pos_at_thigh", "pos_at_hip", "pos_at_waist",
    "pos_at_chest", "pos_at_shoulder", "pos_in_palm", "pos_on_shoulder",
    "pos_held", "pos_pocket",
    "penis", "penis_no", "holding", "sitting",
    # Add any action labels you want to drive from the CSV here
]
SCALE_COLUMN = "scale"
ACTION_COLUMN = "action"
NOTES_COLUMN = "notes"
VALID_SCALES = set(SCALE_TAGS) | {""}


# ---------------------------------------------------------------------------
# REWRITER PROMPT (Lexi-Uncensored-V2)
# ---------------------------------------------------------------------------

_REWRITER_SYSTEM = f"""You are a caption fixer for a text-to-image LoRA training dataset. Your job is to fix specific violations in image captions while preserving everything else exactly as written.

THE CAPTION RULES:
{_XLASM_DIRECTIVE}

YOUR TASK:
- You will receive a caption, a list of violations, and the active labels for the image.
- Remove or rephrase ONLY the violating words and phrases.
- Preserve everything else in the caption exactly as written.
- Do NOT shorten, summarize, or restructure the caption beyond fixing violations.
- Do NOT add new content that was not in the original.
- For magnitude words (huge, towering, enormous, etc.) - delete them; the trigger phrases carry the size concept.
- For diminutives (tiny, child, figurine, doll, etc.) - replace with neutral references to "the {TRIGGER_MAN}" or remove the descriptor entirely.
- For body-type words (muscular, busty, slim, curvy) appearing without their authorizing label - delete the body-type description.
- For base-vocabulary collisions (giantess, tall woman, shrunken man, etc.) - replace with the correct trigger phrase ("{TRIGGER_WOMAN}" or "{TRIGGER_MAN}").
- For missing trigger phrases - rewrite ambiguous figure references to use "{TRIGGER_WOMAN}" and "{TRIGGER_MAN}" explicitly. Both must appear at least once.
- Output ONLY the fixed caption. No preamble, no explanation, no quotes.
"""


def build_rewriter_messages(
    caption: str,
    violations: list[str],
    body_warnings: list[str],
    missing_triggers: list[str],
    labels: list[str],
) -> list[dict]:
    """Build the chat-format message list for the Lexi rewriter."""
    parts = []
    if violations:
        parts.append(f"Forbidden words/phrases found: {', '.join(violations)}")
    if body_warnings:
        parts.append(f"Body-type violations: {'; '.join(body_warnings)}")
    if missing_triggers:
        parts.append(
            f"Missing required trigger phrases: {', '.join(missing_triggers)}. "
            f"Both must appear in the caption."
        )
    parts.append(f"Active labels for this image: {', '.join(labels) if labels else '(none)'}")
    parts.append(f"Original caption:\n{caption}")

    user_msg = "\n\n".join(parts) + "\n\nFix the violations and output the corrected caption."

    return [
        {"role": "system", "content": _REWRITER_SYSTEM},
        {"role": "user", "content": user_msg},
    ]


# ---------------------------------------------------------------------------
# MODEL LOADERS
# ---------------------------------------------------------------------------


def load_joycaption():
    """Load JoyCaption Beta One."""
    print(f"Loading JoyCaption: {JOYCAPTION_MODEL}", file=sys.stderr)
    processor = AutoProcessor.from_pretrained(JOYCAPTION_MODEL, use_fast=False)
    model = LlavaForConditionalGeneration.from_pretrained(
        JOYCAPTION_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()
    return model, processor


def load_lexi(quant: str | None):
    """Load Lexi-Uncensored-V2."""
    print(f"Loading Lexi: {LEXI_MODEL} (quant={quant})", file=sys.stderr)
    kwargs = {"device_map": "auto"}
    if quant == "8bit":
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
    elif quant == "4bit":
        # Model card warns Q4 has refusal regressions; prefer 8bit if VRAM allows.
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
        )
    else:
        kwargs["torch_dtype"] = torch.bfloat16

    tokenizer = AutoTokenizer.from_pretrained(LEXI_MODEL)
    model = AutoModelForCausalLM.from_pretrained(LEXI_MODEL, **kwargs)
    model.eval()
    return model, tokenizer


# ---------------------------------------------------------------------------
# CSV LOADING + TAG ASSEMBLY
# ---------------------------------------------------------------------------


def load_tag_csv(csv_path: Path) -> dict[str, dict]:
    """Load manual tags CSV. Returns dict mapping filename to row metadata.

    The 'scale' field is stored separately - it's CSV-only metadata used for
    dataset balance auditing, not for caption generation.
    """
    rows = {}
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        with_filename = ["filename"] + [SCALE_COLUMN] + BOOLEAN_TAG_COLUMNS
        missing = [c for c in with_filename if c not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"CSV missing required columns: {missing}. "
                f"Found: {reader.fieldnames}"
            )
        for row in reader:
            filename = row["filename"].strip()
            if not filename:
                continue
            scale = row.get(SCALE_COLUMN, "").strip()
            if scale not in VALID_SCALES:
                print(
                    f"WARNING: {filename} has invalid scale '{scale}'. "
                    f"Valid: {sorted(VALID_SCALES - {''})}",
                    file=sys.stderr,
                )
                scale = ""
            bools = {c: row.get(c, "0").strip() == "1" for c in BOOLEAN_TAG_COLUMNS}
            action = row.get(ACTION_COLUMN, "").strip()
            rows[filename] = {
                "scale": scale,  # CSV-only metadata, not fed to JoyCaption
                "bools": bools,
                "action": action,
                "notes": row.get(NOTES_COLUMN, "").strip(),
            }
    return rows


def assemble_caption_labels(row: dict) -> list[str]:
    """Build the label list passed to JoyCaption.

    Scale is deliberately excluded - it's CSV-only metadata. Only labels
    that should resolve to LABEL_PROMPT directives are included here.
    """
    labels = []
    for col in BOOLEAN_TAG_COLUMNS:
        if row["bools"][col]:
            labels.append(col)
    if row["action"]:
        labels.append(row["action"])
    return labels


def assemble_record_labels(row: dict) -> list[str]:
    """Build the full label list stored in the JSONL record.

    Includes scale (for downstream auditing) and all caption labels.
    """
    labels = []
    if row["scale"]:
        labels.append(row["scale"])
    labels.extend(assemble_caption_labels(row))
    return labels


# ---------------------------------------------------------------------------
# JOYCAPTION INFERENCE
# ---------------------------------------------------------------------------


@torch.inference_mode()
def caption_image(
    model,
    processor,
    image_path: Path,
    caption_labels: list[str],
    notes: str,
    trigger: str = "1xlasm",
) -> str:
    """Run JoyCaption with the trigger directive and label hints applied.

    Note: caption_labels here excludes scale tags. Scale is not fed to
    JoyCaption because it would create contradictions with visible posture.
    """
    image = Image.open(image_path).convert("RGB")

    hint = ""
    for label in caption_labels:
        add = LABEL_PROMPT.get(label)
        if add:
            hint += add
    if notes:
        hint += f" Additional context from human reviewer: {notes}"

    prompt = DEFAULT_PROMPT
    prompt += CONTENT_PROMPT.get(trigger, "")
    if hint:
        prompt += hint
    prompt += POST_PROMPT

    system_content = DEFAULT_SYSTEM + CONTENT_SYSTEM.get(trigger, "")
    convo = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]
    convo_text = processor.apply_chat_template(
        convo, tokenize=False, add_generation_prompt=True,
    )
    inputs = processor(
        text=[convo_text], images=[image], return_tensors="pt",
    ).to(model.device)
    inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)

    output = model.generate(
        **inputs,
        max_new_tokens=512,
        do_sample=True,
        temperature=0.6,
        top_p=0.9,
        suppress_tokens=None,
        use_cache=True,
    )
    generated = output[0][inputs["input_ids"].shape[1]:]
    text = processor.tokenizer.decode(
        generated, skip_special_tokens=True, clean_up_tokenization_spaces=False,
    ).strip()
    return text


# ---------------------------------------------------------------------------
# LEXI REWRITER
# ---------------------------------------------------------------------------


@torch.inference_mode()
def rewrite_caption(
    model,
    tokenizer,
    caption: str,
    violations: list[str],
    body_warnings: list[str],
    missing_triggers: list[str],
    caption_labels: list[str],
    temperature: float = 0.3,
) -> str:
    """Run Lexi to fix a flagged caption. Low temp for deterministic edits."""
    messages = build_rewriter_messages(
        caption, violations, body_warnings, missing_triggers, caption_labels,
    )
    input_ids = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt",
    ).to(model.device)

    output = model.generate(
        input_ids,
        max_new_tokens=300,
        temperature=temperature,
        do_sample=temperature > 0,
        top_p=0.9,
        pad_token_id=tokenizer.eos_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    generated = output[0][input_ids.shape[-1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True).strip()

    for prefix in ("Fixed:", "Corrected:", "Output:", "Caption:"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    return text.strip('"\'')


# ---------------------------------------------------------------------------
# VALIDATION ORCHESTRATION
# ---------------------------------------------------------------------------


def validate(
    caption: str,
    caption_labels: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Run all three validators.

    Returns (forbidden_violations, body_warnings, missing_triggers).
    Note: caption_labels here excludes scale - scale tags are not consulted
    by any validator since they don't appear in captions.
    """
    return (
        caption_has_xlasm_violations(caption),
        validate_body_type_consistency(caption, caption_labels),
        validate_trigger_presence(caption),
    )


def is_clean(
    violations: list[str],
    body_warnings: list[str],
    missing_triggers: list[str],
) -> bool:
    """Caption is clean only when all three validators pass."""
    return not violations and not body_warnings and not missing_triggers


def format_status(
    violations: list[str],
    body_warnings: list[str],
    missing_triggers: list[str],
) -> str:
    """Human-readable status string for the JSONL output."""
    parts = []
    if violations:
        parts.append(f"forbidden={violations}")
    if body_warnings:
        parts.append(f"body={body_warnings}")
    if missing_triggers:
        parts.append(f"missing_triggers={missing_triggers}")
    return "; ".join(parts) if parts else "clean"


# ---------------------------------------------------------------------------
# DATASET BALANCE AUDIT
# ---------------------------------------------------------------------------


def audit_dataset_balance(rows: dict[str, dict]) -> None:
    """Print scale tier distribution and warnings for under-represented tiers.

    Each scale tier should have enough training images to be learned reliably.
    Tiers with fewer than ~50 images may produce weak inference results.
    """
    scale_counts = Counter(r["scale"] or "(unscaled)" for r in rows.values())
    total = len(rows)

    print("\n" + "=" * 60, file=sys.stderr)
    print("DATASET BALANCE AUDIT (scale distribution)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    for scale in list(SCALE_TAGS) + ["(unscaled)"]:
        count = scale_counts.get(scale, 0)
        pct = (count / total * 100) if total > 0 else 0
        bar = "#" * int(pct / 2)
        warning = ""
        if scale != "(unscaled)" and 0 < count < 50:
            warning = "  WARNING: under 50 images, may train weakly"
        elif scale != "(unscaled)" and count == 0:
            warning = "  WARNING: no images, scale tier will not train at all"
        print(f"  {scale:15s} {count:4d} ({pct:5.1f}%) {bar}{warning}", file=sys.stderr)

    print("=" * 60, file=sys.stderr)


# ---------------------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------------------


def process(
    csv_path: Path,
    images_dir: Path,
    output_path: Path,
    write_txt: bool,
    skip_existing: bool,
    lexi_quant: str | None,
    max_rewrite_retries: int,
    skip_rewriter: bool,
):
    rows = load_tag_csv(csv_path)
    print(f"Loaded {len(rows)} tagged rows from {csv_path}", file=sys.stderr)
    print(f"Trigger phrases: '{TRIGGER_WOMAN}' / '{TRIGGER_MAN}'", file=sys.stderr)

    # Audit dataset balance before processing - if scale tiers are badly
    # imbalanced, you may want to fix that before spending hours captioning.
    audit_dataset_balance(rows)

    existing = set()
    if skip_existing and output_path.exists():
        with output_path.open() as f:
            for line in f:
                if line.strip():
                    existing.add(json.loads(line)["image"])
        print(f"Skipping {len(existing)} already-captioned images", file=sys.stderr)

    joy_model, joy_processor = load_joycaption()

    # Lazy-load Lexi only if/when we hit a flagged caption
    lexi_model = None
    lexi_tokenizer = None

    stats = {
        "total": 0,
        "clean_first_try": 0,
        "fixed_by_rewriter": 0,
        "still_flagged_after_rewrite": 0,
        "rewriter_skipped": 0,
        "first_try_forbidden": 0,
        "first_try_body_type": 0,
        "first_try_missing_triggers": 0,
    }

    start = time.time()
    mode = "a" if skip_existing and output_path.exists() else "w"

    with output_path.open(mode) as out:
        for i, (filename, row) in enumerate(rows.items(), 1):
            if filename in existing:
                continue
            image_path = images_dir / filename
            if not image_path.exists():
                print(f"  MISSING: {filename}", file=sys.stderr)
                continue

            # Caption labels exclude scale (CSV-only metadata)
            caption_labels = assemble_caption_labels(row)
            # Record labels include scale (for the JSONL record)
            record_labels = assemble_record_labels(row)
            stats["total"] += 1

            # Stage 1: JoyCaption
            try:
                caption = caption_image(
                    joy_model, joy_processor, image_path, caption_labels, row["notes"],
                )
            except Exception as e:
                print(f"  JOYCAPTION ERROR on {filename}: {e}", file=sys.stderr)
                continue

            violations, body_warnings, missing_triggers = validate(caption, caption_labels)
            original_caption = caption
            status = "ok"
            rewrite_attempts = []

            if violations:
                stats["first_try_forbidden"] += 1
            if body_warnings:
                stats["first_try_body_type"] += 1
            if missing_triggers:
                stats["first_try_missing_triggers"] += 1

            if is_clean(violations, body_warnings, missing_triggers):
                stats["clean_first_try"] += 1
            elif skip_rewriter:
                status = f"flagged: {format_status(violations, body_warnings, missing_triggers)}"
                stats["rewriter_skipped"] += 1
            else:
                # Stage 2: Lexi rewriter fallback
                if lexi_model is None:
                    lexi_model, lexi_tokenizer = load_lexi(lexi_quant)

                for attempt in range(max_rewrite_retries + 1):
                    temp = 0.3 + (attempt * 0.15)
                    try:
                        rewritten = rewrite_caption(
                            lexi_model, lexi_tokenizer,
                            caption, violations, body_warnings, missing_triggers,
                            caption_labels, temperature=temp,
                        )
                    except Exception as e:
                        print(f"  REWRITER ERROR on {filename}: {e}", file=sys.stderr)
                        break

                    new_v, new_b, new_t = validate(rewritten, caption_labels)
                    rewrite_attempts.append({
                        "attempt": attempt,
                        "temperature": temp,
                        "caption": rewritten,
                        "violations": new_v,
                        "body_warnings": new_b,
                        "missing_triggers": new_t,
                    })
                    if is_clean(new_v, new_b, new_t):
                        caption = rewritten
                        violations, body_warnings, missing_triggers = new_v, new_b, new_t
                        stats["fixed_by_rewriter"] += 1
                        status = "ok (rewritten)"
                        break
                else:
                    if rewrite_attempts:
                        last = rewrite_attempts[-1]
                        caption = last["caption"]
                        violations = last["violations"]
                        body_warnings = last["body_warnings"]
                        missing_triggers = last["missing_triggers"]
                    status = (
                        f"flagged after rewrite: "
                        f"{format_status(violations, body_warnings, missing_triggers)}"
                    )
                    stats["still_flagged_after_rewrite"] += 1

            # Record includes scale in labels (for downstream auditing) but
            # the caption itself was generated without scale guidance
            record = {
                "image": filename,
                "scale": row["scale"],  # explicit field for easy auditing
                "labels": record_labels,
                "caption_labels": caption_labels,  # what was actually fed to JoyCaption
                "notes": row["notes"],
                "caption": caption,
                "status": status,
            }
            if rewrite_attempts:
                record["original_caption"] = original_caption
                record["rewrite_attempts"] = rewrite_attempts
            out.write(json.dumps(record) + "\n")
            out.flush()

            if write_txt and status.startswith("ok"):
                txt_path = images_dir / (image_path.stem + ".txt")
                txt_path.write_text(caption + "\n")

            elapsed = time.time() - start
            rate = stats["total"] / elapsed if elapsed > 0 else 0
            remaining = len(rows) - i
            eta = remaining / rate if rate > 0 else 0
            print(
                f"[{i}/{len(rows)}] {filename:30s} {status[:50]:50s} "
                f"({rate:.2f}/s, ETA {eta/60:.1f}min)",
                file=sys.stderr,
            )

    # Final stats
    print("\n" + "=" * 60, file=sys.stderr)
    print("PIPELINE STATS", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    for key, val in stats.items():
        print(f"  {key:35s} {val}", file=sys.stderr)
    if stats["total"] > 0:
        clean_rate = stats["clean_first_try"] / stats["total"] * 100
        flagged_first = stats["total"] - stats["clean_first_try"]
        rescue_rate = (
            stats["fixed_by_rewriter"] / flagged_first * 100
            if flagged_first > 0 else 0
        )
        print(
            f"\n  Clean first-try rate: {clean_rate:.1f}%",
            file=sys.stderr,
        )
        print(
            f"  Rewriter rescue rate: {rescue_rate:.1f}% "
            f"(of flagged captions)",
            file=sys.stderr,
        )
        print("\n  First-pass failure breakdown (a single caption can fail multiple validators):", file=sys.stderr)
        print(f"    forbidden vocabulary: {stats['first_try_forbidden']}", file=sys.stderr)
        print(f"    body-type violations: {stats['first_try_body_type']}", file=sys.stderr)
        print(f"    missing triggers:     {stats['first_try_missing_triggers']}", file=sys.stderr)
    print(f"\nOutput: {output_path}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, required=True, help="Manual tags CSV")
    p.add_argument("--images", type=Path, required=True, help="Image directory")
    p.add_argument("--output", type=Path, required=True, help="Output JSONL")
    p.add_argument(
        "--write-txt", action="store_true",
        help="Write companion .txt files next to images (kohya/musubi format). "
             "Only written for captions with 'ok' status.",
    )
    p.add_argument(
        "--skip-existing", action="store_true",
        help="Resume - skip images already in the output JSONL",
    )
    p.add_argument(
        "--lexi-quant", choices=["none", "8bit", "4bit"], default="none",
        help="Quantization for Lexi rewriter (bf16 default)",
    )
    p.add_argument(
        "--rewrite-retries", type=int, default=2,
        help="Number of rewrite attempts before giving up on a caption",
    )
    p.add_argument(
        "--skip-rewriter", action="store_true",
        help="Skip the Lexi rewriter stage entirely - just flag bad captions",
    )
    args = p.parse_args()

    quant = None if args.lexi_quant == "none" else args.lexi_quant
    process(
        args.csv,
        args.images,
        args.output,
        args.write_txt,
        args.skip_existing,
        quant,
        args.rewrite_retries,
        args.skip_rewriter,
    )


if __name__ == "__main__":
    main()
