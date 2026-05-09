"""
JoyCaption LoRA training entrypoint.

Edit the values below and run:

    python script/joy_train_prepare.py

Requires reachability to prod Mongo and the image filesystem (since the
dataset is built directly from `SceneSetManager` / `SceneImageManager`).
"""

from pathlib import Path

from ait.caption.joy_train import train


SET_NAME = 'gts_v3'
CONFIG = 'prod'
TRIGGER = '1xlasm'

OUTPUT_DIR = Path('/workspace/joy_lora_gts_v3')

EPOCHS = 4
LEARNING_RATE = 1e-4
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
GRAD_ACCUM = 8
MAX_LENGTH = 1024
SEED = 42


if __name__ == '__main__':
    train(
        set_name=SET_NAME,
        config=CONFIG,
        trigger=TRIGGER,
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
