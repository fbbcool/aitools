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
    "control_hed-fp16.safetensors",
]
controlnet_model_id_xl="lllyasviel/sd_control_collection"
controlnet_models_xl = [
    "diffusers_xl_depth_mid.safetensors",
    "thibaud_xl_openpose_256lora.safetensors",
    "t2i-adapter_diffusers_xl_openpose.safetensors",
    "thibaud_xl_openpose.safetensors",
]
controlnet_inst_dir = "/workspace/storage/stable_diffusion/models/controlnet"

for model in controlnet_models:
    hf = hf_hub_download(repo_id=controlnet_model_id, filename=model)
    shutil.copy2(hf, controlnet_inst_dir)

for model in controlnet_models_xl:
    hf = hf_hub_download(repo_id=controlnet_model_id_xl, filename=model)
    shutil.copy2(hf, controlnet_inst_dir)


#from civitai import models
#model = models.get_model(modelId=15003) # cyberrealistic
#modelVersion = models.get_by_modelVersion(modelVersionId=128713)
#model.name                # DreamShaper
#modelVersion.name  
