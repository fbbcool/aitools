from enum import Enum, auto
import os
import sys
import shutil
from typing import Final
#from huggingface_hub import hf_hub_download
import requests
from tqdm import tqdm
#import gdown
from git import Repo  # pip install gitpython

class DownloadMethod(Enum):
    Hugging = auto()
    Wget = auto()
    GDrive = auto()
    Git = auto()
class DownloadGroup(Enum):
    SD15 = auto()
    SDXL = auto()
    SDALL = auto()
    FLUX = auto()
class TargetType(Enum):
    Comfy = auto()
    SD = auto()
    Kohyass = auto()
class ModelType(Enum):
    Checkpoint = auto()
    Controlnet = auto()
    Lora = auto()
    Embedding = auto()
    ClipVision = auto()
    Clip = auto()
    IPAdapter = auto()
    CustomNode = auto()
    VAE = auto()
    Unet = auto()


class ModelInst:
    UrlStorageModels: Final = "/workspace/storage/stable_diffusion/models"
    def __init__(self, target: TargetType, model: ModelType, method: DownloadMethod, url: str, name: str="", ext:str ="safetensors") -> None:
        self.target = target
        self.model = model
        self.method = method
        self.url = url
        self.ext = ext
        self.name = name
        if not name:
            self.name = os.path.basename(self.url)
            self.ext = ""
    
    def url_download(self, url: str, fname: str):
        resp = requests.get(url, stream=True)
        total = int(resp.headers.get('content-length', 0))
        
        fopath, _ = os.path.split(fname)
        if not os.path.exists(fopath):
            os.makedirs(fopath)
        try:
            with open(fname, 'wb') as file, tqdm(
                desc=fname,
                total=total,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
            ) as bar:
                for data in resp.iter_content(chunk_size=1024):
                    size = file.write(data)
                    bar.update(size)
        except:
            print(f"Url download went wrong: {url}")

    def url_download_old(self, url: str) -> str:
        local_filename = url.split('/')[-1]
        try:
            with requests.get(url, stream=True) as r:
                with open(local_filename, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
        except:
            print(f"Url download went wrong: {url}")

        return local_filename

    def git_clone(self, url: str, folder: str) -> None:
        try:
            Repo.clone_from(url, folder, recursive=True)
        except:
            print(f"Url git clone went wrong: {url} -> {folder}")
    
    @classmethod
    def url_exit(cls, url: str) -> bool:
        return os.path.isfile(url) or os.path.isdir(url)
    
    @property
    def install(self, force: bool = False) -> None:
        url_folder = self.url_models
        url_repos = f"{url_folder}/{self.name}"
        url_model = url_repos
        if self.ext:
            url_model = f"{url_model}.{self.ext}"
        
        if not force:
            if ModelInst.url_exit(url_model):
                return
            
        os.makedirs(url_folder, exist_ok=True)
        
        if self.method == DownloadMethod.Hugging:
            print(f"(NO)installing from hugging: {self.url} -> {url_model}")
            url_split = self.url.split("/")
            #filename = hf_hub_download(repo_id = f"{url_split[0]}/{url_split[1]}", filename = url_split[2])
            #shutil.move(filename, url_model)
            
        if self.method == DownloadMethod.Wget:
            print(f"installing by wget: {self.url} -> {url_model}")
            #filename = self.url_download_old(self.url)
            #shutil.move(filename, url_model)
            self.url_download(self.url, url_model)

        if self.method == DownloadMethod.GDrive:
            print(f"(NO)installing from gdrive: {self.url} -> {url_model}")
            #gdown.download(id = self.url, output = url_model)

        if self.method == DownloadMethod.Git:
            print(f"git clone: {self.url} -> {url_repos}")
            self.git_clone(self.url, url_folder)

    @property
    def url_models(self) -> str:
        path_models = ""
        folder_model = ""
        if self.target == TargetType.Comfy:
            path_models = "/opt/ComfyUI/models"
            if self.model == ModelType.Checkpoint:
                folder_model = "checkpoints"
            elif self.model == ModelType.VAE:
                folder_model = "vae"
            elif self.model == ModelType.Controlnet:
                folder_model = "controlnet"
            elif self.model == ModelType.CustomNode:
                folder_model = "nodes"
            elif self.model == ModelType.Lora:
                folder_model = "loras"
            elif self.model == ModelType.Embedding:
                folder_model = "embeddings"
            elif self.model == ModelType.Clip:
                folder_model = "clip"
            elif self.model == ModelType.ClipVision:
                folder_model = "clip_vision"
            elif self.model == ModelType.IPAdapter:
                folder_model = "ipadapter"
            elif self.model == ModelType.Unet:
                folder_model = "unet"
        
        if not folder_model:
            raise ValueError("Dir Models unknown!")
        
        return f"{path_models}/{folder_model}"
    
class ModelInstComfyUi:
    def __init__(self, group = DownloadGroup.SD15) -> None:
        t = TargetType.Comfy
        wget = DownloadMethod.Wget
        models_sd15: list[ModelInst] = [
            ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/256915", "cyberrealistic"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/143906", "EpicRealism"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/573082", "GODDESSofRealism"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/283712", "MFCGDollMix"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/245598?type=Model&format=SafeTensor&size=pruned&fp=fp16", "realisticvision"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/128713?type=Model&format=SafeTensor&size=pruned&fp=fp16", "dreamshaper"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/143906?type=Model&format=SafeTensor&size=pruned&fp=fp16", "epic_realism_vae"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/251662", "dreamshaper_xl"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/288982?type=Model&format=SafeTensor&size=full&fp=fp16", "juggernaut_xl"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0/resolve/main/sd_xl_refiner_1.0_0.9vae.safetensors?download=true", "sdxl_refiner"),

            #ModelInst(t, ModelType.Lora, wget, "https://drive.usercontent.google.com/download?id=1WOAizZJY4g4qO8nGWOW2UuMLvbI3bWsM&export=download&authuser=0&confirm=t&uuid=2754e049-8f00-4b61-af55-974da0d86cf4&at=APZUnTVuxLuA5FGY9HgGSYyqScEe%3A1705351998875", "lara"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/260383?type=Model&format=SafeTensor", "Muscle_bimbo"),
            #ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/281780?type=Model&format=SafeTensor", "Muscle_mgm"),
            #ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/87153?type=Model&format=SafeTensor", "Adetailer"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/96699", "Minigiantess"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/315369", "GiantessWithTiny"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/154604", "ChloeVevrier"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/123205", "Giantess"),
            #ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/310719", "ExtremeHairy_v2"),
            #ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/137206", "Unshaven"),
            #ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/229047", "Insertion"),
            #ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/295786", "MuscleGirlsXL"),
            ModelInst(t, ModelType.Lora, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sd15_lora.safetensors"),
            ModelInst(t, ModelType.Lora, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sd15_lora.safetensors"),
            
            ModelInst(t, ModelType.Embedding, wget, "https://civitai.com/api/download/models/77169?type=Model&format=PickleTensor", "BadDream", ext="pt"),
            ModelInst(t, ModelType.Embedding, wget, "https://civitai.com/api/download/models/77173?type=Model&format=PickleTensor", "UnrealisticDream", ext="pt"),

            #ModelInst(t, ModelType.ClipVision, wget, "https://huggingface.co/InvokeAI/ip_adapter_sd_image_encoder/resolve/main/model.safetensors?download=true", "ip_adapter_sd_image_encoder"),
            ModelInst(t, ModelType.ClipVision, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors", "CLIP-ViT-H-14-laion2B-s32B-b79K"),
            ModelInst(t, ModelType.ClipVision, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors", "CLIP-ViT-bigG-14-laion2B-39B-b160k"),

            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15.safetensors"),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_light_v11.safetensors"),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus_sd15.safetensors"),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus-face_sd15.safetensors"),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-full-face_sd15.safetensors"),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_vit-G.safetensors"),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sd15.bin"),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sd15.bin"),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-portrait-v11_sd15.bin"),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/ostris/ip-composition-adapter/resolve/main/ip_plus_composition_sd15.safetensors"),

            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/webui/ControlNet-modules-safetensors/resolve/main/control_depth-fp16.safetensors?download=true", "control_depth-fp16"),
            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/lllyasviel/control_v11f1e_sd15_tile/resolve/main/diffusion_pytorch_model.bin?download=true", "control_tile-fp16", ext="pth"),
            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_softedge.pth?download=true", "control_softedge-fp16", ext="pth"),
            #ModelInst(t, ModelType.CustomNode, wget "https://github.com/ssitu/ComfyUI_UltimateSDUpscale", "ComfyUI_UltimateSDUpscale"),
        ]
        models_sdxl: list[ModelInst] = [
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/149868", "BBBvolup"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/344487", "RealVisXL V4.0"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/461409", "EpicRealismXL_v6"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/401841", "EpicRealismXL_Lightning_Zeus"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/251662", "dreamshaper_xl"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/288982?type=Model&format=SafeTensor&size=full&fp=fp16", "juggernaut_xl"),
            #ModelInst(t, ModelType.Checkpoint, wget, "https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0/resolve/main/sd_xl_refiner_1.0_0.9vae.safetensors?download=true", "sdxl_refiner"),
            ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/461409", "Pony_Realism_XL"),
            ModelInst(t, ModelType.Checkpoint, wget, "https://civitai.com/api/download/models/290640?type=Model&format=SafeTensor&size=pruned&fp=fp16", "PonyDiff_v6_XL"),
            
            ModelInst(t, ModelType.VAE, wget, "https://civitai.com/api/download/models/290640?type=VAE&format=SafeTensor", "PonyDiff_VAE_XL"),

            #ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/281780?type=Model&format=SafeTensor", "Muscle_mgm"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/87153?type=Model&format=SafeTensor", "Adetailer"),
            #ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/295786", "MuscleGirlsXL"),
            #ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/152734", "Uberfit"),
            #ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/166271", "MinigiantessXL"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/577428", "MinigiantessPDXL"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/422872", "AnalVorePDXL"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/443306", "UnbirthPDXL"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/564673", "ShrunkPDXL"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/539041", "PubicHairSlider_PDXL"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/532904", "GiantessShrink_PDXL"),
            ModelInst(t, ModelType.Lora, wget, "https://civitai.com/api/download/models/394030", "Hairy_SDXL"),
            #ModelInst(t, ModelType.Lora, wget, "https://drive.usercontent.google.com/download?id=12hW1O5jk06wwjbaalNDAOiq6GtAEb56C&export=download&authuser=0&confirm=t&uuid=6f0b3a21-37aa-487d-bd6e-6ad48c7ab68b&at=APZUnTWUTuTLbnTZjWSiW2DcBkMH%3A1713994594036", "LaraXL"),
            ModelInst(t, ModelType.Lora, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sdxl_lora.safetensors", ""),
            ModelInst(t, ModelType.Lora, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl_lora.safetensors", ""),
            #ModelInst(t, ModelType.Lora, wget, "https://huggingface.co/ByteDance/SDXL-Lightning/resolve/main/sdxl_lightning_2step_lora.safetensors", ""),
            #ModelInst(t, ModelType.Lora, wget, "https://huggingface.co/ByteDance/SDXL-Lightning/resolve/main/sdxl_lightning_4step_lora.safetensors", ""),
            #ModelInst(t, ModelType.Lora, wget, "https://huggingface.co/ByteDance/SDXL-Lightning/resolve/main/sdxl_lightning_8step_lora.safetensors", ""),
            
            ModelInst(t, ModelType.Embedding, wget, "https://civitai.com/api/download/models/77169?type=Model&format=PickleTensor", "BadDream", ext="pt"),
            ModelInst(t, ModelType.Embedding, wget, "https://civitai.com/api/download/models/77173?type=Model&format=PickleTensor", "UnrealisticDream", ext="pt"),

            ModelInst(t, ModelType.ClipVision, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors", "CLIP-ViT-H-14-laion2B-s32B-b79K"),
            ModelInst(t, ModelType.ClipVision, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors", "CLIP-ViT-bigG-14-laion2B-39B-b160k"),

            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl_vit-h.safetensors", ""),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors", ""),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors", ""),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl.safetensors", ""),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid_sdxl.bin", ""),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl.bin", ""),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-portrait_sdxl.bin", ""),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-portrait_sdxl_unnorm.bin", ""),
            ModelInst(t, ModelType.IPAdapter, wget, "https://huggingface.co/ostris/ip-composition-adapter/resolve/main/ip_plus_composition_sdxl.safetensors", ""),

            ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/xinsir/controlnet-union-sdxl-1.0/resolve/main/diffusion_pytorch_model_promax.safetensors", ""),
            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/webui/ControlNet-modules-safetensors/resolve/main/control_depth-fp16.safetensors?download=true", "control_depth-fp16"),
            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/lllyasviel/control_v11f1e_sd15_tile/resolve/main/diffusion_pytorch_model.bin?download=true", "control_tile-fp16", ext="pth"),
            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_softedge.pth?download=true", "control_softedge-fp16", ext="pth"),
            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/lllyasviel/sd_control_collection/resolve/main/t2i-adapter_diffusers_xl_canny.safetensors", ""),
            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/lllyasviel/sd_control_collection/resolve/main/t2i-adapter_diffusers_xl_depth_midas.safetensors", ""),
            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/lllyasviel/sd_control_collection/resolve/main/t2i-adapter_diffusers_xl_openpose.safetensors", ""),
            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/lllyasviel/sd_control_collection/resolve/main/t2i-adapter_diffusers_xl_sketch.safetensors", ""),
            #ModelInst(t, ModelType.Controlnet, wget, "https://huggingface.co/lllyasviel/sd_control_collection/resolve/main/t2i-adapter_xl_openpose.safetensors", ""),
        ]
        models_flux: list[ModelInst] = [
            ModelInst(t, ModelType.Unet, wget, "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/flux1-schnell.sft?download=true", "flux1-schnell"),
            
            ModelInst(t, ModelType.VAE, wget, "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/vae/diffusion_pytorch_model.safetensors?download=true", "vae_flux1"),

            ModelInst(t, ModelType.Clip, wget, "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors?download=true", "clip_l"),
            ModelInst(t, ModelType.Clip, wget, "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors?download=true", "t5xxl_fp16"),
            ModelInst(t, ModelType.Clip, wget, "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors?download=true", "t5xxl_fp8_e4m3fn"),
        ]
        model_db = {
            DownloadGroup.SD15: models_sd15,
            DownloadGroup.SDXL: models_sdxl,
            DownloadGroup.SDALL: models_sd15 + models_sdxl,
            DownloadGroup.FLUX: models_flux
        }
        for model in model_db[group]:
            model.install

