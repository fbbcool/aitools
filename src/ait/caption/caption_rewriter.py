"""
Caption rewriter using Llama-3.1-8B-Lexi-Uncensored-V2.

Reads raw captions (e.g. from JoyCaption) from a JSONL file, rewrites each one
against a strict template using a local uncensored LLM, and writes results to
a new JSONL file.

Input JSONL format (one object per line):
    {"image": "path/to/img1.png", "caption": "raw JoyCaption output..."}

Output JSONL format:
    {"image": "path/to/img1.png", "caption": "raw...", "rewritten": "templated..."}

Usage:
    python caption_rewriter.py --input raw.jsonl --output rewritten.jsonl
    python caption_rewriter.py --input raw.jsonl --output rewritten.jsonl --quant 8bit
"""

import argparse
import json
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


MODEL_ID = "Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2"


# ---------------------------------------------------------------------------
# CONFIGURE YOUR REWRITER HERE
# ---------------------------------------------------------------------------

TRIGGERS = {
    "height": "g14ntss",
    "build": "mscld",
}

# Template that every rewritten caption must follow.
# Edit field order, vocabulary, and structure to match what your image LoRA needs.
TEMPLATE_DESCRIPTION = """\
[trigger_height] [trigger_build] woman, [height_ratio_phrase], [man_position_phrase], \
[woman_pose_or_action], [muscle_features_visible], [woman_clothing], [man_clothing], \
[environment], [lighting], [camera_angle]
"""

# Vocabulary rules - the model will follow these consistently across the dataset.
VOCABULARY_RULES = """\
- Always start with the trigger words: "g14ntss mscld woman"
- For height ratios, use ONLY these phrasings:
    * 2:1 ratio  -> "approximately twice the man's height"
    * 3:1 ratio  -> "approximately three times the man's height"
    * 4:1 ratio  -> "approximately four times the man's height"
    * unclear    -> "significantly taller than the man"
- For the man's position relative to her body, use body-part references:
    "his head reaches her hip", "his head reaches her shoulder", \
"his head reaches her thigh", "his head reaches her waist", etc.
- For muscle features, list visible ones: "defined biceps", "visible quadriceps", \
"lat spread", "vascularity on arms", "developed deltoids", "calf definition"
- Describe the man as "normal-sized man" or "average-build man" - never use diminutives
- Use sentence-case, comma-separated phrases, no period at the end
- Keep total length under 60 words
"""

# Few-shot examples teach the model the exact transformation pattern.
# Replace these with 5-10 of YOUR ideal hand-written examples for best results.
FEW_SHOT_EXAMPLES = [
    {
        "raw": (
            "A very tall muscular woman stands in a modern kitchen next to a "
            "much shorter man. She has visible arm muscles and is wearing a "
            "sports bra and shorts. The man wears a button-up shirt and looks "
            "up at her. Bright daylight comes through the window."
        ),
        "rewritten": (
            "g14ntss mscld woman, approximately twice the man's height, his head "
            "reaches her hip, standing upright facing the camera, defined biceps "
            "and developed deltoids, black sports bra and shorts, blue button-up "
            "shirt and slacks, modern kitchen with marble countertops, bright "
            "natural daylight, eye-level shot from the man's perspective"
        ),
    },
    {
        "raw": (
            "An enormous bodybuilder female towers over a regular guy on a city "
            "sidewalk. Her quads and calves are huge. She's in a tank top. He's "
            "in a suit and looks shocked. It's a sunny day."
        ),
        "rewritten": (
            "g14ntss mscld woman, approximately three times the man's height, "
            "his head reaches her thigh, standing on sidewalk facing forward, "
            "massive quadriceps and calf definition, white tank top and athletic "
            "leggings, gray business suit, urban street with shopfronts, bright "
            "sunny daylight, low-angle shot looking up"
        ),
    },
]

# ---------------------------------------------------------------------------


SYSTEM_PROMPT = f"""You are a caption rewriting assistant for a text-to-image LoRA training dataset. Your job is to take raw image captions and rewrite them to follow a strict template with consistent vocabulary.

TEMPLATE:
{TEMPLATE_DESCRIPTION}

VOCABULARY RULES:
{VOCABULARY_RULES}

CRITICAL INSTRUCTIONS:
- Output ONLY the rewritten caption. No preamble, no explanation, no quotes.
- If the raw caption lacks information for a field, infer it from context or omit that field gracefully.
- Never invent details that contradict the raw caption.
- Always include both trigger words at the start.
- Be consistent across captions - identical concepts get identical phrasing.
"""


