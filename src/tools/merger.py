import os
from pathlib import Path
import torch
from tqdm import tqdm
from safetensors.torch import load_file, save_file

FOLDER_MODELS_COMFY = Path("/workspace/ComfyUI/models")
FOLDER_MODELS_LOCAL = Path("/Volumes/data/Project/AI/models/000_local")
FOLDER_MODELS = FOLDER_MODELS_LOCAL
FOLDER_UNET = FOLDER_MODELS / "unet"
FOLDER_LORA = FOLDER_MODELS / "loras"
FOLDER_OUTPUT = FOLDER_MODELS / "unet"

# Main entry point
def merge_lora_with_checkpoint(stem_ckpt: str, stem_lora: str, ratio: float):
    print("\nStarting the merge process")

    model_suffix = ".safetensors"

    file_ckpt = FOLDER_UNET / stem_ckpt
    file_ckpt = file_ckpt.with_suffix(model_suffix)

    file_lora = FOLDER_LORA / stem_lora
    file_lora = file_lora.with_suffix(model_suffix)

    lora_data = load_file(file_lora)
    checkpoint_data = load_file(file_ckpt)

    do_full_merge = True
    # Merge based on the selected strategy
    if do_full_merge:
        merged_model = full_merge(lora_data, checkpoint_data, ratio)
    else:
        pass
        #merged_model = selective_merge(lora_data, checkpoint_data, config['merge_weights'])

    s = file_lora.stem.split("_")
    file_model_out = FOLDER_OUTPUT / f"{file_ckpt.stem}_{s[1]}{int(ratio*100.0)}"
    file_model_out = file_model_out.with_suffix(model_suffix)
    print(f"\n\t saving {str(file_model_out)}")
    save_file(merged_model, FOLDER_OUTPUT / file_model_out)

    print("Merge completed successfully!")

# Full model merging with a specific ratio
def full_merge(lora_data, checkpoint_data, ratio):
    merged = {}
    total_layers = set(checkpoint_data.keys()).union(lora_data.keys())

    for layer in tqdm(total_layers, desc="Merging Layers", unit="layer"):
        if layer in checkpoint_data and layer in lora_data:
            merged[layer] = checkpoint_data[layer] + (ratio * lora_data[layer])
        elif layer in checkpoint_data:
            merged[layer] = checkpoint_data[layer]
        else:
            merged[layer] = ratio * lora_data[layer]
    
    return merged

# Selective merge with different ratios per layer
def selective_merge(lora_data, checkpoint_data, merge_weights):
    merged = {}
    total_layers = set(checkpoint_data.keys()).union(lora_data.keys())

    for layer in tqdm(total_layers, desc="Selective Merging", unit="layer"):
        if layer in merge_weights:
            ratio = merge_weights[layer]
            merged[layer] = checkpoint_data.get(layer, 0) + (ratio * lora_data.get(layer, 0))
        else:
            merged[layer] = checkpoint_data.get(layer, lora_data.get(layer))

    return merged
