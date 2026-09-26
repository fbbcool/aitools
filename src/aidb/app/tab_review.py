"""Review tab of the AIDB scene app (board task 102).

Answers throwaway image review lists from the ``review_imgs`` collection
(see ``aidb.review_imgs``; lists are created by agents via
``script/review_list.py``). Reviewing never touches ``images``/``scenes``.

Server side renders one HTML block per list: embedded list JSON (form,
items, responses — ``context`` only when ``show_context``) plus a grid of
cards with base64 thumbnails. Everything interactive lives in REVIEW_HEAD
(injected into <head>, since <script> in gr.HTML does not run):

  * per-card forms rendered from the form spec, fullscreen modal with the
    same form alongside the image (full-res image fetched on demand)
  * keys: 1-9 = first choice field, 0 = clear it, ←/→ j/k = prev/next
    (↑/↓ too inside the modal), Enter/Space = open modal, Esc = close
  * answers are kept dirty in JS and flushed (debounced) through a hidden
    databus + button; the server acks per item/version, un-acked items are
    re-sent, so rapid keying never loses an answer.

All elem_ids / classes are ``rv-``-prefixed and the key handler is inert
unless the Review list is visible (or its modal is open).
"""

from __future__ import annotations

import base64
import html
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gradio as gr
from PIL import Image, ImageOps

from aidb.review_imgs import ReviewImgs, answered_count
from ait.tools.files import is_img

THUMB_SIZE = 384
FULL_SIZE = 2048

ELEM_SAVE_BUS = 'rv-save-bus'
ELEM_SAVE_BTN = 'rv-save-btn'
ELEM_SAVE_OUT = 'rv-save-out'
ELEM_FULL_BUS = 'rv-full-bus'
ELEM_FULL_BTN = 'rv-full-btn'
ELEM_FULL_OUT = 'rv-full-out'


def _jpeg_b64(url: str, size: int, quality: int) -> str | None:
    """Downscaled JPEG as base64, None for missing/unreadable/non-image files."""
    p = Path(url)
    if not is_img(p) or not p.is_file():
        return None
    try:
        with Image.open(p) as src:
            src.draft('RGB', (size, size))
            im = ImageOps.exif_transpose(src).convert('RGB')
            im.thumbnail((size, size))
            buf = io.BytesIO()
            im.save(buf, format='JPEG', quality=quality)
        return base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception:  # noqa: BLE001 - unreadable file -> placeholder, never an error
        return None


