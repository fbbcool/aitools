"""Penis-mask annotator as a tab in the AIDB scene app.

Interactive SAM2 masking with a YOLO box-proposer, backed by the scene DB:

  * candidate pool  = every registered SceneImage not yet in claude_penis_masks
                      (unreviewed-first; deferred images reappear)
  * pixels          = SceneImage.pil (native/original resolution)
  * on accept/skip  = one doc upserted into the ``claude_penis_masks`` Mongo
                      collection (status + points + bbox + base64 mask)

Models (SAM2 + YOLO) load LAZILY on the first activation of the tab, so the
host app stays light until the tab is actually used.

All front-end JS listeners are scoped behind ``pmActive()`` (the annotator
image being visible) and every elem_id is ``pm_``-prefixed, so nothing here
interferes with the other tabs.

Storage doc schema (claude_penis_masks), keyed by ``image_id``:
    { image_id, status: accepted|skipped_absent|skipped_hard,
      include_points, exclude_points, bbox, image_size:[W,H],
      mask_coverage_pct, mask_png_b64|null, annotator, tool,
      sam_model, yolo_weights|null, ts }
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
from PIL import Image

import gradio as gr

from aidb.scene.scene_common import SceneDef

SAM_ID = 'facebook/sam2.1-hiera-base-plus'
CATEGORY = 'penis'
COLLECTION = 'claude_penis_masks'
# on-disk mask store: <scene-root>/___mask/<category>/mask_<category>___<id>.png
MASK_DIRNAME = f'{SceneDef.SEPERATOR_ID}mask'          # '___mask'
MASK_PREFIX = f'mask_{CATEGORY}'                       # 'mask_penis'
WORKSPACE = Path(os.environ.get('WORKSPACE', str(Path.home() / 'Workspace')))
# Prefer the scene-DB-trained detector (465 pos + 339 neg, native res); fall
# back to the original gts-v3 model (127 imgs). Override with PENIS_YOLO_WEIGHTS.
_YOLO_CANDIDATES = [
    WORKSPACE / 'penis_yolo_scenedb' / 'runs' / 'penis_det_scenedb' / 'weights' / 'best.pt',
    WORKSPACE / 'penis_yolo' / 'runs' / 'penis_det_s' / 'weights' / 'best.pt',
]
YOLO_WEIGHTS = Path(os.environ['PENIS_YOLO_WEIGHTS']) if os.environ.get('PENIS_YOLO_WEIGHTS') else \
    next((p for p in _YOLO_CANDIDATES if p.exists()), _YOLO_CANDIDATES[0])
YOLO_CONF = float(os.environ.get('PENIS_ANNO_YOLO_CONF', '0.35'))
YOLO_ENABLE = os.environ.get('PENIS_ANNO_YOLO', '1') == '1'
TOOL = 'penis_mask_annotator(tab)'


class PenisMaskTab:
    def __init__(self, scm, verbose: int = 0) -> None:
        self._scm = scm
        self._dbc = scm._dbc
        self._sim = scm.scene_image_manager()
        self._col = self._dbc._get_collection(COLLECTION)
        # on-disk mask store, rooted at the scene-DB root
        self._mask_dir = Path(self._sim.root) / MASK_DIRNAME / CATEGORY
        self._verbose = verbose
        # lazily-loaded model handles
        self._loaded = False
        self._sam_model = None
        self._sam_proc = None
        self._yolo = None
        self._device = 'cpu'

    # ------------------------------------------------------------------ #
    # lazy model loading (called from the tab .select handler)
    # ------------------------------------------------------------------ #
    def _ensure_models(self) -> None:
        if self._loaded:
            return
        import torch
        from transformers import Sam2Model, Sam2Processor

        self._device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f'[pm] loading SAM2 {SAM_ID} on {self._device} ...', flush=True)
        t0 = time.time()
        self._sam_model = Sam2Model.from_pretrained(SAM_ID).to(self._device).eval()
        self._sam_proc = Sam2Processor.from_pretrained(SAM_ID)
        print(f'[pm] SAM2 ready in {time.time() - t0:.1f}s', flush=True)

        if YOLO_ENABLE and YOLO_WEIGHTS.exists():
            try:
                from ultralytics import YOLO

                self._yolo = YOLO(str(YOLO_WEIGHTS))
                print(f'[pm] YOLO proposer loaded ({YOLO_WEIGHTS.name}, conf>={YOLO_CONF})', flush=True)
            except Exception as e:  # noqa: BLE001
                print(f'[pm] YOLO disabled ({e})', flush=True)
        elif YOLO_ENABLE:
            print(f'[pm] YOLO weights not found at {YOLO_WEIGHTS}; auto-proposal off', flush=True)
        self._loaded = True

    # ------------------------------------------------------------------ #
    # pool (scene DB) + review state (claude_penis_masks)
    # ------------------------------------------------------------------ #
    def _reviewed_ids(self) -> set[str]:
        return {d['image_id'] for d in self._col.find({}, {'image_id': 1})}

    def _pool(self) -> list[str]:
        return list(self._sim.ids)

    def _next_pending(self, after: str | None = None) -> str | None:
        pool = self._pool()
        reviewed = self._reviewed_ids()
        start = 0
        if after is not None and after in pool:
            start = pool.index(after) + 1
        for iid in pool[start:]:
            if iid not in reviewed:
                return iid
        for iid in pool:  # wrap
            if iid not in reviewed:
                return iid
        return None

    def _counter_text(self) -> str:
        total = len(self._pool())
        done = self._col.count_documents({})
        return f'{done}/{total} reviewed  •  {total - done} pending'

    def _pixels(self, image_id: str) -> Image.Image | None:
        simg = self._sim.img_from_id(image_id)
        if simg is None:
            return None
        pil = simg.pil
        return pil.convert('RGB') if pil is not None else None

    # ------------------------------------------------------------------ #
    # SAM2 + YOLO
    # ------------------------------------------------------------------ #
    @staticmethod
    def _inside(mask: np.ndarray, x: float, y: float) -> bool:
        h, w = mask.shape
        xi, yi = int(round(x)), int(round(y))
        if 0 <= yi < h and 0 <= xi < w:
            return bool(mask[yi, xi])
        return False

    def _score(self, mask: np.ndarray, pts: list[list], iou: float) -> float:
        pos = [(p[0], p[1]) for p in pts if p[2] == 1]
        neg = [(p[0], p[1]) for p in pts if p[2] == 0]
        pos_cov = (sum(self._inside(mask, x, y) for x, y in pos) / len(pos)) if pos else 1.0
        neg_cov = (sum(self._inside(mask, x, y) for x, y in neg) / len(neg)) if neg else 0.0
        return pos_cov - 2.5 * neg_cov + 0.1 * float(iou)

    def _predict(self, img: Image.Image, pts: list[list], bbox: list | None) -> np.ndarray | None:
        if img is None or (not pts and not bbox):
            return None
        import torch

        input_points = [[[[float(p[0]), float(p[1])] for p in pts]]] if pts else None
        input_labels = [[[int(p[2]) for p in pts]]] if pts else None
        input_boxes = [[[float(v) for v in bbox]]] if bbox else None
        inputs = self._sam_proc(
            images=img,
            input_points=input_points,
            input_labels=input_labels,
            input_boxes=input_boxes,
            return_tensors='pt',
        ).to(self._device)
        with torch.no_grad():
            out = self._sam_model(**inputs, multimask_output=True)
        masks = self._sam_proc.post_process_masks(out.pred_masks, inputs['original_sizes'])[0]
        cands = masks[0].cpu().numpy().astype(bool)  # [3, H, W]
        ious = out.iou_scores[0, 0].cpu().numpy()  # [3]
        best_i, best_s = 0, -1e9
        for i in range(cands.shape[0]):
            s = self._score(cands[i], pts, float(ious[i]))
            if s > best_s:
                best_s, best_i = s, i
        return cands[best_i]

    def _yolo_propose(self, img: Image.Image) -> tuple[list[float], float] | None:
        if self._yolo is None:
            return None
        res = self._yolo.predict(source=img, conf=YOLO_CONF, imgsz=1024, verbose=False)[0]
        if res.boxes is None or len(res.boxes) == 0:
            return None
        confs = res.boxes.conf.cpu().numpy()
        boxes = res.boxes.xyxy.cpu().numpy()
        i = int(np.argmax(confs))
        return [float(v) for v in boxes[i]], float(confs[i])

    @staticmethod
    def _overlay(img: Image.Image, mask: np.ndarray | None) -> Image.Image:
        if mask is None:
            return img
        base = np.asarray(img.convert('RGB')).astype(np.float32)
        red = np.zeros_like(base)
        red[..., 0] = 255.0
        a = (mask[..., None].astype(np.float32)) * 0.45
        out = base * (1 - a) + red * a
        return Image.fromarray(out.clip(0, 255).astype(np.uint8))

    # ------------------------------------------------------------------ #
    # storage: mask PNG -> disk, all metadata -> claude_penis_masks (Mongo)
    # ------------------------------------------------------------------ #
    def _write_mask_png(self, image_id, mask: np.ndarray) -> str:
        """Write the binary mask to <root>/___mask/<cat>/mask_<cat>___<id>.png.

        Returns the path relative to the scene-DB root (stored in Mongo).
        """
        self._mask_dir.mkdir(parents=True, exist_ok=True)
        fname = SceneDef.filename_from_id(MASK_PREFIX, image_id, suffix=SceneDef.SUFFIX_IMG_STD)
        path = self._mask_dir / fname
        Image.fromarray((mask.astype(np.uint8) * 255), mode='L').save(path)
        return str(path.relative_to(Path(self._sim.root)))

    def _store(self, image_id, status, mask, pts, bbox, img) -> None:
        cov = float(mask.mean()) * 100 if mask is not None else 0.0
        mask_file = None
        if status == 'accepted' and mask is not None:
            mask_file = self._write_mask_png(image_id, mask)
        doc = {
            'image_id': image_id,
            'category': CATEGORY,
            'status': status,
            'include_points': [[p[0], p[1]] for p in pts if p[2] == 1],
            'exclude_points': [[p[0], p[1]] for p in pts if p[2] == 0],
            'bbox': bbox,
            'image_size': [img.width, img.height] if img is not None else None,
            'mask_coverage_pct': round(cov, 4),
            'mask_file': mask_file,   # relative to scene-DB root, or None for skips
            'annotator': 'user',
            'tool': TOOL,
            'sam_model': SAM_ID,
            'yolo_weights': YOLO_WEIGHTS.name if self._yolo is not None else None,
            'ts': int(time.time() * 1000),
        }
        self._col.replace_one({'image_id': image_id}, doc, upsert=True)

    # ------------------------------------------------------------------ #
    # image load (with YOLO proposal) -> 10-tuple for advance_out
    # ------------------------------------------------------------------ #
    def _load_image(self, image_id: str | None):
        if image_id is None:
            blank = '🎉 no pending images — every registered image has a mask decision'
            return (None, None, None, [], None, [], blank, '[]', '', self._counter_text())
        img = self._pixels(image_id)
        if img is None:
            return (None, None, image_id, [], None, [], f'⚠ pixels unavailable for {image_id}',
                    '[]', '', self._counter_text())
        prop = self._yolo_propose(img)
        if prop is not None:
            box, conf = prop
            mask = self._predict(img, [], box)
            cov = float(mask.mean()) * 100 if mask is not None else 0.0
            status = (
                f'{image_id} ({img.width}×{img.height})  •  YOLO box conf={conf:.2f} '
                f'cov={cov:.2f}%  —  accept or refine'
            )
            return (img, self._overlay(img, mask), image_id, [], box, [], status, '[]',
                    _json(box), self._counter_text())
        status = f'{image_id} ({img.width}×{img.height})  •  no YOLO box — annotate manually'
        return (img, None, image_id, [], None, [], status, '[]', '', self._counter_text())

    # ------------------------------------------------------------------ #
    # event handlers
    # ------------------------------------------------------------------ #
    def _on_tab_active(self, current_fn):
        self._ensure_models()
        if current_fn:
            # already showing an image; just refresh the counter, keep the rest
            return (gr.update(),) * 9 + (self._counter_text(),)
        return self._load_image(self._next_pending())

    def _on_click(self, img, current_fn, pts, mode, bbox, history, evt: gr.SelectData):
        if img is None or current_fn is None:
            return gr.update(), pts, history, gr.update(), '[]'
        x, y = int(evt.index[0]), int(evt.index[1])
        label = 0 if (mode or 'include') == 'exclude' else 1
        pts = list(pts) + [[x, y, label]]
        history = list(history) + [['add_point', [x, y, label]]]
        mask = self._predict(img, pts, bbox)
        cov = float(mask.mean()) * 100 if mask is not None else 0.0
        npos = sum(1 for p in pts if p[2] == 1)
        nneg = sum(1 for p in pts if p[2] == 0)
        status = (
            f'add {"exclude" if label == 0 else "include"}  •  pts +{npos} / -{nneg}  •  '
            f'bbox={"set" if bbox else "none"}  •  cov={cov:.2f}%'
        )
        return self._overlay(img, mask), pts, history, status, _json(pts)

    def _on_bbox(self, bbox_text, img, current_fn, pts, prev_bbox, history):
        if img is None or current_fn is None or not (bbox_text or '').strip():
            return gr.update(), prev_bbox, history, gr.update(), _json(pts)
        try:
            x1, y1, x2, y2 = (float(v) for v in _unjson(bbox_text))
            bbox = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
        except Exception as e:  # noqa: BLE001
            return gr.update(), prev_bbox, history, f'bad bbox: {e}', _json(pts)
        history = list(history) + [['change_bbox', prev_bbox]]
        mask = self._predict(img, pts, bbox)
        cov = float(mask.mean()) * 100 if mask is not None else 0.0
        status = f'bbox [{int(bbox[0])},{int(bbox[1])},{int(bbox[2])},{int(bbox[3])}]  •  cov={cov:.2f}%'
        return self._overlay(img, mask), bbox, history, status, _json(pts)

    def _on_undo(self, img, current_fn, pts, bbox, history):
        if not history:
            return gr.update(), pts, bbox, history, 'nothing to undo', _json(pts)
        history = list(history)
        action, payload = history.pop()
        if action == 'add_point':
            for i in range(len(pts) - 1, -1, -1):
                if pts[i] == payload:
                    pts = pts[:i] + pts[i + 1:]
                    break
        elif action == 'change_bbox':
            bbox = payload
        mask = self._predict(img, pts, bbox)
        cov = float(mask.mean()) * 100 if mask is not None else 0.0
        npos = sum(1 for p in pts if p[2] == 1)
        nneg = sum(1 for p in pts if p[2] == 0)
        status = f'undid {action}  •  pts +{npos} / -{nneg}  •  cov={cov:.2f}%'
        return self._overlay(img, mask), pts, bbox, history, status, _json(pts)

    def _terminal(self, image_id, status, mask, pts, bbox, img):
        if image_id is None:
            return self._load_image(None)
        self._store(image_id, status, mask, pts, bbox, img)
        return self._load_image(self._next_pending(after=image_id))

    def _on_accept(self, img, current_fn, pts, bbox):
        mask = self._predict(img, pts, bbox) if (pts or bbox) else None
        if mask is None:
            return (gr.update(),) * 10
        return self._terminal(current_fn, 'accepted', mask, pts, bbox, img)

    def _on_skip_absent(self, img, current_fn, pts, bbox):
        return self._terminal(current_fn, 'skipped_absent', None, pts, bbox, img)

    def _on_skip_hard(self, img, current_fn, pts, bbox):
        return self._terminal(current_fn, 'skipped_hard', None, pts, bbox, img)

    def _on_defer(self, img, current_fn, pts, bbox):
        return self._load_image(self._next_pending(after=current_fn))

    def _on_reset_pts(self, img, current_fn, bbox):
        mask = self._predict(img, [], bbox) if bbox else None
        return (self._overlay(img, mask) if img is not None else None, [], [],
                'cleared points', '[]')

    def _on_reset_bbox(self, img, current_fn, pts):
        mask = self._predict(img, pts, None) if pts else None
        return (self._overlay(img, mask) if img is not None else None, None, [], '',
                'cleared bbox', _json(pts))

    # ------------------------------------------------------------------ #
    # UI build (call inside the app's gr.Blocks context)
    # ------------------------------------------------------------------ #
    def build(self) -> None:
        # NOTE: the annotator's JS is injected via the app's gr.Blocks(head=...)
        # (see PENIS_MASK_HEAD) — <script> inside gr.HTML is NOT executed by the
        # browser (innerHTML-inserted scripts don't run), so it must live in
        # <head>. The style block below is harmless if duplicated in head.
        with gr.Tab('Penis Masks', elem_id='pm_tab') as tab:
            gr.Markdown(
                '## penis-mask annotator (scene DB)\n'
                'YOLO-proposed box → SAM2 mask on load; accept or refine.  \n'
                'left-click = include · **Shift**+click = exclude · click-drag = bbox · '
                'wheel = zoom · results stored to `claude_penis_masks`'
            )
            counter = gr.Markdown(self._counter_text())

            fn_state = gr.State(None)
            pts_state = gr.State([])
            bbox_state = gr.State(None)
            history_state = gr.State([])

            with gr.Row():
                src_img = gr.Image(type='pil', sources=[], interactive=True,
                                   elem_id='pm_src_img', label='source', height=560)
                mask_img = gr.Image(type='pil', interactive=False,
                                    elem_id='pm_mask_img', label='mask overlay', height=560)

            mode_radio = gr.Radio(['include', 'exclude'], value='include',
                                  elem_id='pm_mode_radio', label='click mode (hold Shift to flip)')
            status = gr.Textbox(label='status', interactive=False)
            bbox_input = gr.Textbox(elem_id='pm_bbox_input')
            points_dom = gr.Textbox(elem_id='pm_points_dom', value='[]')

            with gr.Row():
                accept_btn = gr.Button('✅ accept mask', variant='primary')
                skip_absent_btn = gr.Button('🚫 skip — no penis present')
                skip_hard_btn = gr.Button('🥵 skip — too hard to separate')
            with gr.Row():
                undo_btn = gr.Button('↶ undo last')
                reset_pts_btn = gr.Button('clear points')
                reset_bbox_btn = gr.Button('clear bbox')
                defer_btn = gr.Button('⏭ next (no decision)')

            advance_out = [src_img, mask_img, fn_state, pts_state, bbox_state, history_state,
                           status, points_dom, bbox_input, counter]

            # lazy model load + first image on first activation
            tab.select(self._on_tab_active, [fn_state], advance_out)

            src_img.select(
                self._on_click,
                [src_img, fn_state, pts_state, mode_radio, bbox_state, history_state],
                [mask_img, pts_state, history_state, status, points_dom],
            )
            bbox_input.input(
                self._on_bbox,
                [bbox_input, src_img, fn_state, pts_state, bbox_state, history_state],
                [mask_img, bbox_state, history_state, status, points_dom],
            )
            undo_btn.click(
                self._on_undo,
                [src_img, fn_state, pts_state, bbox_state, history_state],
                [mask_img, pts_state, bbox_state, history_state, status, points_dom],
            )
            accept_btn.click(self._on_accept, [src_img, fn_state, pts_state, bbox_state], advance_out)
            skip_absent_btn.click(self._on_skip_absent, [src_img, fn_state, pts_state, bbox_state], advance_out)
            skip_hard_btn.click(self._on_skip_hard, [src_img, fn_state, pts_state, bbox_state], advance_out)
            defer_btn.click(self._on_defer, [src_img, fn_state, pts_state, bbox_state], advance_out)
            reset_pts_btn.click(self._on_reset_pts, [src_img, fn_state, bbox_state],
                                [mask_img, pts_state, history_state, status, points_dom])
            reset_bbox_btn.click(self._on_reset_bbox, [src_img, fn_state, pts_state],
                                 [mask_img, bbox_state, history_state, bbox_input, status, points_dom])


def _json(obj) -> str:
    import json
    return json.dumps(obj)


def _unjson(s: str):
    import json
    return json.loads(s)


# --------------------------------------------------------------------------- #
# scoped front-end JS + CSS (inert unless the annotator image is visible).
# Injected into the app's <head> via gr.Blocks(head=PENIS_MASK_HEAD) — a
# <script> inside gr.HTML does NOT run (innerHTML-inserted scripts don't
# execute), so it must be in <head>.
# --------------------------------------------------------------------------- #

PENIS_MASK_HEAD = r"""
<style>
#pm_bbox_input, #pm_points_dom { display: none !important; }
#pm_src_img img, #pm_mask_img img { will-change: transform; }
</style>
<script>
(function(){
  let gscale = 1.0, layer = null, drag = null, dragRect = null;

  function pane(id){ const c=document.querySelector('#'+id); return c? c.querySelector('img') : null; }
  function srcImg(){ return pane('pm_src_img'); }
  function maskImg(){ return pane('pm_mask_img'); }
  // annotator active = its source image is present AND visible (tab shown)
  function pmActive(){ const im=srcImg(); return !!(im && im.offsetParent !== null); }
  function ensureLayer(){
    if(!layer){ layer=document.createElement('div'); layer.id='pm_layer';
      layer.style.cssText='position:fixed;left:0;top:0;width:0;height:0;pointer-events:none;z-index:99999;';
      document.body.appendChild(layer);} return layer;
  }
  function txt(sel){ return document.querySelector(sel+' textarea'); }
  function setTxt(sel,val){ const t=txt(sel); if(!t) return;
    const s=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
    s.call(t,val); t.dispatchEvent(new Event('input',{bubbles:true})); }

  function zoomPane(im, fx, fy, ns){
    if(!im) return;
    const rect=im.getBoundingClientRect();
    const st=im.__zst||{scale:1,tx:0,ty:0};
    const baseLeft=rect.left-st.tx, baseTop=rect.top-st.ty;
    const w0=rect.width/st.scale, h0=rect.height/st.scale;
    const lx=fx*w0, ly=fy*h0;
    const sx=rect.left+fx*rect.width, sy=rect.top+fy*rect.height;
    st.tx=sx-baseLeft-lx*ns; st.ty=sy-baseTop-ly*ns; st.scale=ns;
    if(ns<=1.0001){st.scale=1;st.tx=0;st.ty=0;}
    im.__zst=st; im.style.transformOrigin='0 0';
    im.style.transform=`translate(${st.tx}px,${st.ty}px) scale(${st.scale})`;
  }
  document.addEventListener('wheel', function(e){
    if(!pmActive()) return;
    const sc=document.querySelector('#pm_src_img'), mc=document.querySelector('#pm_mask_img');
    const overSrc=sc&&sc.contains(e.target), overMask=mc&&mc.contains(e.target);
    if(!overSrc && !overMask) return;
    e.preventDefault();
    const im=overSrc?srcImg():maskImg(); if(!im) return;
    const rect=im.getBoundingClientRect();
    const fx=(e.clientX-rect.left)/rect.width, fy=(e.clientY-rect.top)/rect.height;
    let ns=gscale*(e.deltaY<0?1.15:1/1.15); ns=Math.max(1,Math.min(12,ns)); gscale=ns;
    zoomPane(srcImg(),fx,fy,ns); zoomPane(maskImg(),fx,fy,ns);
  }, {passive:false});

  function natFromClient(im,cx,cy){ const r=im.getBoundingClientRect();
    return [(cx-r.left)/r.width*im.naturalWidth,(cy-r.top)/r.height*im.naturalHeight]; }
  document.addEventListener('mousedown', function(e){
    if(!pmActive()) return;
    const sc=document.querySelector('#pm_src_img');
    if(!(sc&&sc.contains(e.target))||e.button!==0) return;
    drag={x0:e.clientX,y0:e.clientY,moved:false};
  }, true);
  document.addEventListener('mousemove', function(e){
    if(!drag) return;
    if(Math.abs(e.clientX-drag.x0)+Math.abs(e.clientY-drag.y0)>4) drag.moved=true;
    if(drag.moved){ ensureLayer();
      if(!dragRect){ dragRect=document.createElement('div');
        dragRect.style.cssText='position:fixed;border:2px dashed #19f;background:rgba(30,150,255,0.12);pointer-events:none;';
        layer.appendChild(dragRect);}
      const x=Math.min(drag.x0,e.clientX), y=Math.min(drag.y0,e.clientY);
      dragRect.style.left=x+'px'; dragRect.style.top=y+'px';
      dragRect.style.width=Math.abs(e.clientX-drag.x0)+'px';
      dragRect.style.height=Math.abs(e.clientY-drag.y0)+'px'; }
  }, true);
  document.addEventListener('mouseup', function(e){
    if(!drag) return;
    const im=srcImg(), moved=drag.moved;
    if(moved&&im){ const a=natFromClient(im,drag.x0,drag.y0), b=natFromClient(im,e.clientX,e.clientY);
      setTxt('#pm_bbox_input', JSON.stringify([a[0],a[1],b[0],b[1]])); }
    drag=null; if(dragRect){dragRect.remove();dragRect=null;}
    if(moved){ const kill=function(ev){ ev.stopImmediatePropagation(); ev.preventDefault();
      document.removeEventListener('click',kill,true); };
      document.addEventListener('click',kill,true); }
  }, true);

  function readPts(){ const t=txt('#pm_points_dom'); if(!t||!t.value) return []; try{return JSON.parse(t.value);}catch(_){return [];} }
  function readBbox(){ const t=txt('#pm_bbox_input'); if(!t||!t.value) return null; try{return JSON.parse(t.value);}catch(_){return null;} }
  function render(){
    const lay=ensureLayer();
    Array.from(lay.children).forEach(c=>{ if(c!==dragRect) c.remove(); });
    if(!pmActive()) return;
    const im=srcImg(); if(!im) return;
    im.draggable=false;
    const rect=im.getBoundingClientRect();
    const sx=rect.width/im.naturalWidth, sy=rect.height/im.naturalHeight;
    readPts().forEach(p=>{ const d=document.createElement('div');
      const col=p[2]===0?'#f33':'#1d6';
      d.style.cssText='position:fixed;width:8px;height:8px;border-radius:50%;border:1px solid #fff;box-shadow:0 0 2px #000;pointer-events:none;background:'+col+';';
      d.style.left=(rect.left+p[0]*sx-4)+'px'; d.style.top=(rect.top+p[1]*sy-4)+'px'; lay.appendChild(d); });
    const bb=readBbox();
    if(bb){ const x1=Math.min(bb[0],bb[2]),y1=Math.min(bb[1],bb[3]),x2=Math.max(bb[0],bb[2]),y2=Math.max(bb[1],bb[3]);
      const d=document.createElement('div');
      d.style.cssText='position:fixed;border:2px solid #ffcc00;pointer-events:none;';
      d.style.left=(rect.left+x1*sx)+'px'; d.style.top=(rect.top+y1*sy)+'px';
      d.style.width=((x2-x1)*sx)+'px'; d.style.height=((y2-y1)*sy)+'px'; lay.appendChild(d); }
  }
  setInterval(render, 120);

  function setMode(val){ if(!pmActive()) return;
    document.querySelectorAll('#pm_mode_radio input[type=radio]').forEach(r=>{
      if(r.value===val&&!r.checked){ r.checked=true;
        r.dispatchEvent(new Event('input',{bubbles:true}));
        r.dispatchEvent(new Event('change',{bubbles:true})); } }); }
  document.addEventListener('keydown', e=>{ if(e.key==='Shift') setMode('exclude'); });
  document.addEventListener('keyup',   e=>{ if(e.key==='Shift') setMode('include'); });

  // kill native drag-drop ONLY while the annotator tab is active
  ['dragstart','dragenter','dragover','drop'].forEach(ev=>
    document.addEventListener(ev, e=>{ if(pmActive()) e.preventDefault(); }, false));
})();
</script>
"""
