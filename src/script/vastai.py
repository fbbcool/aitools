import shutil
from huggingface_hub import hf_hub_download

controlnet_model_id = "webui/ControlNet-modules-safetensors"
controlnet_models = [
    "control_depth-fp16.safetensors",
    "control_openpose-fp16.safetensors",
    "control_scribble-fp16.safetensors",
    "control_seg-fp16.safetensors",
    "control_normal-fp16.safetensors",
    "control_mlsd-fp16.safetensors",
    "control_heg-fp16.safetensors",
]
controlnet_inst_dir = "/workspace/storage/stable_diffusion/models/controlnet"

for model in controlnet_models:
    hf = hf_hub_download(repo_id=controlnet_model_id, filename=model)
    shutil.copy2(hf, controlnet_inst_dir)

