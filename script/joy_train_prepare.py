"""
JoyCaption LoRA training entrypoint.

Edit the values below and run:

    python script/joy_train_prepare.py

Requires reachability to prod Mongo and the image filesystem (since the
dataset is built directly from `SceneSetManager` / `SceneImageManager`).

Training data shape: each row is ((image, caption_prompt) → caption).
The `caption_prompt` is the curator-finalized stored prompt (built by
`/imgs_caption_prompt` for curated images, or `/imgs_update_caption_prompt`
for legacy ones). Training on the same prompt distribution `/imgs_caption_joy`
forwards at inference avoids train/inference mismatch.
"""

import os
from pathlib import Path

from ait.caption.joy_train import train


SET_NAME = 'gts_v3'
CONFIG = 'prod'
SKIN = '1xlasm'

# Versioned output dir — the legacy LoRA at $WORKSPACE/joy_lora_gts_v3 is
# preserved for performance comparison. After validation, the curator can
# either repoint AInstallerDB to this new path or rename.
OUTPUT_DIR = Path(os.environ['WORKSPACE']) / 'joy_lora_gts_v3_jp'

EPOCHS = 6
LEARNING_RATE = 1e-4
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
GRAD_ACCUM = 8
MAX_LENGTH = 4096
SEED = 42


if __name__ == '__main__':
    train(
        set_name=SET_NAME,
        config=CONFIG,
        skin_name=SKIN,
        output_dir=OUTPUT_DIR,
        epochs=EPOCHS,
        learning_rate=LEARNING_RATE,
        lora_r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        grad_accum=GRAD_ACCUM,
        max_length=MAX_LENGTH,
        seed=SEED,
    )
