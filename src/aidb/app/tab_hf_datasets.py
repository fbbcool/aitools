"""HF datasets tab of the AIDB scene app.

Browse the operator's active Hugging Face dataset repos (``hf_datasets``
collection, see ``aidb.hf_datasets``): pick one from the dropdown and its
media files are pulled into the local HF cache and shown as a grid of cells.
Per cell, ``url`` copies the local HF-cache path, ``cap`` the caption and
``smartO`` a SmartInput comfy-node payload (url + caption) to the clipboard.
Datasets are added by url / repo id and deleted from the list (the HF cache
itself is left alone).

The copy handler lives in HF_DATASETS_HEAD (injected into <head>, since
<script> in gr.HTML does not run); values ride on ``data-v`` attributes.
All elem_ids / classes are ``hfds-``-prefixed.
"""

from __future__ import annotations

import html
import json
from concurrent.futures import ThreadPoolExecutor

import gradio as gr

from aidb.app.tab_review import _jpeg_b64
from aidb.hf_datasets import HFDatasetLocal, HFDatasetsActive

THUMB_SIZE = 320

# Flat (legacy) enhancer payload: the comfy SmartInput node recognizes it by the
# schema_id prefix, loads the image from `url` and emits `prompt` verbatim.
SMARTO_SCHEMA_ID = '1xlasm_enhancer.iteration'


def smarto_payload(url: str, caption: str | None) -> str:
    return json.dumps(
        {'schema_id': SMARTO_SCHEMA_ID, 'url': url, 'prompt': caption or ''},
        ensure_ascii=False,
    )


class HFDatasetsTab:
    def __init__(self, dbc, verbose: int = 0) -> None:
        self._hfa = HFDatasetsActive(dbc=dbc, verbose=verbose)
        self._verbose = verbose
        self._datasets: dict[str, HFDatasetLocal] = {}
        self._thumb_cache: dict[str, str | None] = {}

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[hf_datasets_tab:{level}] {msg}')

    def _thumb(self, url: str) -> str | None:
        if url not in self._thumb_cache:
            self._thumb_cache[url] = _jpeg_b64(url, THUMB_SIZE, 85)
        return self._thumb_cache[url]

    def _dataset(self, repo_id: str, reload: bool = False) -> HFDatasetLocal:
        # snapshot_download hits the hub on every call -> keep it per session
        if reload or repo_id not in self._datasets:
            self._datasets[repo_id] = HFDatasetLocal(repo_id)
        return self._datasets[repo_id]

    # ------------------------------------------------------------------ #
    # rendering
    # ------------------------------------------------------------------ #
    @staticmethod
    def _copy_btn(label: str, value: str | None, title: str) -> str:
        if not value:
            return f'<button type="button" class="hfds-copy" disabled>{label}</button>'
        v = html.escape(value, quote=True)
        return (
            f'<button type="button" class="hfds-copy" data-v="{v}" title="{title}">{label}</button>'
        )

    def _render(self, repo_id: str | None, reload: bool = False) -> str:
        if not repo_id:
            return '<div class="hfds-empty">Select a dataset above.</div>'
        try:
            ds = self._dataset(repo_id, reload=reload)
        except Exception as e:  # noqa: BLE001
            self._log(f'load {repo_id} failed: {e}', 'error')
            return f'<div class="hfds-empty">Loading {html.escape(repo_id)} failed: {html.escape(str(e))}</div>'

        with ThreadPoolExecutor(max_workers=8) as ex:
            thumbs = list(ex.map(lambda it: self._thumb(it['url']), ds.items))

        cells = []
        for i, it in enumerate(ds.items):
            name = it['url'].rsplit('/', 1)[-1]
            if thumbs[i] is not None:
                img = f'<img src="data:image/jpeg;base64,{thumbs[i]}" loading="lazy">'
            else:
                img = f'<div class="hfds-missing">no preview<br><span>{html.escape(name)}</span></div>'
            cap = it['caption']
            cap_title = html.escape(cap, quote=True) if cap else 'no caption'
            cells.append(
                '<div class="hfds-cell">'
                f'<div class="hfds-thumb" title="{cap_title}">{img}</div>'
                f'<div class="hfds-meta"><span class="hfds-name">#{i + 1} · {html.escape(name)}</span>'
                + self._copy_btn('url', it['url'], 'copy local HF-cache path')
                + self._copy_btn('cap', cap, 'copy caption')
                + self._copy_btn(
                    'smartO',
                    smarto_payload(it['url'], cap),
                    'copy SmartInput payload (url+caption)',
                )
                + '</div></div>'
            )
        n_cap = sum(1 for it in ds.items if it['caption'])
        return (
            '<div id="hfds-root">'
            f'<div class="hfds-bar"><b>{html.escape(repo_id)}</b> · {len(ds)} files · '
            f'{n_cap} captioned · <span class="hfds-path">{html.escape(str(ds.root))}</span></div>'
            f'<div class="hfds-grid">{"".join(cells)}</div>'
            '</div>'
        )

    # ------------------------------------------------------------------ #
    # handlers
    # ------------------------------------------------------------------ #
    def _on_refresh(self, current: str | None):
        choices = self._hfa.repo_ids
        return gr.update(choices=choices, value=current if current in choices else None)

    def _on_add(self, url: str | None):
        try:
            repo_id = self._hfa.add(url or '')
        except ValueError as e:
            return gr.update(), gr.update(), f'⚠ {e}'
        return gr.update(choices=self._hfa.repo_ids, value=repo_id), '', f'added {repo_id}'

    # repo_id arrives only after the JS confirm(); None = cancelled
    def _on_delete(self, repo_id: str | None):
        if not repo_id:
            return gr.update(), gr.update(), ''
        self._hfa.delete(repo_id)
        self._datasets.pop(repo_id, None)
        return self._on_refresh(None), self._render(None), f'removed {repo_id} from the active list'

    # ------------------------------------------------------------------ #
    # UI build (call inside the app's gr.Blocks context)
    # ------------------------------------------------------------------ #
    def build(self) -> None:
        with gr.Tab('HF datasets', elem_id='hfds_tab') as tab:
            dropdown = gr.Dropdown(
                choices=self._hfa.repo_ids,
                value=None,
                allow_custom_value=True,
                label='Active HF dataset',
                interactive=True,
            )
            with gr.Row():
                refresh_btn = gr.Button('↻ list', scale=1)
                reload_btn = gr.Button('reload dataset (re-sync from hub)', scale=1)
                delete_btn = gr.Button('delete from list', variant='stop', scale=1)
            with gr.Row():
                add_box = gr.Textbox(
                    placeholder='https://huggingface.co/datasets/<org>/<name>  or  <org>/<name>',
                    show_label=False,
                    scale=4,
                )
                add_btn = gr.Button('add', scale=1)
            status = gr.Markdown()
            grid_html = gr.HTML()

            tab.select(self._on_refresh, [dropdown], [dropdown])
            refresh_btn.click(self._on_refresh, [dropdown], [dropdown])
            dropdown.change(self._render, [dropdown], [grid_html])
            reload_btn.click(lambda r: self._render(r, reload=True), [dropdown], [grid_html])
            add_btn.click(self._on_add, [add_box], [dropdown, add_box, status])
            add_box.submit(self._on_add, [add_box], [dropdown, add_box, status])
            delete_btn.click(
                self._on_delete,
                [dropdown],
                [dropdown, grid_html, status],
                js='(r) => (r && confirm("Remove " + r + " from the active list?")) ? r : null',
            )


