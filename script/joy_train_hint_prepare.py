"""JoyCaption HINT-LoRA training entrypoint.

Companion to `joy_train_prepare.py` — trains a focused LoRA on the
HINT generation task (curator-style terse hints), separate from the
full-caption LoRA. Output adapter is intended to be loaded at iter-5
of `/suggest_image` to close the hint-jaccard gap (current 0.10 → target ≥0.50).

Edit the values below and run:

    python script/joy_train_hint_prepare.py

GPU prerequisite: ≥20 GiB free (model loads in bf16 + gradient
checkpointing; ~2-4 hours runtime for 4-6 epochs on 117 pairs).

Requires reachability to prod Mongo and the image filesystem.
"""
import os
from pathlib import Path

from ait.caption.joy_train_hint import train_hint


SET_NAME = 'gts_v3'
CONFIG = 'prod'
SKIN_NAME = '1xlasm'

OUTPUT_DIR = Path(os.environ['WORKSPACE']) / 'joy_hint_lora_gts_v3'

# Hyperparams — start with the same shape as the existing
# `joy_train_prepare.py` defaults; tune after the first run if needed.
EPOCHS = 4               # 117 pairs × 4 ≈ 468 samples; ~60 grad updates at accum=8
LEARNING_RATE = 1e-4
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
GRAD_ACCUM = 8
MAX_LENGTH = 4096
MIN_HINT_CHARS = 10      # filter out very-short fragments
SEED = 42


if __name__ == '__main__':
    train_hint(
        set_name=SET_NAME,
        config=CONFIG,
        skin_name=SKIN_NAME,
        output_dir=OUTPUT_DIR,
        epochs=EPOCHS,
        learning_rate=LEARNING_RATE,
        lora_r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        grad_accum=GRAD_ACCUM,
        max_length=MAX_LENGTH,
        min_hint_chars=MIN_HINT_CHARS,
        seed=SEED,
    )
