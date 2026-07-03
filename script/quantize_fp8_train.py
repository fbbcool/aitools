"""Streaming bf16 -> plain-fp8 (e4m3) reduction for a TRAINING base.

Reproduces the qwen training-fp8 convention (`*-fp8.safetensors`, NOT `-fp8-scaled`):
the big transformer-block linear weights are cast to `float8_e4m3fn`; norms, 1-D
params, and the keep-in-high-precision layers stay at their source dtype. There are
NO per-tensor scales and NO `_quantization_metadata` — this is exactly the tensor set
diffusion-pipe's ComfyPipeline casts at load time with `diffusion_model_dtype='float8'`,
just pre-baked so the download/checkpoint is ~half size and fits a 32 GB card.

A tensor is cast to fp8 iff  ndim >= 2  AND  its name contains none of KEEP. Everything
else is copied verbatim (bf16 linears for the keep layers, F32 norms/1-D as-is).

Streams one tensor at a time -> RAM bounded by the largest single weight.

Usage: edit constants / env (Q_SRC, Q_OUT, Q_KEEP) and run.
"""
import gc
import json
import os
import struct
import time
from pathlib import Path

import torch
from safetensors import safe_open

# ── inputs ───────────────────────────────────────────────────────────────────
SRC = Path(os.environ.get(
    'Q_SRC',
    '/home/misw/venv/comfy2/ComfyUI/models/diffusion_models/krea2/raw/'
    'krea2-raw-snofs0.75-bf16.safetensors'
))
OUT = Path(os.environ.get(
    'Q_OUT',
    '/home/misw/venv/comfy2/ComfyUI/models/diffusion_models/krea2/raw/'
    'krea2-raw-snofs0.75-fp8.safetensors'
))
# Substrings of tensor names kept in high precision (matches the krea2 ComfyPipeline
# keep_in_high_precision: patch-embed, timestep/text projections, text-fusion adapter,
# final layer). Only the shared SingleStreamBlocks (`blocks.*`) get reduced to fp8.
KEEP = os.environ.get('Q_KEEP', 'first,tmlp,tproj,txtfusion,txtmlp,last').split(',')

FP8 = torch.float8_e4m3fn
ST_NAME = {torch.float32: 'F32', torch.float16: 'F16', torch.bfloat16: 'BF16', FP8: 'F8_E4M3'}
NAME_BYTES = {'F32': 4, 'F16': 2, 'BF16': 2, 'F8_E4M3': 1}


def _numel(shape):
    n = 1
    for s in shape:
        n *= s
    return n


def target_dtype(key: str, shape: list[int], src_name: str):
    """fp8 for 2-D block linears, otherwise keep the source dtype."""
    if len(shape) >= 2 and not any(k in key for k in KEEP):
        return FP8, 'F8_E4M3'
    return None, src_name  # copy verbatim


def main() -> None:
    t0 = time.time()
    if not SRC.exists():
        raise SystemExit(f'source not found: {SRC}')
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # header pass
    with open(SRC, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        src_hdr = json.loads(f.read(n))
    src_meta = src_hdr.get('__metadata__', {})
    order = [k for k in src_hdr if k != '__metadata__']

    entries: dict[str, dict] = {}
    off = 0
    n_fp8 = n_keep = 0
    plan: dict[str, str] = {}
    for k in order:
        shape = src_hdr[k]['shape']
        src_name = src_hdr[k]['dtype']
        _, out_name = target_dtype(k, shape, src_name)
        plan[k] = out_name
        if out_name == 'F8_E4M3' and src_name != 'F8_E4M3':
            n_fp8 += 1
        else:
            n_keep += 1
        nb = NAME_BYTES[out_name] * (1 if not shape else _numel(shape))
        entries[k] = {'dtype': out_name, 'shape': shape, 'data_offsets': [off, off + nb]}
        off += nb

    entries['__metadata__'] = {
        'format': 'pt',
        'reduced_from': SRC.name,
        'quant': 'fp8_e4m3fn plain (block linears; keep=%s)' % ','.join(KEEP),
        'merge_type': src_meta.get('merge_type', ''),
        'lora_strength': src_meta.get('lora_strength', ''),
    }
    hb = json.dumps(entries, separators=(',', ':')).encode('utf-8')
    hb += b' ' * ((8 - (len(hb) % 8)) % 8)

    print(f'[plan] {len(order)} tensors: {n_fp8} -> fp8, {n_keep} kept verbatim  (keep={KEEP})')

    # write pass
    print(f'[write] streaming -> {OUT}')
    last = time.time()
    with open(OUT, 'wb') as out, safe_open(SRC, framework='pt') as fs:
        out.write(struct.pack('<Q', len(hb)))
        out.write(hb)
        for i, k in enumerate(order):
            t = fs.get_tensor(k)
            if plan[k] == 'F8_E4M3' and ST_NAME.get(t.dtype) != 'F8_E4M3':
                t = t.float().clamp(-448.0, 448.0).to(FP8)
            out.write(t.contiguous().view(torch.uint8).numpy().tobytes())
            del t
            if (i + 1) % 100 == 0:
                gc.collect()
            if time.time() - last > 5.0:
                print(f'    {i+1}/{len(order)}')
                last = time.time()

    src_gb = SRC.stat().st_size / 1e9
    out_gb = OUT.stat().st_size / 1e9
    print(f'\n✓ done in {time.time()-t0:.1f}s')
    print(f'  fp8 weights: {n_fp8}   kept: {n_keep}')
    print(f'  {SRC.name}: {src_gb:.2f} GB  ->  {OUT.name}: {out_gb:.2f} GB  ({out_gb/src_gb:.0%})')


if __name__ == '__main__':
    main()
