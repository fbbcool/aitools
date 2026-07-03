"""Streaming bf16 -> scaled-fp8 quantiser, matching a reference fp8 file's layout.

Produces a ComfyUI-loadable `float8_e4m3fn` scaled checkpoint from a bf16
transformer, reproducing the EXACT format of a reference stock fp8 file:
  - per-linear weight stored as fp8_e4m3fn = round(W / scale), scale = max|W|/448
  - per-linear `{layer}.weight_scale` F32 scalar (comfy dequant: fp8 * scale)
  - 1-D params (norms) as BF16
  - the reference's `_quantization_metadata` header block copied verbatim, so
    comfy's loader (utils.py:1454 -> comfy_quant -> MixedPrecisionOps) recognises
    exactly the same layers as scaled-fp8.

Which tensors are fp8 is defined solely by the reference file (its F8_E4M3 keys +
_quantization_metadata), so this stays correct even if the base's fp8 layer set
is non-trivial. Streams one tensor at a time -> RAM bounded by the largest weight.

Usage: edit the constants and run. Runs a self-test first (re-quantise the stock
bf16 and check it reproduces the stock fp8) before writing the real output.
"""
import gc
import json
import os
import struct
import time
from pathlib import Path

import torch
from safetensors import safe_open

# ── inputs (override via env: Q_MERGED / Q_FP8_REF / Q_STOCK_BF16 / Q_OUT) ───
# FP8_REF + STOCK_BF16 must be the *same variant's* stock files (the fp8 ref
# defines which layers are fp8 + the _quantization_metadata; the self-test
# checks the quantiser reproduces that stock fp8 from its stock bf16).
MERGED_BF16 = Path(os.environ.get(
    'Q_MERGED',
    '/home/misw/venv/comfy2/ComfyUI/models/diffusion_models/krea2/raw/'
    'krea2-raw-snofs0.75-bf16.safetensors'
))
FP8_REF = Path(os.environ.get(
    'Q_FP8_REF', '/home/misw/venv/comfy2/ComfyUI/models/diffusion_models/krea2/raw/fp8.safetensors'))
STOCK_BF16 = Path(os.environ.get(
    'Q_STOCK_BF16',
    '/home/misw/.cache/huggingface/hub/models--comfy-org--krea-2/snapshots/'
    '8038ce89b91b042141541ad0fa51b985ca262c5f/diffusion_models/krea2_raw_bf16.safetensors'
))

# ── output ─────────────────────────────────────────────────────────────────
OUT = Path(os.environ.get(
    'Q_OUT',
    '/home/misw/venv/comfy2/ComfyUI/models/diffusion_models/krea2/raw/'
    'krea2-raw-snofs0.75-fp8-scaled.safetensors'
))

FP8_MAX = 448.0  # float8_e4m3fn max representable
DTYPE_BYTES = {'F32': 4, 'F16': 2, 'BF16': 2, 'F8_E4M3': 1}
TORCH_FROM_NAME = {'F32': torch.float32, 'F16': torch.float16,
                   'BF16': torch.bfloat16, 'F8_E4M3': torch.float8_e4m3fn}