class ReviewTab:
    def __init__(self, dbc, verbose: int = 0) -> None:
        self._rv = ReviewImgs(dbc=dbc, verbose=verbose)
        self._verbose = verbose
        self._thumb_cache: dict[tuple, str | None] = {}

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[review:{level}] {msg}')

    # ------------------------------------------------------------------ #
    # rendering
    # ------------------------------------------------------------------ #
    def _choices(self) -> list[tuple[str, str]]:
        return [
            (f'{d["title"]}  [{d["list_id"]}]  {d["answered"]}/{d["total"]}', d['list_id'])
            for d in self._rv.ls()
        ]

    def _thumb(self, url: str) -> str | None:
        try:
            mtime = Path(url).stat().st_mtime
        except OSError:
            return None
        key = (url, mtime)
        if key not in self._thumb_cache:
            if len(self._thumb_cache) > 5000:
                self._thumb_cache.clear()
            self._thumb_cache[key] = _jpeg_b64(url, THUMB_SIZE, 85)
        return self._thumb_cache[key]

    def _render(self, list_id: str | None) -> str:
        if not list_id:
            return '<div class="rv-empty">Select a review list above.</div>'
        doc = self._rv.get(list_id)
        if doc is None:
            return f'<div class="rv-empty">Review list {html.escape(list_id)} not found.</div>'

        items = doc.get('items') or []
        show_ctx = bool(doc.get('show_context'))
        with ThreadPoolExecutor(max_workers=8) as ex:
            thumbs = list(ex.map(lambda it: self._thumb(str(it.get('url', ''))), items))

        data = {
            'list_id': doc['list_id'],
            'title': doc.get('title'),
            'show_context': show_ctx,
            'form': doc['form'],
            'comment': doc.get('comment'),
            'items': [
                {
                    'id': it['id'],
                    'url': it.get('url'),
                    'context': it.get('context') if show_ctx else None,
                    'response': it.get('response'),
                    'has_img': thumbs[i] is not None,
                }
                for i, it in enumerate(items)
            ],
        }
        answered, total = answered_count(doc)
        token = f'{doc["list_id"]}:{time.time_ns()}'

        cards = []
        for i, it in enumerate(items):
            if thumbs[i] is not None:
                img = f'<img src="data:image/jpeg;base64,{thumbs[i]}" loading="lazy">'
            else:
                img = (
                    '<div class="rv-missing">missing / unreadable<br>'
                    f'<span>{html.escape(str(it.get("url", "")))}</span></div>'
                )
            ctx = ''
            if show_ctx and it.get('context'):
                ctx = f'<div class="rv-ctx">{html.escape(str(it["context"]))}</div>'
            cards.append(
                f'<div class="rv-card" id="rv-card-{i}" data-idx="{i}">'
                f'<div class="rv-thumb" data-idx="{i}" title="open fullscreen">{img}</div>'
                f'<div class="rv-meta">#{i + 1} · {html.escape(str(it["id"]))}</div>'
                f'{ctx}'
                f'<div class="rv-form" data-scope="c" data-idx="{i}"></div>'
                '</div>'
            )

        data_attr = html.escape(json.dumps(data, ensure_ascii=False, default=str), quote=True)
        created = html.escape(f'{doc.get("created") or ""} · {doc.get("created_by") or ""}')
        return (
            f'<div id="rv-root" data-token="{html.escape(token)}">'
            f'<div id="rv-json" hidden data-json="{data_attr}"></div>'
            f'<div class="rv-bar">'
            f'<span class="rv-title">{html.escape(str(doc.get("title") or ""))}</span>'
            f'<span class="rv-sub">{created}</span>'
            f'<span id="rv-count">{answered}/{total} answered</span>'
            '<label><input type="checkbox" id="rv-unanswered"> unanswered only</label>'
            '<label><input type="checkbox" id="rv-autoadv"> auto-advance on number key</label>'
            '<span id="rv-status"></span>'
            '</div>'
            '<div class="rv-help">click image = fullscreen · 1-9 = first choice field '
            '(0 clears) · ←/→ or j/k = prev/next · Enter/Space = fullscreen · Esc = close</div>'
            f'<div class="rv-grid">{"".join(cards)}</div>'
            '<div class="rv-comment"><div class="rv-flabel">List comment</div>'
            '<textarea id="rv-list-comment" rows="3"></textarea></div>'
            '</div>'
        )

    # ------------------------------------------------------------------ #
    # handlers
    # ------------------------------------------------------------------ #
    def _on_refresh(self, current: str | None):
        choices = self._choices()
        values = [c[1] for c in choices]
        value = current if current in values else None
        return gr.update(choices=choices, value=value)

    def _on_save(self, payload: str | None) -> str:
        if not payload:
            return ''
        try:
            data = json.loads(payload)
            list_id = data['list_id']
        except (ValueError, KeyError, TypeError):
            return ''
        saved: list[dict] = []
        failed: list[dict] = []
        for u in data.get('updates') or []:
            try:
                ok = self._rv.set_response(list_id, int(u['idx']), str(u['id']), u['response'])
            except Exception as e:  # noqa: BLE001
                self._log(f'save {list_id}[{u.get("idx")}] failed: {e}', 'error')
                ok = False
            (saved if ok else failed).append({'idx': u.get('idx'), 'ver': u.get('ver')})
        out = {'list_id': list_id, 'saved': saved, 'failed': failed}
        if 'comment' in data:
            out['comment_ver'] = data.get('comment_ver')
            out['comment_saved'] = self._rv.set_comment(list_id, data['comment'])
        return json.dumps(out)

    def _on_full(self, payload: str | None) -> str:
        if not payload:
            return ''
        try:
            data = json.loads(payload)
            doc = self._rv.get(data['list_id'])
            assert doc is not None
            url = str(doc['items'][int(data['idx'])]['url'])
        except Exception:  # noqa: BLE001
            return ''
        b64 = _jpeg_b64(url, FULL_SIZE, 92)
        return json.dumps(
            {
                'list_id': data['list_id'],
                'idx': data['idx'],
                'b64': b64,
            }
        )

    # ------------------------------------------------------------------ #
    # UI build (call inside the app's gr.Blocks context)
    # ------------------------------------------------------------------ #
    def build(self) -> None:
        with gr.Tab('Review', elem_id='rv_tab') as tab:
            gr.Markdown(
                'Throwaway image review lists (`review_imgs`). Agents create them with '
                '`script/review_list.py` — cheatsheet: `conf/review/README.md`.'
            )
            with gr.Row():
                # lists created after launch arrive via ↻ / tab select; custom
                # values keep the server-side choice validation out of the way
                dropdown = gr.Dropdown(
                    choices=self._choices(),
                    value=None,
                    allow_custom_value=True,
                    label='Review list (newest first, answered/total)',
                    interactive=True,
                    scale=6,
                )
                refresh_btn = gr.Button('↻ lists', scale=1)
                reload_btn = gr.Button('reload list', scale=1)
            list_html = gr.HTML()

            save_bus = gr.Textbox(visible='hidden', elem_id=ELEM_SAVE_BUS)
            save_btn = gr.Button(visible='hidden', elem_id=ELEM_SAVE_BTN)
            save_out = gr.Textbox(visible='hidden', elem_id=ELEM_SAVE_OUT)
            full_bus = gr.Textbox(visible='hidden', elem_id=ELEM_FULL_BUS)
            full_btn = gr.Button(visible='hidden', elem_id=ELEM_FULL_BTN)
            full_out = gr.Textbox(visible='hidden', elem_id=ELEM_FULL_OUT)

            tab.select(self._on_refresh, [dropdown], [dropdown])
            refresh_btn.click(self._on_refresh, [dropdown], [dropdown])
            dropdown.change(self._render, [dropdown], [list_html])
            reload_btn.click(self._render, [dropdown], [list_html])

            # every flush must reach the server (acks drive the JS dirty map)
            save_btn.click(
                self._on_save,
                [save_bus],
                [save_out],
                trigger_mode='multiple',
                show_progress='hidden',
            ).then(
                fn=None,
                inputs=[save_out],
                outputs=None,
                js='(s) => { if (window.rvOnSaved) window.rvOnSaved(s); }',
            )
            # only the latest full-image request matters
            full_btn.click(
                self._on_full,
                [full_bus],
                [full_out],
                trigger_mode='always_last',
                show_progress='hidden',
            ).then(
                fn=None,
                inputs=[full_out],
                outputs=None,
                js='(s) => { if (window.rvOnFull) window.rvOnFull(s); }',
            )


