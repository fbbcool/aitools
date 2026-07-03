"""Streaming LoKr-into-bf16 merge (krea2 learning base).

Bakes an ai-toolkit / LyCORIS **LoKr** adapter into a bf16 transformer to make a
merged training base — the krea2 analogue of `qwen-image-2512-snofs0.65`.

LoKr math (mirrors ComfyUI `comfy/weight_adapter/lokr.py::calculate_weight`):
for a module with FULL factors `lokr_w1` and `lokr_w2` (no `_a`/`_b`/tucker
decomposition), `dim` is None so the stored `alpha` is IGNORED (alpha == 1.0).
The delta is therefore just the Kronecker product, scaled only by strength:

    delta = torch.kron(w1, w2).reshape(W.shape)
    W_new = W + STRENGTH * delta

Streams one base tensor at a time, so peak RAM is bounded by the largest single
weight's fp32 materialisation (~0.4 GB here) plus the small LoKr factor set
(~1.6 GB), NOT the 26 GB model. Output is all-bf16.

Usage: edit the constants below and run.
"""
import gc
import json
import os
import struct
import time
from pathlib import Path

import torch
from safetensors import safe_open

# ── inputs (override via env: MERGE_BASE / MERGE_LORA / MERGE_OUT / MERGE_STRENGTH) ──
BASE_BF16 = Path(os.environ.get(
    'MERGE_BASE',
    '/home/misw/.cache/huggingface/hub/models--comfy-org--krea-2/snapshots/'
    '8038ce89b91b042141541ad0fa51b985ca262c5f/diffusion_models/krea2_raw_bf16.safetensors'
))
LORA = Path(os.environ.get(
    'MERGE_LORA', '/home/misw/venv/comfy2/ComfyUI/models/loras/krea2/snofs_krea_v1.safetensors'))

# ── output ─────────────────────────────────────────────────────────────────
OUT = Path(os.environ.get(
    'MERGE_OUT',
    '/home/misw/venv/comfy2/ComfyUI/models/diffusion_models/krea2/raw/'
    'krea2-raw-snofs0.75-bf16.safetensors'
))

# ── merge config ───────────────────────────────────────────────────────────
STRENGTH = float(os.environ.get('MERGE_STRENGTH', '0.75'))

SAFETENSORS_DTYPE = {
    torch.bfloat16: 'BF16',
    torch.float16: 'F16',
    torch.float32: 'F32',
}
# name -> (torch dtype, bytes per element). The base keeps norm/1-D params in
# F32 and linears in BF16; we PRESERVE each tensor's native dtype so those
# high-precision params are copied verbatim (only the merged linears change).
DTYPE_FROM_NAME = {
    'F32': (torch.float32, 4),
    'F16': (torch.float16, 2),
    'BF16': (torch.bfloat16, 2),
}


def load_lokr(path: Path) -> dict[str, tuple[torch.Tensor, torch.Tensor]]:
    """base_weight_key -> (w1, w2). Asserts pure full-form (no _a/_b/t2)."""
    pairs: dict[str, tuple[torch.Tensor, torch.Tensor]] = {}
    with safe_open(path, framework='pt') as f:
        keys = set(f.keys())
        decomposed = [k for k in keys if k.endswith(
            ('.lokr_w1_a', '.lokr_w1_b', '.lokr_w2_a', '.lokr_w2_b', '.lokr_t2'))]
        if decomposed:
            raise SystemExit(
                f'LoKr has decomposed factors ({len(decomposed)} tensors, e.g. '
                f'{decomposed[0]}); this script only handles full w1/w2. Aborting.')
        for k in keys:
            if not k.endswith('.lokr_w1'):
                continue
            module = k[: -len('.lokr_w1')]
            w2_k = f'{module}.lokr_w2'
            if w2_k not in keys:
                raise SystemExit(f'{module}: lokr_w1 without lokr_w2')
            base_k = module.removeprefix('diffusion_model.') + '.weight'
            pairs[base_k] = (f.get_tensor(k), f.get_tensor(w2_k))
    return pairs