HF_DATASETS_HEAD = r"""
<style>
#hfds-root .hfds-bar { margin: 4px 0 8px; font-size: 0.95em; }
#hfds-root .hfds-path { opacity: 0.6; font-family: monospace; font-size: 0.85em; }
#hfds-root .hfds-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px; }
#hfds-root .hfds-cell { border: 1px solid var(--border-color-primary); border-radius: 6px;
  padding: 6px; display: flex; flex-direction: column; gap: 4px; }
#hfds-root .hfds-thumb { display: flex; align-items: center; justify-content: center;
  aspect-ratio: 1; overflow: hidden; }
#hfds-root .hfds-thumb img { max-width: 100%; max-height: 100%; object-fit: contain; }
#hfds-root .hfds-missing { opacity: 0.6; text-align: center; font-size: 0.85em; }
#hfds-root .hfds-meta { display: flex; align-items: center; gap: 4px; font-size: 0.8em; }
#hfds-root .hfds-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#hfds-root .hfds-copy { padding: 1px 8px; border: 1px solid var(--border-color-primary);
  border-radius: 4px; cursor: pointer; }
#hfds-root .hfds-copy:disabled { opacity: 0.35; cursor: default; }
#hfds-root .hfds-copy.hfds-copied { background: #2e7d32; color: #fff; }
</style>
<script>
(() => {
  // navigator.clipboard needs a secure context (LAN http has none) -> textarea fallback
  function copy(btn){
    const v = btn.dataset.v; if (!v) return;
    const label = btn.textContent;
    const ok = () => { btn.classList.add('hfds-copied'); btn.textContent = 'copied';
      setTimeout(() => { btn.classList.remove('hfds-copied'); btn.textContent = label; }, 900); };
    const fallback = () => {
      const ta = document.createElement('textarea');
      ta.value = v; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { if (document.execCommand('copy')) ok(); } catch(_) {}
      ta.remove();
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(v).then(ok).catch(fallback);
    else fallback();
  }
  document.addEventListener('click', (e) => {
    const btn = e.target.closest && e.target.closest('#hfds-root .hfds-copy');
    if (btn && !btn.disabled) { e.preventDefault(); copy(btn); }
  });
})();
</script>
"""