# --------------------------------------------------------------------------- #
# front-end JS + CSS, injected into <head> by AIDBSceneApp.launch
# --------------------------------------------------------------------------- #

REVIEW_HEAD = r"""
<style>
#rv-save-bus, #rv-save-out, #rv-full-bus, #rv-full-out,
#rv-save-btn, #rv-full-btn { display: none !important; }
#rv-root { --rv-ok: #2ea043; --rv-cur: #1f6feb; --rv-line: rgba(128,128,128,0.45); }
#rv-root .rv-bar { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; margin: 4px 0; }
#rv-root .rv-title { font-weight: 600; font-size: 1.1em; }
#rv-root .rv-sub, .rv-help { opacity: 0.7; font-size: 0.85em; }
#rv-count { font-weight: 600; }
#rv-status { font-size: 0.85em; opacity: 0.8; }
#rv-status.rv-err { color: #f85149; opacity: 1; font-weight: 600; }
#rv-root .rv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 10px; margin-top: 8px; }
#rv-root .rv-card { border: 2px solid var(--rv-line); border-radius: 6px; padding: 6px;
  display: flex; flex-direction: column; gap: 4px; }
#rv-root .rv-card.rv-answered { border-color: var(--rv-ok); }
#rv-root .rv-card.rv-cur { outline: 3px solid var(--rv-cur); outline-offset: 1px; }
#rv-root .rv-card.rv-hide { display: none; }
#rv-root .rv-thumb { cursor: zoom-in; display: flex; justify-content: center; align-items: center;
  min-height: 120px; background: rgba(0,0,0,0.25); border-radius: 4px; }
#rv-root .rv-thumb img { max-width: 100%; max-height: 320px; object-fit: contain; }
.rv-missing { padding: 16px; text-align: center; color: #d29922; font-size: 0.85em;
  word-break: break-all; }
.rv-missing span { opacity: 0.7; }
#rv-root .rv-meta { font-size: 0.85em; opacity: 0.8; }
.rv-ctx { font-size: 0.85em; white-space: pre-wrap; background: rgba(128,128,128,0.15);
  border-radius: 4px; padding: 4px 6px; }
.rv-field { margin: 3px 0; }
.rv-flabel { font-size: 0.8em; opacity: 0.75; margin-bottom: 2px; }
.rv-opts { display: flex; flex-wrap: wrap; gap: 4px; }
.rv-opt { border: 1px solid var(--rv-line, #666); border-radius: 4px; padding: 2px 8px;
  background: transparent; color: inherit; cursor: pointer; font-size: 0.9em; }
.rv-opt:hover { border-color: #1f6feb; }
.rv-opt.rv-on { background: #1f6feb; border-color: #1f6feb; color: #fff; }
.rv-opt .rv-k { opacity: 0.6; margin-right: 3px; font-size: 0.85em; }
.rv-text { width: 100%; box-sizing: border-box; font-size: 0.9em; background: transparent;
  color: inherit; border: 1px solid var(--rv-line, #666); border-radius: 4px; padding: 3px; }
#rv-root .rv-comment { margin-top: 14px; }
#rv-list-comment { width: 100%; box-sizing: border-box; background: transparent; color: inherit;
  border: 1px solid var(--rv-line); border-radius: 4px; padding: 4px; }
.rv-empty { opacity: 0.7; padding: 12px; }
#rv-modal { position: fixed; inset: 0; z-index: 10000; background: rgba(0,0,0,0.93);
  display: flex; color: #eee; }
#rv-modal.rv-hidden { display: none; }
#rv-modal .rv-m-img { flex: 1; display: flex; align-items: center; justify-content: center;
  min-width: 0; padding: 10px; }
#rv-modal .rv-m-img img { max-width: 100%; max-height: calc(100vh - 20px); object-fit: contain; }
#rv-modal .rv-m-side { width: 360px; flex: none; background: #161b22; padding: 14px;
  overflow-y: auto; display: flex; flex-direction: column; gap: 8px; --rv-line: #555; }
#rv-modal .rv-m-head { display: flex; justify-content: space-between; align-items: center;
  font-weight: 600; }
#rv-m-close { cursor: pointer; font-size: 28px; line-height: 1; padding: 0 6px; }
#rv-m-close:hover { color: #f85149; }
#rv-m-id { font-size: 0.85em; opacity: 0.8; word-break: break-all; }
#rv-m-state { font-size: 0.85em; }
#rv-m-state.rv-ok { color: #2ea043; }
#rv-modal .rv-help { color: #aaa; }
</style>
<script>
(function(){
  const RV = { data: null, token: null, resp: [], ver: [], dirty: {}, cur: 0,
               comment: null, commentVer: 0, commentDirty: false,
               modal: false, full: {}, fullOrder: [], timer: null, inflight: 0,
               lastSend: 0, numKey: null };
  window.__rv = RV;

  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function root(){ return document.getElementById('rv-root'); }
  function listVisible(){ const r = root(); return !!(r && r.offsetParent !== null); }
  function active(){ return RV.data && (RV.modal || listVisible()); }
  function n(){ return RV.data ? RV.data.items.length : 0; }
  function field(key){ return RV.data.form.find(f => f.key === key); }
  function lsGet(k, d){ try { const v = localStorage.getItem(k); return v === null ? d : v === '1'; }
                        catch(_) { return d; } }
  function lsSet(k, v){ try { localStorage.setItem(k, v ? '1' : '0'); } catch(_) {} }

  function answered(i){
    const r = RV.resp[i]; if (!r) return false;
    return Object.values(r).some(v => !(v === null || v === '' || (Array.isArray(v) && !v.length)));
  }
  function nAnswered(){ let c = 0; for (let i = 0; i < n(); i++) if (answered(i)) c++; return c; }

  // ---------------- bridge to python ----------------
  function send(busId, btnId, payload){
    const t = document.querySelector('#' + busId + ' textarea');
    const b = document.getElementById(btnId);
    if (!t || !b) return false;
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    setter.call(t, JSON.stringify(payload));
    t.dispatchEvent(new Event('input', {bubbles: true}));
    b.click();
    return true;
  }
  function status(msg, err){
    const s = document.getElementById('rv-status');
    if (s) { s.textContent = msg; s.classList.toggle('rv-err', !!err); }
    const m = document.getElementById('rv-m-state');
    if (m) { m.textContent = msg; m.className = err ? 'rv-err' : (msg === 'saved' ? 'rv-ok' : ''); }
  }
  function schedule(ms){ clearTimeout(RV.timer); RV.timer = setTimeout(flush, ms == null ? 250 : ms); }
  function flush(){
    if (!RV.data) return;
    const updates = Object.keys(RV.dirty).map(k => {
      const i = +k;
      return { idx: i, id: RV.data.items[i].id, response: RV.resp[i], ver: RV.ver[i] };
    });
    if (!updates.length && !RV.commentDirty) return;
    const payload = { list_id: RV.data.list_id, updates: updates };
    if (RV.commentDirty) { payload.comment = RV.comment; payload.comment_ver = RV.commentVer; }
    if (send('rv-save-bus', 'rv-save-btn', payload)) {
      RV.inflight++; RV.lastSend = Date.now(); status('saving…');
    }
  }
  window.rvOnSaved = function(s){
    RV.inflight = Math.max(0, RV.inflight - 1);
    if (!s) return;
    let d; try { d = JSON.parse(s); } catch(_) { return; }
    if (!RV.data || d.list_id !== RV.data.list_id) return;
    (d.saved || []).forEach(u => { if (RV.ver[u.idx] === u.ver) delete RV.dirty[u.idx]; });
    if (d.comment_saved && d.comment_ver === RV.commentVer) RV.commentDirty = false;
    if ((d.failed || []).length) {
      (d.failed || []).forEach(u => { if (RV.ver[u.idx] === u.ver) delete RV.dirty[u.idx]; });
      status('save FAILED for ' + d.failed.map(u => '#' + (u.idx + 1)).join(', ') + ' — reload list', true);
      return;
    }
    if (Object.keys(RV.dirty).length || RV.commentDirty) schedule(100);
    else if (!RV.inflight) status('saved');
  };
  // safety net: re-send anything un-acked for >3s (lost event, server hiccup)
  setInterval(() => {
    if (!RV.data) return;
    if ((Object.keys(RV.dirty).length || RV.commentDirty) && Date.now() - RV.lastSend > 3000) flush();
  }, 1000);

  // ---------------- forms ----------------
  function formHtml(i, scope){
    const r = RV.resp[i] || {};
    let h = '';
    RV.data.form.forEach(f => {
      const k = esc(f.key), v = r[f.key];
      h += '<div class="rv-field"><div class="rv-flabel">' + esc(f.label || f.key) + '</div>';
      if (f.type === 'text') {
        h += '<textarea class="rv-text" rows="2" data-scope="' + scope + '" data-idx="' + i +
             '" data-key="' + k + '">' + esc(v || '') + '</textarea>';
      } else {
        const opts = f.type === 'bool' ? [['true', 'yes'], ['false', 'no']]
                                       : f.options.map(o => [o, o]);
        const num = f.key === RV.numKey;
        h += '<div class="rv-opts">';
        opts.forEach((o, j) => {
          let on;
          if (f.type === 'bool') on = (v === true && o[0] === 'true') || (v === false && o[0] === 'false');
          else if (f.type === 'multi') on = Array.isArray(v) && v.includes(o[0]);
          else on = v === o[0];
          h += '<button type="button" class="rv-opt' + (on ? ' rv-on' : '') + '" data-idx="' + i +
               '" data-key="' + k + '" data-val="' + esc(o[0]) + '">' +
               (num && j < 9 ? '<span class="rv-k">' + (j + 1) + '</span>' : '') + esc(o[1]) + '</button>';
        });
        h += '</div>';
      }
      h += '</div>';
    });
    return h;
  }
  function renderItem(i){
    const f = document.querySelector('#rv-root .rv-form[data-scope="c"][data-idx="' + i + '"]');
    if (f) f.innerHTML = formHtml(i, 'c');
    const card = document.getElementById('rv-card-' + i);
    if (card) card.classList.toggle('rv-answered', answered(i));
    if (RV.modal && RV.cur === i) document.getElementById('rv-m-form').innerHTML = formHtml(i, 'm');
    counter();
  }
  function counter(){
    const txt = nAnswered() + '/' + n() + ' answered';
    const c = document.getElementById('rv-count'); if (c) c.textContent = txt;
    const m = document.getElementById('rv-m-count'); if (m) m.textContent = txt;
  }
  function setValue(i, key, v, rerender){
    const r = Object.assign({}, RV.resp[i] || {});
    r[key] = v; RV.resp[i] = r;
    RV.ver[i] = (RV.ver[i] || 0) + 1; RV.dirty[i] = true;
    if (rerender) renderItem(i);
    else { const card = document.getElementById('rv-card-' + i);
           if (card) card.classList.toggle('rv-answered', answered(i)); counter(); }
  }
  function clickOpt(i, key, val){
    const f = field(key); if (!f) return;
    const cur = (RV.resp[i] || {})[key];
    let v;
    if (f.type === 'bool') { const b = val === 'true'; v = cur === b ? null : b; }
    else if (f.type === 'choice') v = cur === val ? null : val;
    else if (f.type === 'multi') {
      const a = Array.isArray(cur) ? cur.slice() : [];
      const j = a.indexOf(val); if (j >= 0) a.splice(j, 1); else a.push(val);
      v = f.options.filter(o => a.includes(o));
    }
    setValue(i, key, v, true); schedule();
  }

  // ---------------- navigation / filter ----------------
  function visible(i){ return !(RV.unanswered && answered(i) && i !== RV.cur); }
  function applyFilter(){
    for (let i = 0; i < n(); i++) {
      const c = document.getElementById('rv-card-' + i);
      if (c) c.classList.toggle('rv-hide', !visible(i));
    }
  }
  function setCur(i, scroll){
    if (!RV.data || i < 0 || i >= n()) return;
    const old = document.getElementById('rv-card-' + RV.cur); if (old) old.classList.remove('rv-cur');
    RV.cur = i;
    const c = document.getElementById('rv-card-' + i);
    if (RV.unanswered) applyFilter();
    if (c) { c.classList.add('rv-cur'); if (scroll && !RV.modal) c.scrollIntoView({block: 'nearest'}); }
    if (RV.modal) fillModal();
  }
  function step(d){
    for (let i = RV.cur + d; i >= 0 && i < n(); i += d) {
      if (!(RV.unanswered && answered(i))) { setCur(i, true); return; }
    }
  }

  // ---------------- modal ----------------
  function ensureModal(){
    let m = document.getElementById('rv-modal');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'rv-modal'; m.className = 'rv-hidden';
    m.innerHTML =
      '<div class="rv-m-img"><img id="rv-m-img" alt=""><div id="rv-m-missing" class="rv-missing"></div></div>' +
      '<div class="rv-m-side">' +
        '<div class="rv-m-head"><span id="rv-m-pos"></span><span id="rv-m-close" title="close (Esc)">&times;</span></div>' +
        '<div id="rv-m-id"></div><div id="rv-m-count"></div>' +
        '<div id="rv-m-ctx" class="rv-ctx"></div>' +
        '<div id="rv-m-form" class="rv-form" data-scope="m"></div>' +
        '<div id="rv-m-state"></div>' +
        '<div class="rv-help">1-9 = first choice field (0 clears) · ←/→ ↑/↓ j/k = prev/next · Esc = close</div>' +
      '</div>';
    document.body.appendChild(m);
    return m;
  }
  function fillModal(){
    const i = RV.cur, it = RV.data.items[i];
    document.getElementById('rv-m-pos').textContent = '#' + (i + 1) + ' / ' + n();
    document.getElementById('rv-m-id').textContent = it.id;
    const ctx = document.getElementById('rv-m-ctx');
    ctx.textContent = it.context || '';
    ctx.style.display = (RV.data.show_context && it.context) ? '' : 'none';
    document.getElementById('rv-m-form').innerHTML = formHtml(i, 'm');
    counter();
    const img = document.getElementById('rv-m-img'), miss = document.getElementById('rv-m-missing');
    if (!it.has_img) {
      img.style.display = 'none'; img.removeAttribute('src');
      miss.style.display = ''; miss.innerHTML = 'missing / unreadable<br><span>' + esc(it.url) + '</span>';
      return;
    }
    miss.style.display = 'none'; img.style.display = '';
    if (RV.full[i]) { img.src = RV.full[i]; return; }
    const th = document.querySelector('#rv-card-' + i + ' .rv-thumb img');
    if (th) img.src = th.src;
    send('rv-full-bus', 'rv-full-btn', { list_id: RV.data.list_id, idx: i });
  }
  window.rvOnFull = function(s){
    if (!s || !RV.data) return;
    let d; try { d = JSON.parse(s); } catch(_) { return; }
    if (d.list_id !== RV.data.list_id || !d.b64) return;
    RV.full[d.idx] = 'data:image/jpeg;base64,' + d.b64;
    RV.fullOrder.push(d.idx);
    while (RV.fullOrder.length > 30) delete RV.full[RV.fullOrder.shift()];
    if (RV.modal && RV.cur === d.idx) document.getElementById('rv-m-img').src = RV.full[d.idx];
  };
  function openModal(i){
    ensureModal().classList.remove('rv-hidden');
    RV.modal = true; setCur(i, false); fillModal();
  }
  function closeModal(){
    const m = document.getElementById('rv-modal'); if (m) m.classList.add('rv-hidden');
    RV.modal = false;
    const c = document.getElementById('rv-card-' + RV.cur);
    if (RV.unanswered) applyFilter();
    if (c) c.scrollIntoView({block: 'nearest'});
  }

  // ---------------- init on each (re)render ----------------
  function init(r){
    if (RV.data) flush();   // push anything pending for the previous list
    let data; try { data = JSON.parse(document.getElementById('rv-json').dataset.json); }
    catch(_) { return; }
    RV.token = r.dataset.token; RV.data = data;
    RV.resp = data.items.map(it => it.response || null);
    RV.ver = data.items.map(() => 0);
    RV.dirty = {}; RV.full = {}; RV.fullOrder = []; RV.cur = 0;
    RV.comment = data.comment || ''; RV.commentVer = 0; RV.commentDirty = false;
    const nf = data.form.find(f => f.type === 'choice') || data.form.find(f => f.type === 'bool');
    RV.numKey = nf ? nf.key : null;
    for (let i = 0; i < n(); i++) renderItem(i);
    const cm = document.getElementById('rv-list-comment'); if (cm) cm.value = RV.comment;
    const un = document.getElementById('rv-unanswered'), aa = document.getElementById('rv-autoadv');
    RV.unanswered = lsGet('rv-unanswered', false); RV.autoadv = lsGet('rv-autoadv', true);
    if (un) un.checked = RV.unanswered;
    if (aa) aa.checked = RV.autoadv;
    let first = 0;
    if (RV.unanswered) { while (first < n() - 1 && answered(first)) first++; }
    setCur(first, false); applyFilter();
    if (RV.modal) closeModal();
    status('');
  }
  setInterval(() => {
    const r = root();
    if (r && r.dataset.token !== RV.token) init(r);
    else if (!r && RV.data) { flush(); RV.data = null; RV.token = null; if (RV.modal) closeModal(); }
  }, 250);

  // ---------------- events ----------------
  document.addEventListener('click', e => {
    if (!RV.data) return;
    const b = e.target.closest('.rv-opt');
    if (b) { e.preventDefault(); const i = +b.dataset.idx; if (i !== RV.cur) setCur(i, false);
             clickOpt(i, b.dataset.key, b.dataset.val); return; }
    if (e.target.id === 'rv-m-close' || e.target.id === 'rv-modal' ||
        (e.target.classList && e.target.classList.contains('rv-m-img'))) { closeModal(); return; }
    const th = e.target.closest('#rv-root .rv-thumb');
    if (th) { openModal(+th.dataset.idx); return; }
    const card = e.target.closest('#rv-root .rv-card');
    if (card) setCur(+card.dataset.idx, false);
  });
  document.addEventListener('change', e => {
    if (!RV.data) return;
    if (e.target.id === 'rv-unanswered') { RV.unanswered = e.target.checked; lsSet('rv-unanswered', RV.unanswered); applyFilter(); }
    if (e.target.id === 'rv-autoadv') { RV.autoadv = e.target.checked; lsSet('rv-autoadv', RV.autoadv); }
  });
  document.addEventListener('input', e => {
    if (!RV.data) return;
    const t = e.target;
    if (t.id === 'rv-list-comment') {
      RV.comment = t.value; RV.commentVer++; RV.commentDirty = true; schedule(600); return;
    }
    if (!t.classList || !t.classList.contains('rv-text')) return;
    const i = +t.dataset.idx, key = t.dataset.key;
    setValue(i, key, t.value, false);
    const other = document.querySelector('.rv-text[data-scope="' + (t.dataset.scope === 'm' ? 'c' : 'm') +
      '"][data-idx="' + i + '"][data-key="' + key + '"]');
    if (other) other.value = t.value;
    schedule(600);
  });
  document.addEventListener('keydown', e => {
    if (!active()) return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'textarea' || tag === 'input' || tag === 'select' || e.target.isContentEditable) {
      if (e.key === 'Escape' && RV.modal && e.target.closest('#rv-modal')) e.target.blur();
      return;
    }
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    const k = e.key;
    let handled = true;
    if (k === 'Escape') { if (RV.modal) closeModal(); else handled = false; }
    else if (k === 'ArrowRight' || k === 'j' || (RV.modal && k === 'ArrowDown')) step(1);
    else if (k === 'ArrowLeft' || k === 'k' || (RV.modal && k === 'ArrowUp')) step(-1);
    else if ((k === 'Enter' || k === ' ') && !RV.modal) openModal(RV.cur);
    else if (/^[0-9]$/.test(k) && RV.numKey) {
      const f = field(RV.numKey);
      if (k === '0') { setValue(RV.cur, f.key, null, true); schedule(); }
      else {
        const opts = f.type === 'bool' ? ['true', 'false'] : f.options;
        const val = opts[+k - 1];
        if (val === undefined) handled = false;
        else {
          const i = RV.cur, v = f.type === 'bool' ? val === 'true' : val;
          setValue(i, f.key, v, true); schedule();
          if (RV.autoadv) setTimeout(() => { if (RV.cur === i) step(1); }, 120);
        }
      }
    }
    else handled = false;
    if (handled) { e.preventDefault(); e.stopPropagation(); }
  }, true);
  window.addEventListener('beforeunload', () => { if (RV.data) flush(); });
})();
</script>
"""
