#!/usr/bin/env python
"""Fine-tune a YOLO detector on the penis-mask dataset (box proposer for SAM2).

Small dataset (127) + small objects (median box ~0.5% of image) -> the recipe
leans on a COCO-pretrained backbone, high input resolution, and aggressive
augmentation (copy-paste + mosaic + scale jitter) to squeeze generalisation out
of few examples. The detector only needs to be roughly right; SAM2 refines the
box into a pixel mask downstream.
"""

from __future__ import annotations

import os
from pathlib import Path

from ultralytics import YOLO

WORKSPACE = Path(os.environ.get('WORKSPACE', str(Path.home() / 'Workspace')))
# Override via env to target the scene-DB dataset:
#   PENIS_YOLO_DATA=$WORKSPACE/penis_yolo_scenedb/data.yaml
#   PENIS_YOLO_RUN=penis_det_scenedb
DATA = Path(os.environ.get('PENIS_YOLO_DATA', str(WORKSPACE / 'penis_yolo' / 'data.yaml')))
RUN_NAME = os.environ.get('PENIS_YOLO_RUN', 'penis_det_s')
PROJECT = DATA.parent / 'runs'


def main() -> None:
    model = YOLO('yolo11s.pt')  # COCO-pretrained detect
    model.train(
        data=str(DATA),
        epochs=200,
        patience=40,
        imgsz=1024,          # small objects need resolution
        batch=16,
        project=str(PROJECT),
        name=RUN_NAME,
        exist_ok=True,
        # augmentation tuned for few-shot small-object
        mosaic=1.0,
        close_mosaic=20,     # disable mosaic for the last 20 epochs
        copy_paste=0.5,      # strong help for small objects
        scale=0.5,
        fliplr=0.5,
        flipud=0.0,          # anatomy has a vertical prior; no vertical flip
        degrees=5.0,
        translate=0.1,
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.4,
        # single class: cls loss weight can stay default; box matters most
        box=7.5,
        seed=1337,
        deterministic=True,
        plots=True,
    )
    print(f'[done] best weights: {PROJECT / RUN_NAME / "weights" / "best.pt"}')


if __name__ == '__main__':
    main()
