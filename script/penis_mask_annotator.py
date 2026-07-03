#!/usr/bin/env python
"""SAM2-powered manual penis-mask annotator for the gts-v3 recovery pool.

Persistent rebuild of the tool that was previously living in /tmp (and got
wiped on reboot). It exists to hand-segment the 139 images that the automated
NudeNet -> SAM2 batch could NOT mask cleanly:

    81 NudeNet misses  (no genitalia box at all)
  + 58 FP-rejected     (NudeNet boxed something, curator rejected the mask)
  = 139 recovery pool

The 33 confirmed true-positive masks from the batch already live on the hub at
``fbbcool/gts-v3 -> train/masks/penis/`` and are NOT re-reviewed here.

Workflow per image:
  * left-click            -> add an INCLUDE point   (green)
  * hold Shift + click    -> add an EXCLUDE point    (red)   (radio also toggles)
  * click-and-drag        -> define a bbox neighbourhood hint
  * mouse wheel           -> zoom at cursor (both panes synced)
  * SAM2 runs on every edit, picks the best of 3 candidate masks via
    pos_cov - 2.5*neg_cov + 0.1*iou so exclude points actually bite.
  * accept / skip-absent / too-hard  -> writes a JSON sidecar (always) plus a
    binary mask PNG (accept only), then advances to the next pending image.

Every terminal decision persists the curator's points + bbox + status, because
that hand annotation is itself valuable (downstream NudeNet finetune / routing).

Outputs (persistent, survive reboot):
    $WORKSPACE/gts_v3_penis_masks/
        train___<id>.png          accepted binary masks (white = penis)
        train___<id>.png.anno.json sidecar for every terminal decision
        _recovery_state.json      {reviewed: {fn: status}, index: N}
        _pool.json                the 139-image pool (for reference)

Run it yourself (you own start/stop):
    python script/penis_mask_annotator.py
    # serves on http://127.0.0.1:7863  (override with PENIS_ANNO_PORT)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import torch
from huggingface_hub import hf_hub_download, try_to_load_from_cache
from PIL import Image

import gradio as gr
from transformers import Sam2Model, Sam2Processor

# --------------------------------------------------------------------------- #
# config / paths
# --------------------------------------------------------------------------- #

DATASET = 'fbbcool/gts-v3'
SNAPSHOT = 'train'
SAM_ID = 'facebook/sam2.1-hiera-base-plus'
PORT = int(os.environ.get('PENIS_ANNO_PORT', '7863'))
HF_TOKEN = os.environ.get('HF_TOKEN_RW') or os.environ.get('HF_TOKEN')

WORKSPACE = Path(os.environ.get('WORKSPACE', str(Path.home() / 'Workspace')))
OUT_DIR = WORKSPACE / 'gts_v3_penis_masks'
OUT_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = OUT_DIR / '_recovery_state.json'
POOL_FILE = OUT_DIR / '_pool.json'

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

# --------------------------------------------------------------------------- #
# pool reconstruction (from the on-hub batch manifest)
# --------------------------------------------------------------------------- #


def _load_manifest() -> dict:
    p = hf_hub_download(
        DATASET, f'{SNAPSHOT}/masks/penis/_manifest.json', repo_type='dataset', token=HF_TOKEN
    )
    with open(p) as fh:
        return json.load(fh)


def build_pool() -> list[str]:
    """Recovery pool = 81 NudeNet misses + 58 curator-FP-rejected = 139 files."""
    m = _load_manifest()
    misses = [Path(d['file_name']).name for d in m['misses_detail']]
    fps = list(m['curator_review_2026_06_26']['fp_list'])
    seen: set[str] = set()
    pool: list[str] = []
    for fn in misses + fps:
        if fn not in seen:
            seen.add(fn)
            pool.append(fn)
    POOL_FILE.write_text(json.dumps({'pool': pool, 'misses': len(misses), 'fps': len(fps)}, indent=2))
    return pool


def resolve_src(fn: str) -> Path:
    """Local path to a source image; pull just that file from the hub if absent."""
    rel = f'{SNAPSHOT}/images/{fn}'
    cached = try_to_load_from_cache(DATASET, rel, repo_type='dataset')
    if isinstance(cached, str) and Path(cached).exists():
        return Path(cached)
    return Path(hf_hub_download(DATASET, rel, repo_type='dataset', token=HF_TOKEN))


# --------------------------------------------------------------------------- #
# recovery state
# --------------------------------------------------------------------------- #


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {'reviewed': {}, 'index': 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


# --------------------------------------------------------------------------- #
# SAM2
# --------------------------------------------------------------------------- #

print(f'[anno] loading SAM2 {SAM_ID} on {DEVICE} ...', flush=True)
_t0 = time.time()
SAM_MODEL = Sam2Model.from_pretrained(SAM_ID).to(DEVICE).eval()
SAM_PROC = Sam2Processor.from_pretrained(SAM_ID)
print(f'[anno] SAM2 ready in {time.time() - _t0:.1f}s', flush=True)

# --------------------------------------------------------------------------- #
# optional YOLO auto-proposal (box proposer -> SAM2), see script/penis_yolo_*.py
# --------------------------------------------------------------------------- #

YOLO_ENABLE = os.environ.get('PENIS_ANNO_YOLO', '1') == '1'
YOLO_CONF = float(os.environ.get('PENIS_ANNO_YOLO_CONF', '0.35'))
YOLO_WEIGHTS = WORKSPACE / 'penis_yolo' / 'runs' / 'penis_det_s' / 'weights' / 'best.pt'
YOLO_MODEL = None
if YOLO_ENABLE and YOLO_WEIGHTS.exists():
    try:
        from ultralytics import YOLO

        YOLO_MODEL = YOLO(str(YOLO_WEIGHTS))
        print(f'[anno] YOLO proposer loaded ({YOLO_WEIGHTS.name}, conf>={YOLO_CONF})', flush=True)
    except Exception as e:  # noqa: BLE001
        print(f'[anno] YOLO disabled ({e})', flush=True)
elif YOLO_ENABLE:
    print(f'[anno] YOLO weights not found at {YOLO_WEIGHTS}; auto-proposal off', flush=True)


def yolo_propose(img: Image.Image) -> tuple[list[float], float] | None:
    """Highest-confidence YOLO box ([x1,y1,x2,y2], conf) for `img`, or None."""
    if YOLO_MODEL is None:
        return None
    res = YOLO_MODEL.predict(source=img, conf=YOLO_CONF, imgsz=1024, verbose=False)[0]
    if res.boxes is None or len(res.boxes) == 0:
        return None
    confs = res.boxes.conf.cpu().numpy()
    boxes = res.boxes.xyxy.cpu().numpy()
    i = int(np.argmax(confs))
    return [float(v) for v in boxes[i]], float(confs[i])


def _inside(mask: np.ndarray, x: float, y: float) -> bool:
    h, w = mask.shape
    xi, yi = int(round(x)), int(round(y))
    if 0 <= yi < h and 0 <= xi < w:
        return bool(mask[yi, xi])
    return False


def _score(mask: np.ndarray, pts: list[list], iou: float) -> float:
    pos = [(p[0], p[1]) for p in pts if p[2] == 1]
    neg = [(p[0], p[1]) for p in pts if p[2] == 0]
    pos_cov = (sum(_inside(mask, x, y) for x, y in pos) / len(pos)) if pos else 1.0
    neg_cov = (sum(_inside(mask, x, y) for x, y in neg) / len(neg)) if neg else 0.0
    return pos_cov - 2.5 * neg_cov + 0.1 * float(iou)


def predict(img: Image.Image, pts: list[list], bbox: list | None) -> np.ndarray | None:
    """Run SAM2, return the best binary mask (bool HxW) or None if no prompt."""
    if not pts and not bbox:
        return None
    input_points = [[[[float(p[0]), float(p[1])] for p in pts]]] if pts else None
    input_labels = [[[int(p[2]) for p in pts]]] if pts else None
    input_boxes = [[[float(v) for v in bbox]]] if bbox else None

    t0 = time.time()
    inputs = SAM_PROC(
        images=img,
        input_points=input_points,
        input_labels=input_labels,
        input_boxes=input_boxes,
        return_tensors='pt',
    ).to(DEVICE)
    with torch.no_grad():
        out = SAM_MODEL(**inputs, multimask_output=True)
    masks = SAM_PROC.post_process_masks(out.pred_masks, inputs['original_sizes'])[0]
    # masks: [num_objects=1, num_masks=3, H, W] bool ; iou_scores: [1, 1, 3]
    cands = masks[0].cpu().numpy().astype(bool)  # [3, H, W]
    ious = out.iou_scores[0, 0].cpu().numpy()  # [3]

    best_i, best_s = 0, -1e9
    for i in range(cands.shape[0]):
        s = _score(cands[i], pts, float(ious[i]))
        if s > best_s:
            best_s, best_i = s, i
    print(
        f'[predict] ok t={time.time() - t0:.2f}s pts={len(pts)} bbox={"y" if bbox else "n"} '
        f'pick={best_i} score={best_s:.3f}',
        flush=True,
    )
    return cands[best_i]


def overlay(img: Image.Image, mask: np.ndarray | None) -> Image.Image:
    if mask is None:
        return img
    base = np.asarray(img.convert('RGB')).astype(np.float32)
    red = np.zeros_like(base)
    red[..., 0] = 255.0
    a = (mask[..., None].astype(np.float32)) * 0.45
    out = base * (1 - a) + red * a
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))


# --------------------------------------------------------------------------- #
# app state helpers
# --------------------------------------------------------------------------- #

POOL = build_pool()
STATE = load_state()
print(f'[anno] pool={len(POOL)}  reviewed={len(STATE["reviewed"])}', flush=True)


def next_pending(after: str | None = None) -> str | None:
    """First pool item not yet reviewed (optionally strictly after `after`)."""
    start = 0
    if after is not None and after in POOL:
        start = POOL.index(after) + 1
    for fn in POOL[start:]:
        if fn not in STATE['reviewed']:
            return fn
    for fn in POOL:  # wrap around
        if fn not in STATE['reviewed']:
            return fn
    return None


def counter_text() -> str:
    done = len(STATE['reviewed'])
    return f'{done}/{len(POOL)} reviewed  •  {len(POOL) - done} pending'


def load_image(fn: str | None):
    """Return the full set of UI/state updates to display image `fn`.

    If a YOLO box is proposed, it is fed through SAM2 and pre-loaded as the
    starting mask + bbox, so the curator just accepts or refines.
    """
    if fn is None:
        blank = '🎉 recovery pool complete — nothing pending'
        return (None, None, None, [], None, [], blank, '[]', '', counter_text())
    img = Image.open(resolve_src(fn)).convert('RGB')
    prop = yolo_propose(img)
    if prop is not None:
        box, conf = prop
        mask = predict(img, [], box)
        cov = float(mask.mean()) * 100 if mask is not None else 0.0
        status = (
            f'loaded {fn} ({img.width}×{img.height})  •  YOLO proposed box '
            f'conf={conf:.2f}  cov={cov:.2f}%  —  accept or refine'
        )
        return (
            img, overlay(img, mask), fn, [], box, [], status, '[]',
            json.dumps(box), counter_text(),
        )
    status = f'loaded {fn}  ({img.width}×{img.height})  •  no YOLO box — annotate manually'
    return (img, None, fn, [], None, [], status, '[]', '', counter_text())


# --------------------------------------------------------------------------- #
# event handlers
# --------------------------------------------------------------------------- #


def on_click(img, current_fn, pts, mode, bbox, history, evt: gr.SelectData):
    if img is None or current_fn is None:
        return gr.update(), pts, history, gr.update(), '[]'
    x, y = int(evt.index[0]), int(evt.index[1])
    label = 0 if (mode or 'include') == 'exclude' else 1
    pts = list(pts) + [[x, y, label]]
    history = list(history) + [['add_point', [x, y, label]]]
    mask = predict(img, pts, bbox)
    cov = float(mask.mean()) * 100 if mask is not None else 0.0
    npos = sum(1 for p in pts if p[2] == 1)
    nneg = sum(1 for p in pts if p[2] == 0)
    status = (
        f'add {"exclude" if label == 0 else "include"}  •  pts +{npos} / -{nneg}  •  '
        f'bbox={"set" if bbox else "none"}  •  coverage={cov:.2f}%'
    )
    return overlay(img, mask), pts, history, status, json.dumps(pts)


def on_bbox_change(bbox_text, img, current_fn, pts, prev_bbox, history):
    if img is None or current_fn is None or not (bbox_text or '').strip():
        return gr.update(), prev_bbox, history, gr.update(), json.dumps(pts)
    try:
        vals = [float(v) for v in json.loads(bbox_text)]
        x1, y1, x2, y2 = vals
        bbox = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
    except Exception as e:
        return gr.update(), prev_bbox, history, f'bad bbox: {e}', json.dumps(pts)
    history = list(history) + [['change_bbox', prev_bbox]]
    mask = predict(img, pts, bbox)
    cov = float(mask.mean()) * 100 if mask is not None else 0.0
    status = (
        f'bbox set [{int(bbox[0])},{int(bbox[1])},{int(bbox[2])},{int(bbox[3])}]  •  '
        f'coverage={cov:.2f}%'
    )
    return overlay(img, mask), bbox, history, status, json.dumps(pts)


def on_undo(img, current_fn, pts, bbox, history):
    if not history:
        return gr.update(), pts, bbox, history, 'nothing to undo', json.dumps(pts)
    history = list(history)
    action, payload = history.pop()
    if action == 'add_point':
        # remove the last matching point
        for i in range(len(pts) - 1, -1, -1):
            if pts[i] == payload:
                pts = pts[:i] + pts[i + 1 :]
                break
    elif action == 'change_bbox':
        bbox = payload
    mask = predict(img, pts, bbox)
    cov = float(mask.mean()) * 100 if mask is not None else 0.0
    npos = sum(1 for p in pts if p[2] == 1)
    nneg = sum(1 for p in pts if p[2] == 0)
    status = (
        f'undid {action}  •  pts +{npos} / -{nneg}  •  bbox={"set" if bbox else "none"}  •  '
        f'coverage={cov:.2f}%'
    )
    return overlay(img, mask), pts, bbox, history, status, json.dumps(pts)


def _write_sidecar(current_fn, status, mask, pts, bbox, img):
    pos = [[p[0], p[1]] for p in pts if p[2] == 1]
    neg = [[p[0], p[1]] for p in pts if p[2] == 0]
    cov = float(mask.mean()) * 100 if mask is not None else 0.0
    mask_file = current_fn if (status == 'accepted' and mask is not None) else None
    sidecar = {
        'file_name': current_fn,
        'mask_file': mask_file,
        'status': status,
        'image_natural_size': [img.width, img.height] if img is not None else None,
        'include_points': pos,
        'exclude_points': neg,
        'bbox': bbox,
        'mask_coverage_pct': round(cov, 4),
        'annotator': 'user',
        'tool': 'penis_mask_annotator',
        'sam_model': SAM_ID,
        'sam_multimask': True,
    }
    (OUT_DIR / f'{current_fn}.anno.json').write_text(json.dumps(sidecar, indent=2))
    if mask_file is not None:
        Image.fromarray((mask.astype(np.uint8) * 255), mode='L').save(OUT_DIR / mask_file)


def _terminal(current_fn, status, mask, pts, bbox, img):
    """Persist a terminal decision and advance to the next pending image."""
    if current_fn is None:
        return load_image(None)
    _write_sidecar(current_fn, status, mask, pts, bbox, img)
    STATE['reviewed'][current_fn] = status
    save_state(STATE)
    nxt = next_pending(after=current_fn)
    return load_image(nxt)


def on_accept(img, current_fn, mask_disp, pts, bbox):
    # recompute the mask from the prompts to persist (mask_disp is just overlay)
    mask = predict(img, pts, bbox) if (pts or bbox) else None
    if mask is None:
        # accept with no mask makes no sense; treat as no-op
        return (gr.update(),) * 10
    return _terminal(current_fn, 'accepted', mask, pts, bbox, img)


def on_skip_absent(img, current_fn, pts, bbox):
    return _terminal(current_fn, 'skipped_absent', None, pts, bbox, img)


def on_skip_hard(img, current_fn, pts, bbox):
    return _terminal(current_fn, 'skipped_hard', None, pts, bbox, img)


def on_defer(img, current_fn, pts, bbox):
    """Move on without recording a terminal decision."""
    nxt = next_pending(after=current_fn)
    return load_image(nxt)


def on_reset_pts(img, current_fn, bbox):
    mask = predict(img, [], bbox) if bbox else None
    status = 'cleared all points'
    return overlay(img, mask) if img is not None else None, [], [], status, '[]'


def on_reset_bbox(img, current_fn, pts):
    mask = predict(img, pts, None) if pts else None
    status = 'cleared bbox'
    return overlay(img, mask) if img is not None else None, None, [], '', status, json.dumps(pts)


# --------------------------------------------------------------------------- #
# front-end JS / CSS
# --------------------------------------------------------------------------- #

ANNO_JS = r"""
<script>
(function(){
  let gscale = 1.0;
  let layer = null;
  let drag = null;          // {x0,y0, moved}
  let dragRect = null;      // live preview div

  function ensureLayer(){
    if(!layer){
      layer = document.createElement('div');
      layer.id = 'anno_layer';
      layer.style.cssText = 'position:fixed;left:0;top:0;width:0;height:0;pointer-events:none;z-index:99999;';
      document.body.appendChild(layer);
    }
    return layer;
  }
  function paneImg(id){ const c=document.querySelector('#'+id); return c? c.querySelector('img') : null; }
  function srcImg(){ return paneImg('src_img'); }
  function maskImg(){ return paneImg('mask_img'); }
  function txt(sel){ const t=document.querySelector(sel+' textarea'); return t; }
  function setTxt(sel,val){
    const t = txt(sel); if(!t) return;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
    setter.call(t,val);
    t.dispatchEvent(new Event('input',{bubbles:true}));
  }

  // ---- zoom (cursor-anchored, both panes share scale) -----------------------
  function zoomPane(im, fx, fy, ns){
    if(!im) return;
    const rect = im.getBoundingClientRect();
    const st = im.__zst || {scale:1, tx:0, ty:0};
    const baseLeft = rect.left - st.tx, baseTop = rect.top - st.ty;
    const w0 = rect.width / st.scale, h0 = rect.height / st.scale;
    const lx = fx*w0, ly = fy*h0;
    const sx = rect.left + fx*rect.width, sy = rect.top + fy*rect.height;
    st.tx = sx - baseLeft - lx*ns;
    st.ty = sy - baseTop  - ly*ns;
    st.scale = ns;
    if(ns <= 1.0001){ st.scale=1; st.tx=0; st.ty=0; }
    im.__zst = st;
    im.style.transformOrigin = '0 0';
    im.style.transform = `translate(${st.tx}px,${st.ty}px) scale(${st.scale})`;
  }
  document.addEventListener('wheel', function(e){
    const sc = document.querySelector('#src_img'), mc = document.querySelector('#mask_img');
    const overSrc = sc && sc.contains(e.target), overMask = mc && mc.contains(e.target);
    if(!overSrc && !overMask) return;
    e.preventDefault();
    const im = overSrc ? srcImg() : maskImg();
    if(!im) return;
    const rect = im.getBoundingClientRect();
    const fx = (e.clientX - rect.left)/rect.width, fy = (e.clientY - rect.top)/rect.height;
    let ns = gscale * (e.deltaY < 0 ? 1.15 : 1/1.15);
    ns = Math.max(1, Math.min(12, ns));
    gscale = ns;
    zoomPane(srcImg(), fx, fy, ns);
    zoomPane(maskImg(), fx, fy, ns);
  }, {passive:false});

  // ---- bbox via click-and-drag on the source pane ---------------------------
  function natFromClient(im, cx, cy){
    const rect = im.getBoundingClientRect();
    return [ (cx-rect.left)/rect.width*im.naturalWidth,
             (cy-rect.top)/rect.height*im.naturalHeight ];
  }
  document.addEventListener('mousedown', function(e){
    const sc = document.querySelector('#src_img');
    if(!(sc && sc.contains(e.target))) return;
    const im = srcImg(); if(!im) return;
    if(e.button !== 0) return;
    drag = {x0:e.clientX, y0:e.clientY, moved:false};
  }, true);
  document.addEventListener('mousemove', function(e){
    if(!drag) return;
    if(Math.abs(e.clientX-drag.x0) + Math.abs(e.clientY-drag.y0) > 4) drag.moved = true;
    if(drag.moved){
      ensureLayer();
      if(!dragRect){
        dragRect = document.createElement('div');
        dragRect.style.cssText='position:fixed;border:2px dashed #19f;background:rgba(30,150,255,0.12);pointer-events:none;';
        layer.appendChild(dragRect);
      }
      const x=Math.min(drag.x0,e.clientX), y=Math.min(drag.y0,e.clientY);
      dragRect.style.left=x+'px'; dragRect.style.top=y+'px';
      dragRect.style.width=Math.abs(e.clientX-drag.x0)+'px';
      dragRect.style.height=Math.abs(e.clientY-drag.y0)+'px';
    }
  }, true);
  document.addEventListener('mouseup', function(e){
    if(!drag) return;
    const im = srcImg();
    const moved = drag.moved;
    if(moved && im){
      const a = natFromClient(im, drag.x0, drag.y0);
      const b = natFromClient(im, e.clientX, e.clientY);
      setTxt('#bbox_input', JSON.stringify([a[0],a[1],b[0],b[1]]));
    }
    drag = null;
    if(dragRect){ dragRect.remove(); dragRect=null; }
    if(moved){ // suppress the click that would otherwise add a point
      const kill = function(ev){ ev.stopImmediatePropagation(); ev.preventDefault();
        document.removeEventListener('click', kill, true); };
      document.addEventListener('click', kill, true);
    }
  }, true);

  // ---- markers + committed bbox (polled, constant screen size) ---------------
  function readPts(){ const t=txt('#points_dom_text'); if(!t||!t.value) return []; try{return JSON.parse(t.value);}catch(_){return [];} }
  function readBbox(){ const t=txt('#bbox_input'); if(!t||!t.value) return null; try{return JSON.parse(t.value);}catch(_){return null;} }
  function render(){
    const im = srcImg();
    const lay = ensureLayer();
    // clear (keep live dragRect)
    Array.from(lay.children).forEach(c=>{ if(c!==dragRect) c.remove(); });
    if(!im) return;
    im.draggable = false;
    const rect = im.getBoundingClientRect();
    const sx = rect.width/im.naturalWidth, sy = rect.height/im.naturalHeight;
    readPts().forEach(p=>{
      const d = document.createElement('div');
      const col = p[2]===0 ? '#f33' : '#1d6';
      d.style.cssText = 'position:fixed;width:8px;height:8px;border-radius:50%;border:1px solid #fff;'
        + 'box-shadow:0 0 2px #000;pointer-events:none;background:'+col+';';
      d.style.left = (rect.left + p[0]*sx - 4)+'px';
      d.style.top  = (rect.top  + p[1]*sy - 4)+'px';
      lay.appendChild(d);
    });
    const bb = readBbox();
    if(bb){
      const x1=Math.min(bb[0],bb[2]), y1=Math.min(bb[1],bb[3]);
      const x2=Math.max(bb[0],bb[2]), y2=Math.max(bb[1],bb[3]);
      const d = document.createElement('div');
      d.style.cssText='position:fixed;border:2px solid #ffcc00;pointer-events:none;';
      d.style.left=(rect.left+x1*sx)+'px'; d.style.top=(rect.top+y1*sy)+'px';
      d.style.width=((x2-x1)*sx)+'px'; d.style.height=((y2-y1)*sy)+'px';
      lay.appendChild(d);
    }
  }
  setInterval(render, 120);

  // ---- Shift toggles include/exclude radio ----------------------------------
  function setMode(val){
    document.querySelectorAll('#mode_radio input[type=radio]').forEach(r=>{
      if(r.value===val && !r.checked){
        r.checked = true;
        r.dispatchEvent(new Event('input',{bubbles:true}));
        r.dispatchEvent(new Event('change',{bubbles:true}));
      }
    });
  }
  document.addEventListener('keydown', e=>{ if(e.key==='Shift') setMode('exclude'); });
  document.addEventListener('keyup',   e=>{ if(e.key==='Shift') setMode('include'); });

  // ---- kill native drag-and-drop (interferes with bbox + quick-load) --------
  ['dragstart','dragenter','dragover','drop'].forEach(ev=>
    document.addEventListener(ev, e=>{ e.preventDefault(); }, false));
})();
</script>
"""

ANNO_CSS = """
#bbox_input, #points_dom_text { display: none !important; }
#src_img img, #mask_img img { will-change: transform; }
"""

# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #

with gr.Blocks(title='penis mask annotator') as demo:
    gr.Markdown(
        '## penis-mask annotator (gts-v3 recovery pool)\n'
        'each image loads with a **YOLO-proposed** box → SAM2 mask; just accept or refine.  \n'
        'left-click = include · **Shift**+click = exclude · click-drag = bbox · '
        'wheel = zoom at cursor'
    )
    counter = gr.Markdown(counter_text())

    fn_state = gr.State(None)
    pts_state = gr.State([])
    bbox_state = gr.State(None)
    history_state = gr.State([])

    with gr.Row():
        src_img = gr.Image(
            type='pil', sources=[], interactive=True, elem_id='src_img', label='source', height=560
        )
        mask_img = gr.Image(
            type='pil', interactive=False, elem_id='mask_img', label='mask overlay', height=560
        )

    mode_radio = gr.Radio(
        ['include', 'exclude'], value='include', elem_id='mode_radio',
        label='click mode (hold Shift to flip)',
    )
    status = gr.Textbox(label='status', interactive=False)

    bbox_input = gr.Textbox(elem_id='bbox_input')
    points_dom_text = gr.Textbox(elem_id='points_dom_text', value='[]')

    with gr.Row():
        accept_btn = gr.Button('✅ accept mask', variant='primary')
        skip_absent_btn = gr.Button('🚫 skip — no penis present')
        skip_hard_btn = gr.Button('🥵 skip — too hard to separate')
    with gr.Row():
        undo_btn = gr.Button('↶ undo last')
        reset_pts_btn = gr.Button('clear points')
        reset_bbox_btn = gr.Button('clear bbox')
        defer_btn = gr.Button('⏭ next (no decision)')

    # --- wiring -------------------------------------------------------------- #
    src_img.select(
        on_click,
        [src_img, fn_state, pts_state, mode_radio, bbox_state, history_state],
        [mask_img, pts_state, history_state, status, points_dom_text],
    )
    # .input (not .change) so it fires only on a user drag, NOT when load_image
    # programmatically sets a YOLO-proposed box into the textbox.
    bbox_input.input(
        on_bbox_change,
        [bbox_input, src_img, fn_state, pts_state, bbox_state, history_state],
        [mask_img, bbox_state, history_state, status, points_dom_text],
    )
    undo_btn.click(
        on_undo,
        [src_img, fn_state, pts_state, bbox_state, history_state],
        [mask_img, pts_state, bbox_state, history_state, status, points_dom_text],
    )

    advance_out = [
        src_img, mask_img, fn_state, pts_state, bbox_state, history_state,
        status, points_dom_text, bbox_input, counter,
    ]
    accept_btn.click(on_accept, [src_img, fn_state, mask_img, pts_state, bbox_state], advance_out)
    skip_absent_btn.click(on_skip_absent, [src_img, fn_state, pts_state, bbox_state], advance_out)
    skip_hard_btn.click(on_skip_hard, [src_img, fn_state, pts_state, bbox_state], advance_out)
    defer_btn.click(on_defer, [src_img, fn_state, pts_state, bbox_state], advance_out)

    reset_pts_btn.click(
        on_reset_pts,
        [src_img, fn_state, bbox_state],
        [mask_img, pts_state, history_state, status, points_dom_text],
    )
    reset_bbox_btn.click(
        on_reset_bbox,
        [src_img, fn_state, pts_state],
        [mask_img, bbox_state, history_state, bbox_input, status, points_dom_text],
    )

    demo.load(lambda: load_image(next_pending()), None, advance_out)


if __name__ == '__main__':
    print(f'[anno] serving on http://127.0.0.1:{PORT}  out={OUT_DIR}', flush=True)
    demo.launch(server_name='127.0.0.1', server_port=PORT, head=ANNO_JS, css=ANNO_CSS)