if __name__ == "__main__":
    str_group = sys.argv[1]
    if str_group == "sd15":
        group = DownloadGroup.SD15
    elif str_group == "sdxl":
        group = DownloadGroup.SDXL
    elif str_group == "sdall":
        group = DownloadGroup.SDALL
    elif str_group == "flux":
        group = DownloadGroup.FLUX
    else:
        str_group = "sd15"
        group = DownloadGroup.SD15
    

    print(f"using download group {str_group}.")
    ModelInstComfyUi(group=group)

# https://huggingface.co/lllyasviel/ControlNet-v1-1/tree/main #ctrlnet models
#https://huggingface.co/h94/IP-Adapter-FaceID/tree/main
# custom nodes
# 002 * ComfyUI-Impact-Pack *
# 003 * ComfyUI-Inspire-Pack *
# 008 * controlnet *
# 013 - clipseg
# 014 - ComFyUI Cutoff
# 016 - ComFyUI Noise
# 020 * Efficiency nodes 2.0+ *
# 064 * ComfyUI WD 1.4 Tagger *
# 073 * ultimateSDupscale *
# 098 * ipadapter plus *
# 127 - ReActor Node for ComfyUI
# 171 * rgthree *
# 202 - comfy_PoP
# 236 * Essentials *
# 227 - CFG Scale Fix
# 231 - Use Everywher
# 275 * segment anything *
# 273 - mask bounding box
# 408 * Comfyui Easy Use *