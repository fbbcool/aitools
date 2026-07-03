#!/usr/bin/env python
"""Build a YOLO detection dataset from the hand-annotated penis masks.

The 127 accepted masks in ``$WORKSPACE/gts_v3_penis_masks/`` give exact ground
truth. Each mask -> a single merged bounding box (specks < MIN_COMP px dropped,
box taken over all remaining foreground so glans/shaft fragments become ONE
object, not several). Source images are pulled from the gts-v3 cache/hub.

Output (YOLO-detect layout):
    $WORKSPACE/penis_yolo/
        images/{train,val}/train___<id>.png
        labels/{train,val}/train___<id>.txt   # "0 xc yc w h" normalised
        data.yaml

The trained detector is meant to feed SAM2 as a box proposer (replacing the
NudeNet stage that failed on this domain), not to produce final masks itself.
"""

from __future__ import annotations

import glob
import os
import random
import shutil
from pathlib import Path

import numpy as np
from huggingface_hub import hf_hub_download, try_to_load_from_cache
from PIL import Image
from scipy import ndimage

DATASET = 'fbbcool/gts-v3'
SNAPSHOT = 'train'
HF_TOKEN = os.environ.get('HF_TOKEN_RW') or os.environ.get('HF_TOKEN')

WORKSPACE = Path(os.environ.get('WORKSPACE', str(Path.home() / 'Workspace')))
MASK_DIR = WORKSPACE / 'gts_v3_penis_masks'
OUT = WORKSPACE / 'penis_yolo'

MIN_COMP = 20  # drop connected components smaller than this many px (specks)
VAL_FRAC = 0.15
SEED = 1337


def resolve_src(fn: str) -> Path:
    rel = f'{SNAPSHOT}/images/{fn}'
    cached = try_to_load_from_cache(DATASET, rel, repo_type='dataset')
    if isinstance(cached, str) and Path(cached).exists():
        return Path(cached)
    return Path(hf_hub_download(DATASET, rel, repo_type='dataset', token=HF_TOKEN))


def merged_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Single bbox over all foreground, after dropping tiny speck components."""
    lab, n = ndimage.label(mask)
    keep = np.zeros_like(mask, dtype=bool)
    for i in range(1, n + 1):
        comp = lab == i
        if comp.sum() >= MIN_COMP:
            keep |= comp
    if not keep.any():
        keep = mask  # nothing survived the filter; fall back to raw mask
    ys, xs = np.where(keep)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ('images/train', 'images/val', 'labels/train', 'labels/val'):
        (OUT / sub).mkdir(parents=True, exist_ok=True)

    masks = sorted(glob.glob(str(MASK_DIR / 'train___*.png')))
    rng = random.Random(SEED)
    rng.shuffle(masks)
    n_val = round(len(masks) * VAL_FRAC)
    val_set = set(masks[:n_val])

    n_ok = 0
    for mp in masks:
        fn = Path(mp).name
        a = np.asarray(Image.open(mp)) > 127
        if a.sum() == 0:
            print(f'[skip] empty mask {fn}')
            continue
        H, W = a.shape
        x1, y1, x2, y2 = merged_bbox(a)
        xc = (x1 + x2) / 2 / W
        yc = (y1 + y2) / 2 / H
        bw = (x2 - x1 + 1) / W
        bh = (y2 - y1 + 1) / H

        split = 'val' if mp in val_set else 'train'
        img = Image.open(resolve_src(fn)).convert('RGB')
        img.save(OUT / 'images' / split / fn)
        (OUT / 'labels' / split / fn.replace('.png', '.txt')).write_text(
            f'0 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n'
        )
        n_ok += 1

    yaml = (
        f'path: {OUT}\n'
        'train: images/train\n'
        'val: images/val\n'
        'names:\n'
        '  0: penis\n'
    )
    (OUT / 'data.yaml').write_text(yaml)
    n_train = len(list((OUT / 'images/train').glob('*.png')))
    n_valc = len(list((OUT / 'images/val').glob('*.png')))
    print(f'[done] {n_ok} labelled  ->  train={n_train}  val={n_valc}')
    print(f'[done] data.yaml at {OUT / "data.yaml"}')


if __name__ == '__main__':
    main()