def header(p: Path) -> dict:
    with open(p, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        return json.loads(f.read(n))


def quantize(w_bf16: torch.Tensor) -> tuple[torch.Tensor, float]:
    """Round-to-nearest scaled fp8, scale = amax/448 (matches stock)."""
    w = w_bf16.float()
    amax = w.abs().max().item()
    scale = amax / FP8_MAX if amax > 0 else 1.0
    q = (w / scale).clamp(-FP8_MAX, FP8_MAX).to(torch.float8_e4m3fn)
    return q, scale


def self_test() -> None:
    print('[self-test] reproducing stock fp8 from stock bf16 ...')
    ref = header(FP8_REF)
    keys = [k for k in ref if k != '__metadata__' and ref[k]['dtype'] == 'F8_E4M3'][:4]
    with safe_open(STOCK_BF16, framework='pt') as fb, safe_open(FP8_REF, framework='pt') as ff:
        for k in keys:
            q, sc = quantize(fb.get_tensor(k))
            sc_ref = ff.get_tensor(k[: -len('.weight')] + '.weight_scale').float().item()
            q_ref = ff.get_tensor(k).float()
            # scale must match to high precision; fp8 codes should match exactly
            scale_ok = abs(sc - sc_ref) / sc_ref < 1e-4
            code_mismatch = (q.float() != q_ref).float().mean().item()
            print(f'    {k}: scale mine={sc:.4e} stock={sc_ref:.4e} ok={scale_ok}  '
                  f'fp8 code mismatch={code_mismatch:.4%}')
            if not scale_ok or code_mismatch > 0.01:
                raise SystemExit('self-test FAILED: format/convention mismatch')
    print('    self-test PASSED (scales match, fp8 codes reproduce stock)\n')


def main() -> None:
    t0 = time.time()
    for p in (MERGED_BF16, FP8_REF):
        if not p.exists():
            raise SystemExit(f'missing input: {p}')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    self_test()

    ref = header(FP8_REF)
    ref_meta = ref.get('__metadata__', {})
    if '_quantization_metadata' not in ref_meta:
        raise SystemExit('reference has no _quantization_metadata; wrong template')
    order = [k for k in ref if k != '__metadata__']
    fp8_wkeys = {k for k in order if ref[k]['dtype'] == 'F8_E4M3'}
    print(f'[1/3] reference: {len(order)} tensors, {len(fp8_wkeys)} fp8 linears')

    # pre-pass: scales from merged weights (256 floats)
    print('[2/3] computing per-linear scales from merged bf16 ...')
    scales: dict[str, float] = {}
    with safe_open(MERGED_BF16, framework='pt') as fm:
        merged_keys = set(fm.keys())
        miss = [k for k in fp8_wkeys if k not in merged_keys]
        if miss:
            raise SystemExit(f'{len(miss)} fp8 targets absent in merged, e.g. {miss[:3]}')
        for k in fp8_wkeys:
            scales[k] = quantize(fm.get_tensor(k))[1]
    print(f'    {len(scales)} scales')

    # build header mirroring the reference dtypes/shapes
    entries: dict[str, dict] = {}
    off = 0
    for k in order:
        dt = ref[k]['dtype']
        shape = ref[k]['shape']
        nb = DTYPE_BYTES[dt] * (1 if not shape else _numel(shape))
        entries[k] = {'dtype': dt, 'shape': shape, 'data_offsets': [off, off + nb]}
        off += nb
    entries['__metadata__'] = {
        'format': 'pt',
        '_quantization_metadata': ref_meta['_quantization_metadata'],  # verbatim
        'merged_from': MERGED_BF16.name,
        'quant': 'fp8_e4m3fn scaled (amax/448, round-nearest)',
    }
    hb = json.dumps(entries, separators=(',', ':')).encode('utf-8')
    hb += b' ' * ((8 - (len(hb) % 8)) % 8)

    # write pass
    print(f'[3/3] streaming quant -> {OUT} ...')
    n_fp8 = n_scale = n_bf16 = 0
    last = time.time()
    with open(OUT, 'wb') as out, safe_open(MERGED_BF16, framework='pt') as fm:
        out.write(struct.pack('<Q', len(hb)))
        out.write(hb)
        for i, k in enumerate(order):
            dt = ref[k]['dtype']
            if dt == 'F8_E4M3':                          # linear weight -> fp8
                q, _ = quantize(fm.get_tensor(k))
                out.write(q.contiguous().view(torch.uint8).numpy().tobytes())
                n_fp8 += 1
            elif k.endswith('.weight_scale'):            # scalar scale
                wk = k[: -len('.weight_scale')] + '.weight'
                out.write(struct.pack('<f', scales[wk]))
                n_scale += 1
            else:                                        # norm/1-D -> bf16
                out.write(fm.get_tensor(k).to(torch.bfloat16)
                          .contiguous().view(torch.uint8).numpy().tobytes())
                n_bf16 += 1
            if (i + 1) % 100 == 0:
                gc.collect()
            if time.time() - last > 5.0:
                print(f'    {i+1}/{len(order)}  fp8={n_fp8} scale={n_scale} bf16={n_bf16}')
                last = time.time()

    print(f'\n✓ done in {time.time()-t0:.1f}s')
    print(f'  fp8 weights: {n_fp8}   scales: {n_scale}   bf16: {n_bf16}')
    print(f'  output: {OUT}  ({OUT.stat().st_size/1e9:.2f} GB)')


def _numel(shape: list[int]) -> int:
    n = 1
    for s in shape:
        n *= s
    return n


if __name__ == '__main__':
    main()
