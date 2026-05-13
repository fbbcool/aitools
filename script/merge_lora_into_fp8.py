"""Streaming LoRA-into-fp8 merge.

Loads a bf16 transformer checkpoint, applies a PEFT-format LoRA at a given
strength, writes a fp8-mixed safetensors file matching the selective-fp8
pattern of an existing reference file (linear weights → fp8 e4m3fn, biases/
norms → bf16). Streams one tensor at a time so peak RAM is bounded by the
largest single tensor, not the model size.

Usage: edit the constants below and run.
"""
import gc
import json
import struct
import time
from pathlib import Path

import torch
from safetensors import safe_open

# ── inputs ─────────────────────────────────────────────────────────────────
BASE_BF16 = Path('/home/misw/Workspace/train/data/diffusion_models/qwen-image-2512-snofs0.65.safetensors')
FP8_REF   = Path('/home/misw/Workspace/train/data/diffusion_models/qwen-image-2512-snofs0.65-fp8.safetensors')
LORA      = Path('/home/misw/venv/comfy2/ComfyUI/models/loras/gts3/adapter_model.safetensors')

# ── output ─────────────────────────────────────────────────────────────────
OUT = Path('/home/misw/venv/comfy2/ComfyUI/models/diffusion_models/qwen-image-2512-snofs0.65_gts3-e10s08-fp8.safetensors')

# ── lora config ────────────────────────────────────────────────────────────
LORA_STRENGTH = 0.8
LORA_RANK     = 32
LORA_ALPHA    = 32   # PEFT/diffusion-pipe default = rank → scale = 1.0
EFFECTIVE     = LORA_STRENGTH * (LORA_ALPHA / LORA_RANK)


SAFETENSORS_DTYPE = {
    torch.bfloat16:        'BF16',
    torch.float8_e4m3fn:   'F8_E4M3',
    torch.float16:         'F16',
    torch.float32:         'F32',
}

# Stochastic-rounding fp8 cast. Deterministic round-to-nearest erases small
# LoRA deltas (75% of targeted weights at gts3 epoch 10 magnitudes round
# back to the pre-LoRA fp8 value). Stochastic rounding preserves the delta
# in expectation: for each element, add uniform noise scaled by the local
# quantization step before the cast. Expected value is preserved; the cost
# is a small per-weight noise pattern, distributed across the whole tensor
# rather than concentrated in the 25% of weights that survived rounding.
#
# fp8_e4m3fn quantization step at value v ≈ |v| × 2^-3 = |v| / 8 (3 mantissa
# bits). Adding uniform noise in [-step/2, +step/2] before cast does dithered
# quantization.
def to_fp8_stochastic(t: torch.Tensor) -> torch.Tensor:
    t_fp32 = t.to(torch.float32)
    step = t_fp32.abs() / 8.0
    # Small floor to avoid zero-noise for near-zero weights
    step = step.clamp(min=1e-12)
    noise = (torch.rand_like(t_fp32) - 0.5) * step
    return (t_fp32 + noise).to(torch.bfloat16).to(torch.float8_e4m3fn)


