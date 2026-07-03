#!/usr/bin/env python
"""YOLO -> SAM2 auto-masker: the trained detector proposes a box, SAM2 refines
it into a pixel mask. This is the automated replacement for the NudeNet stage
that failed on the gts domain.

Usage:
    python script/penis_yolo_detect.py <image.png> [<image2.png> ...]
    python script/penis_yolo_detect.py --dir <folder>
Outputs (per input) to $WORKSPACE/penis_yolo/detect_out/:
    <stem>.overlay.png   box (green) + mask (red) drawn on the image
    <stem>.mask.png      binary mask (white = penis)  [only if a box is found]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from transformers import Sam2Model, Sam2Processor
from ultralytics import YOLO

WORKSPACE = Path(os.environ.get('WORKSPACE', str(Path.home() / 'Workspace')))
# Prefer the scene-DB detector (465 pos + 339 neg); fall back to gts-v3 (127).
_WEIGHT_CANDIDATES = [
    WORKSPACE / 'penis_yolo_scenedb' / 'runs' / 'penis_det_scenedb' / 'weights' / 'best.pt',
    WORKSPACE / 'penis_yolo' / 'runs' / 'penis_det_s' / 'weights' / 'best.pt',
]
WEIGHTS = Path(os.environ['PENIS_YOLO_WEIGHTS']) if os.environ.get('PENIS_YOLO_WEIGHTS') else \
    next((p for p in _WEIGHT_CANDIDATES if p.exists()), _WEIGHT_CANDIDATES[0])
OUT = WORKSPACE / 'penis_yolo' / 'detect_out'
SAM_ID = 'facebook/sam2.1-hiera-base-plus'
CONF = float(os.environ.get('YOLO_CONF', '0.25'))
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'


def sam_mask(proc, model, img: Image.Image, box: list[float]) -> np.ndarray:
    inputs = proc(images=img, input_boxes=[[box]], return_tensors='pt').to(DEVICE)
    with torch.no_grad():
        out = model(**inputs, multimask_output=False)
    m = proc.post_process_masks(out.pred_masks, inputs['original_sizes'])[0]
    return m[0, 0].cpu().numpy().astype(bool)


def main(paths: list[Path]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    yolo = YOLO(str(WEIGHTS))
    proc = Sam2Processor.from_pretrained(SAM_ID)
    sam = Sam2Model.from_pretrained(SAM_ID).to(DEVICE).eval()

    for p in paths:
        img = Image.open(p).convert('RGB')
        res = yolo.predict(source=str(p), conf=CONF, imgsz=1024, verbose=False)[0]
        boxes = res.boxes.xyxy.cpu().numpy() if res.boxes is not None else np.empty((0, 4))
        confs = res.boxes.conf.cpu().numpy() if res.boxes is not None else np.empty((0,))
        ov = img.copy()
        d = ImageDraw.Draw(ov, 'RGBA')
        union = np.zeros((img.height, img.width), dtype=bool)
        for b, c in zip(boxes, confs, strict=True):
            box = [float(v) for v in b]
            mask = sam_mask(proc, sam, img, box)
            union |= mask
            d.rectangle(box, outline=(0, 255, 0, 255), width=4)
            d.text((box[0], max(0, box[1] - 12)), f'{c:.2f}', fill=(0, 255, 0, 255))
        if union.any():
            red = np.zeros((*union.shape, 4), dtype=np.uint8)
            red[union] = (255, 0, 0, 110)
            ov = Image.alpha_composite(ov.convert('RGBA'), Image.fromarray(red)).convert('RGB')
            Image.fromarray((union.astype(np.uint8) * 255), 'L').save(OUT / f'{p.stem}.mask.png')
        ov.save(OUT / f'{p.stem}.overlay.png')
        cov = union.mean() * 100
        print(f'{p.name}: {len(boxes)} box(es) conf={[round(float(c),2) for c in confs]}  mask_cov={cov:.2f}%')
    print(f'[done] outputs in {OUT}')


if __name__ == '__main__':
    args = sys.argv[1:]
    if args and args[0] == '--dir':
        folder = Path(args[1])
        paths = sorted(p for p in folder.glob('*') if p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'})
    else:
        paths = [Path(a) for a in args]
    if not paths:
        print('usage: penis_yolo_detect.py <image ...> | --dir <folder>')
        sys.exit(1)
    main(paths)
