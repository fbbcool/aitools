#!/usr/bin/env python
"""Build a YOLO detection dataset from the scene-DB penis annotations.

Sources the `claude_penis_masks` collection (populated by the annotator tab):

  * status='accepted'       -> POSITIVE: source 0rig image + on-disk mask
                               (<root>/___mask/penis/...) -> one merged bbox.
  * status='skipped_absent' -> NEGATIVE / background: image + EMPTY label file.
                               These explicit "no penis" images cut false
                               positives (e.g. fingers mistaken for anatomy).
  * status='skipped_hard'   -> excluded (neither clean positive nor negative).

Images are symlinked to their 0rig originals (native resolution, matching the
masks), so no pixels are copied. Positives/negatives are split independently
(stratified) so both train and val carry each class.

Output: $WORKSPACE/penis_yolo_scenedb/{images,labels}/{train,val} + data.yaml
"""

from __future__ import annotations

import os
import random
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from aidb import SceneManager

MIN_COMP = 20
VAL_FRAC = 0.15
SEED = 1337
WORKSPACE = Path(os.environ.get('WORKSPACE', str(Path.home() / 'Workspace')))
OUT = WORKSPACE / 'penis_yolo_scenedb'


def merged_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    lab, n = ndimage.label(mask)
    keep = np.zeros_like(mask, dtype=bool)
    for i in range(1, n + 1):
        comp = lab == i
        if comp.sum() >= MIN_COMP:
            keep |= comp
    if not keep.any():
        keep = mask
    ys, xs = np.where(keep)
    if len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def main() -> None:
    cfg = os.environ.get('AIDB_SCENE_CONFIG', 'default')
    scm = SceneManager(config=cfg, verbose=0)
    sim = scm.scene_image_manager()
    root = Path(sim.root)
    col = scm._dbc._get_collection('claude_penis_masks')

    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ('images/train', 'images/val', 'labels/train', 'labels/val'):
        (OUT / sub).mkdir(parents=True, exist_ok=True)

    pos = list(col.find({'status': 'accepted'}))
    neg = list(col.find({'status': 'skipped_absent'}))
    rng = random.Random(SEED)
    rng.shuffle(pos)
    rng.shuffle(neg)

    def split(items):
        k = round(len(items) * VAL_FRAC)
        return set(id(x) for x in items[:k])  # val ids

    val_pos = split(pos)
    val_neg = split(neg)

    n_pos = n_neg = n_bad = 0

    def link_image(image_id: str, split_dir: str) -> Path | None:
        simg = sim.img_from_id(image_id)
        if simg is None:
            return None
        src = simg.url_from_data
        if src is None or not Path(src).exists():
            return None
        dst = OUT / 'images' / split_dir / f'{image_id}.png'
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.symlink_to(Path(src))
        return dst

    # positives
    for d in pos:
        iid = d['image_id']
        mf = d.get('mask_file')
        if not mf or not (root / mf).exists():
            n_bad += 1
            continue
        mask = np.asarray(Image.open(root / mf)) > 127
        if mask.sum() == 0:
            n_bad += 1
            continue
        box = merged_bbox(mask)
        if box is None:
            n_bad += 1
            continue
        H, W = mask.shape
        x1, y1, x2, y2 = box
        xc, yc = (x1 + x2) / 2 / W, (y1 + y2) / 2 / H
        bw, bh = (x2 - x1 + 1) / W, (y2 - y1 + 1) / H
        split_dir = 'val' if id(d) in val_pos else 'train'
        if link_image(iid, split_dir) is None:
            n_bad += 1
            continue
        (OUT / 'labels' / split_dir / f'{iid}.txt').write_text(
            f'0 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n'
        )
        n_pos += 1

    # negatives (background: empty label file)
    for d in neg:
        iid = d['image_id']
        split_dir = 'val' if id(d) in val_neg else 'train'
        if link_image(iid, split_dir) is None:
            n_bad += 1
            continue
        (OUT / 'labels' / split_dir / f'{iid}.txt').write_text('')
        n_neg += 1

    (OUT / 'data.yaml').write_text(
        f'path: {OUT}\ntrain: images/train\nval: images/val\nnames:\n  0: penis\n'
    )
    nt = len(list((OUT / 'images/train').glob('*.png')))
    nv = len(list((OUT / 'images/val').glob('*.png')))
    print(f'[done] positives={n_pos}  negatives={n_neg}  skipped_bad={n_bad}')
    print(f'[done] train={nt}  val={nv}  ({100 * n_neg / max(1, n_pos + n_neg):.0f}% background)')
    print(f'[done] data.yaml at {OUT / "data.yaml"}')


if __name__ == '__main__':
    main()