def build_messages(raw_caption: str) -> list[dict]:
    """Build the chat-format message list with few-shot examples."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for ex in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": f"Raw caption:\n{ex['raw']}"})
        messages.append({"role": "assistant", "content": ex["rewritten"]})
    messages.append({"role": "user", "content": f"Raw caption:\n{raw_caption}"})
    return messages


def load_model(quant: str | None):
    """Load Lexi-Uncensored-V2 in bf16 (default) or 8-bit/4-bit."""
    print(f"Loading {MODEL_ID}...", file=sys.stderr)

    kwargs = {"device_map": "auto"}
    if quant == "8bit":
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
    elif quant == "4bit":
        # Note: model card warns Q4 has occasional refusal issues. Prefer 8bit.
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
        )
    else:
        kwargs["torch_dtype"] = torch.bfloat16

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, **kwargs)
    model.eval()
    return model, tokenizer


@torch.inference_mode()
def rewrite_caption(
    model,
    tokenizer,
    raw_caption: str,
    max_new_tokens: int = 200,
    temperature: float = 0.3,
) -> str:
    """Rewrite a single caption. Low temperature for consistency."""
    messages = build_messages(raw_caption)
    input_ids = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
    ).to(model.device)

    output = model.generate(
        input_ids,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        do_sample=temperature > 0,
        top_p=0.9,
        pad_token_id=tokenizer.eos_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )

    # Extract only the newly generated tokens
    generated = output[0][input_ids.shape[-1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True).strip()

    # Clean up common artifacts: leading "Rewritten:", quotes, etc.
    for prefix in ("Rewritten:", "Output:", "Caption:"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    text = text.strip('"\'')
    return text


def validate_rewrite(rewritten: str) -> tuple[bool, str]:
    """Quick sanity checks. Returns (is_valid, reason)."""
    if not rewritten:
        return False, "empty output"
    if TRIGGERS["height"] not in rewritten:
        return False, f"missing height trigger '{TRIGGERS['height']}'"
    if TRIGGERS["build"] not in rewritten:
        return False, f"missing build trigger '{TRIGGERS['build']}'"
    word_count = len(rewritten.split())
    if word_count > 100:
        return False, f"too long ({word_count} words)"
    if word_count < 10:
        return False, f"too short ({word_count} words)"
    return True, "ok"


def process_file(
    input_path: Path,
    output_path: Path,
    quant: str | None,
    max_retries: int = 2,
):
    """Process a JSONL file of raw captions."""
    model, tokenizer = load_model(quant)

    with input_path.open() as f:
        records = [json.loads(line) for line in f if line.strip()]

    print(f"Rewriting {len(records)} captions...", file=sys.stderr)
    start = time.time()

    with output_path.open("w") as out:
        for i, rec in enumerate(records, 1):
            raw = rec.get("caption", "")
            if not raw:
                rec["rewritten"] = ""
                rec["status"] = "skipped: no input caption"
                out.write(json.dumps(rec) + "\n")
                continue

            # Try with low temp first; bump it on retry if validation fails
            attempts = []
            for retry in range(max_retries + 1):
                temp = 0.3 + (retry * 0.2)
                rewritten = rewrite_caption(model, tokenizer, raw, temperature=temp)
                ok, reason = validate_rewrite(rewritten)
                attempts.append((rewritten, ok, reason))
                if ok:
                    break

            best, ok, reason = attempts[-1]
            rec["rewritten"] = best
            rec["status"] = "ok" if ok else f"flagged: {reason}"
            out.write(json.dumps(rec) + "\n")
            out.flush()

            elapsed = time.time() - start
            rate = i / elapsed
            eta = (len(records) - i) / rate if rate > 0 else 0
            print(
                f"[{i}/{len(records)}] {rec['status']:30s} "
                f"({rate:.2f}/s, ETA {eta:.0f}s)",
                file=sys.stderr,
            )

    print(f"\nDone. Output: {output_path}", file=sys.stderr)
    flagged = sum(1 for r in records if r.get("status", "").startswith("flagged"))
    if flagged:
        print(
            f"WARNING: {flagged}/{len(records)} captions flagged - review them.",
            file=sys.stderr,
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True, help="Input JSONL")
    p.add_argument("--output", type=Path, required=True, help="Output JSONL")
    p.add_argument(
        "--quant",
        choices=["none", "8bit", "4bit"],
        default="none",
        help="Quantization. bf16 (none) recommended; 8bit if VRAM-limited.",
    )
    p.add_argument("--retries", type=int, default=2, help="Retries on validation fail")
    args = p.parse_args()

    quant = None if args.quant == "none" else args.quant
    process_file(args.input, args.output, quant, args.retries)


if __name__ == "__main__":
    main()
