"""JoyCaption HINT-LoRA training entrypoint — v4 on grown dataset.

v1 (rank 16, 4 ep) hit ~0.22 jaccard but under-fit (loss 0.76).
v2 (rank 32, 8 ep) memorized (loss 0.04, jaccard 1.00 on train set).
v3 (rank 32, 8 ep, 100 train / 15 val) — 0.39 held-out jaccard. Same
hyperparams as v2 but with proper val split. Used as production hint
adapter through 2026-05-12.

v4 — same architecture as v3, retrained on the grown dataset (204 eligible
pairs vs v3's 119). 174 train / 30 val for a more stable jaccard
measurement. If v4 jaccard ≥ 0.50 we approach the target; if it
plateaus near v3 the limit is vision-side, not the LM adapter.

GPU prerequisite: ≥20 GiB free (~15 min wall-clock at this config).
Requires reachability to prod Mongo and the image filesystem.
"""
import json
import os
import random
from pathlib import Path

from ait.caption.joy_train_hint import list_eligible_pairs, train_hint


SET_NAME = 'gts_v3'
CONFIG = 'prod'
SKIN_NAME = '1xlasm'

OUTPUT_DIR = Path(os.environ['WORKSPACE']) / 'joy_hint_lora_gts_v3_v4'

# Hyperparams — kept identical to v3 so the train-loss / held-out delta
# attributable to dataset size is clean. Same rank, alpha, epochs, LR.
EPOCHS = 8
LEARNING_RATE = 1e-4
LORA_R = 32
LORA_ALPHA = 64
LORA_DROPOUT = 0.05
GRAD_ACCUM = 8
MAX_LENGTH = 4096
MIN_HINT_CHARS = 10
SEED = 42

# Train/val split — deterministic via seed. Bumped val from 15 to 30
# for a more stable jaccard estimate on the larger dataset.
VAL_COUNT = 30
SPLIT_SEED = 42


if __name__ == '__main__':
    # Build the full eligible-pair list, then split.
    pairs = list_eligible_pairs(
        set_name=SET_NAME, config=CONFIG, min_hint_chars=MIN_HINT_CHARS, verbose=1,
    )
    print(f'[prepare] total eligible pairs: {len(pairs)}')

    rng = random.Random(SPLIT_SEED)
    pairs_shuffled = list(pairs)
    rng.shuffle(pairs_shuffled)
    val_pairs = pairs_shuffled[:VAL_COUNT]
    train_pairs = pairs_shuffled[VAL_COUNT:]
    train_ids = [p['id'] for p in train_pairs]
    val_ids = [p['id'] for p in val_pairs]

    print(f'[prepare] split: {len(train_pairs)} train / {len(val_pairs)} val '
          f'(seed={SPLIT_SEED})')

    # Persist val IDs + their ground-truth hints so the smoke test can use them
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    val_path = OUTPUT_DIR / 'val_pairs.json'
    val_path.write_text(json.dumps(val_pairs, indent=2))
    print(f'[prepare] wrote {val_path}')

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
        train_ids=train_ids,
        seed=SEED,
    )