def main() -> None:
    t_start = time.time()
    print(f'strength: {STRENGTH}  (full-form LoKr -> alpha ignored, matches ComfyUI)')
    if not BASE_BF16.exists():
        raise SystemExit(f'base not found (still downloading?): {BASE_BF16}')
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # 1. Load LoKr factors (small)
    print(f'\n[1/3] loading LoKr factors from {LORA.name} ...')
    lokr = load_lokr(LORA)
    print(f'    {len(lokr)} full-form LoKr modules')

    # 2. First pass: build the all-bf16 header (no tensor data held)
    print(f'\n[2/3] header build from {BASE_BF16.name} ...')
    entries: dict[str, dict] = {}
    order: list[str] = []
    src_dtype: dict[str, str] = {}
    off = 0
    with safe_open(BASE_BF16, framework='pt') as f:
        base_keys = set(f.keys())
        for k in f.keys():
            sl = f.get_slice(k)
            shape = list(sl.get_shape())
            dname = sl.get_dtype()  # preserve native dtype (F32 norms, BF16 linears)
            _, nbytes = DTYPE_FROM_NAME[dname]
            n = 1
            for s in shape:
                n *= s
            entries[k] = {'dtype': dname, 'shape': shape,
                          'data_offsets': [off, off + n * nbytes]}
            src_dtype[k] = dname
            order.append(k)
            off += n * nbytes
    missing = [bk for bk in lokr if bk not in base_keys]
    if missing:
        raise SystemExit(f'{len(missing)} LoKr targets absent in base, e.g. {missing[:3]}')
    print(f'    {len(order)} tensors, {off / 1e9:.2f} GB data section; '
          f'all {len(lokr)} LoKr targets present in base')

    hdr = dict(entries)
    hdr['__metadata__'] = {
        'format': 'pt',
        'merged_from': f'{BASE_BF16.name} + {LORA.name}@{STRENGTH}',
        'merge_type': 'lokr_full_kron',
        'lora_strength': str(STRENGTH),
    }
    hb = json.dumps(hdr, separators=(',', ':')).encode('utf-8')
    hb += b' ' * ((8 - (len(hb) % 8)) % 8)

    # 3. Stream the merge
    print(f'\n[3/3] streaming merge -> {OUT} ...')
    n_merged = n_copy = 0
    last = time.time()
    with open(OUT, 'wb') as out:
        out.write(struct.pack('<Q', len(hb)))
        out.write(hb)
        with safe_open(BASE_BF16, framework='pt') as f:
            for i, k in enumerate(order):
                dt, _ = DTYPE_FROM_NAME[src_dtype[k]]
                t = f.get_tensor(k)
                if k in lokr:
                    w1, w2 = lokr[k]
                    delta = torch.kron(w1.float(), w2.float()).reshape(t.shape)
                    if delta.shape != t.shape:
                        raise SystemExit(f'{k}: kron {tuple(delta.shape)} != {tuple(t.shape)}')
                    t = (t.float() + STRENGTH * delta).to(dt)  # back to native dtype
                    del delta
                    n_merged += 1
                else:
                    t = t.to(dt)  # identity: copied verbatim in native dtype
                    n_copy += 1
                out.write(t.contiguous().cpu().view(torch.uint8).numpy().tobytes())
                del t
                if (i + 1) % 100 == 0:
                    gc.collect()
                if time.time() - last > 5.0:
                    el = time.time() - t_start
                    rate = (i + 1) / max(el, 0.1)
                    print(f'    {i+1:4d}/{len(order)}  merged={n_merged} copy={n_copy}  '
                          f'eta={(len(order)-i-1)/max(rate,1e-3):.0f}s')
                    last = time.time()

    print(f'\n✓ done in {time.time()-t_start:.1f}s')
    print(f'  lokr-merged: {n_merged}   copy-only: {n_copy}')
    print(f'  output:      {OUT}  ({OUT.stat().st_size/1e9:.2f} GB)')


if __name__ == '__main__':
    main()