def main() -> None:
    t_start = time.time()
    # Seed for reproducible stochastic rounding (so the same merge produces the
    # same file bit-for-bit).
    torch.manual_seed(42)
    print(f'effective LoRA multiplier (strength × scale): {EFFECTIVE}')
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # 1. Build the set of keys that should be fp8 (matching the existing fp8 reference file)
    print(f'\n[1/4] scanning fp8 reference pattern from {FP8_REF.name} ...')
    fp8_keys: set[str] = set()
    with safe_open(FP8_REF, framework='pt') as f:
        for k in f.keys():
            if f.get_tensor(k).dtype == torch.float8_e4m3fn:
                fp8_keys.add(k)
    print(f'    {len(fp8_keys)} keys to quantize as fp8 e4m3fn')

    # 2. Load LoRA pairs (small, ~590 MB total) into memory
    print(f'\n[2/4] loading LoRA pairs from {LORA.name} ...')
    lora_pairs: dict[str, tuple[torch.Tensor, torch.Tensor]] = {}
    with safe_open(LORA, framework='pt') as f:
        for k in f.keys():
            if not k.endswith('.lora_A.weight'):
                continue
            stem = k.removeprefix('diffusion_model.').removesuffix('.lora_A.weight')
            base_k = f'{stem}.weight'
            b_k = k.replace('.lora_A.weight', '.lora_B.weight')
            if b_k not in f.keys():
                continue
            lora_pairs[base_k] = (f.get_tensor(k), f.get_tensor(b_k))
    print(f'    {len(lora_pairs)} LoRA pairs loaded')

    # 3. First pass on base: collect (key, shape, output_dtype) — no tensor data held
    print(f'\n[3/4] first-pass header build from {BASE_BF16.name} ...')
    header_entries: dict[str, dict] = {}
    key_order: list[str] = []
    data_offset = 0
    with safe_open(BASE_BF16, framework='pt') as f:
        for k in f.keys():
            t = f.get_tensor(k)
            shape = list(t.shape)
            elem_count = 1
            for s in shape:
                elem_count *= s
            del t
            out_dtype = torch.float8_e4m3fn if k in fp8_keys else torch.bfloat16
            byte_per_elem = 1 if out_dtype == torch.float8_e4m3fn else 2
            n_bytes = elem_count * byte_per_elem
            header_entries[k] = {
                'dtype': SAFETENSORS_DTYPE[out_dtype],
                'shape': shape,
                'data_offsets': [data_offset, data_offset + n_bytes],
            }
            key_order.append(k)
            data_offset += n_bytes
    total_data_bytes = data_offset
    print(f'    {len(key_order)} tensors, total data section: {total_data_bytes / 1e9:.2f} GB')

    # Compose JSON header
    header_with_meta = dict(header_entries)
    header_with_meta['__metadata__'] = {
        'format': 'pt',
        'merged_from': f'{BASE_BF16.name} + {LORA.name}@{LORA_STRENGTH}',
        'lora_strength': str(LORA_STRENGTH),
        'lora_rank': str(LORA_RANK),
        'lora_alpha': str(LORA_ALPHA),
    }
    header_bytes = json.dumps(header_with_meta, separators=(',', ':')).encode('utf-8')
    # Pad header to 8-byte alignment to keep tensor data aligned
    pad = (8 - (len(header_bytes) % 8)) % 8
    header_bytes += b' ' * pad
    print(f'    header size: {len(header_bytes)} bytes')

    # 4. Stream the merge: open output, write header, then loop tensors
    print(f'\n[4/4] streaming merge → {OUT} ...')
    n_lora_applied = 0
    n_copy = 0
    n_fp8 = 0
    n_bf16 = 0
    last_progress = time.time()

    with open(OUT, 'wb') as out:
        # Write 8-byte little-endian header length, then header JSON
        out.write(struct.pack('<Q', len(header_bytes)))
        out.write(header_bytes)
        assert out.tell() == 8 + len(header_bytes)

        with safe_open(BASE_BF16, framework='pt') as f:
            for i, k in enumerate(key_order):
                t = f.get_tensor(k).to(torch.bfloat16)  # ensure bf16 working precision

                # Apply LoRA if applicable
                if k in lora_pairs:
                    A, B = lora_pairs[k]
                    # B: [out, rank], A: [rank, in]  →  delta: [out, in]
                    delta = (B.to(torch.float32) @ A.to(torch.float32)) * EFFECTIVE
                    t = (t.to(torch.float32) + delta).to(torch.bfloat16)
                    del delta
                    n_lora_applied += 1
                else:
                    n_copy += 1

                # Cast to output dtype. Deterministic round-to-nearest. NOTE:
                # for LoRAs with small per-weight delta (mean ~|w|/100 or less),
                # fp8_e4m3fn unscaled cannot represent the LoRA effect because
                # the delta is below the quantization step. Use bf16 or fp8-scaled
                # output for those cases.
                if k in fp8_keys:
                    t = t.to(torch.float8_e4m3fn)
                    n_fp8 += 1
                else:
                    # already bf16
                    n_bf16 += 1

                # Write raw bytes (mmap-free)
                t = t.contiguous().cpu()
                tensor_bytes = t.view(torch.uint8).numpy().tobytes()
                out.write(tensor_bytes)
                del t, tensor_bytes
                # garbage collect occasionally to free mmap pages
                if (i + 1) % 100 == 0:
                    gc.collect()
                if time.time() - last_progress > 5.0:
                    elapsed = time.time() - t_start
                    rate = (i + 1) / max(elapsed, 0.1)
                    eta = (len(key_order) - i - 1) / max(rate, 0.001)
                    print(f'    {i+1:4d}/{len(key_order)}  '
                          f'lora={n_lora_applied} copy={n_copy}  '
                          f'eta={eta:.0f}s')
                    last_progress = time.time()

    elapsed = time.time() - t_start
    out_size = OUT.stat().st_size
    print(f'\n✓ done in {elapsed:.1f}s')
    print(f'  lora-applied: {n_lora_applied}')
    print(f'  copy-only:    {n_copy}')
    print(f'  fp8 tensors:  {n_fp8}')
    print(f'  bf16 tensors: {n_bf16}')
    print(f'  output size:  {out_size / 1e9:.2f} GB')
    print(f'  output:       {OUT}')


if __name__ == '__main__':
    main()
