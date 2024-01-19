from enum import Enum, auto
import os
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
    IPAdapter = auto()
    CustomNode = auto()


class ModelInst:
    UrlStorageModels: Final = "/workspace/storage/stable_diffusion/models"
    def __init__(self, target: TargetType, model: ModelType, method: DownloadMethod, url: str, name: str, ext:str ="safetensors") -> None:
        self.target = target
        self.model = model
        self.method = method
        self.url = url
        self.ext = ext
        self.name = name
    
    def url_download(self, url: str, fname: str):
        resp = requests.get(url, stream=True)
        total = int(resp.headers.get('content-length', 0))
        # Can also replace 'file' with a io.BytesIO object
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
        url_model = f"{self.url_models}/{self.name}.{self.ext}"
        url_folder = f"{self.url_models}/{self.name}"
        
        if not force:
            if ModelInst.url_exit(url_model):
                return
        
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
            print(f"git clone: {self.url} -> {url_folder}")
            self.git_clone(self.url, url_folder)
            #gdown.download(id = self.url, output = url_model)

    @property
    def url_models(self) -> str:
        if self.target == TargetType.Comfy:
            if self.model == ModelType.Checkpoint:
                return "/opt/ComfyUI/models/checkpoints"
            if self.model == ModelType.Controlnet:
                return "/opt/ComfyUI/models/controlnet"
            if self.model == ModelType.CustomNode:
                return "/opt/ComfyUI/custom_nodes"
            if self.model == ModelType.Lora:
                return "/opt/ComfyUI/models/loras"
            if self.model == ModelType.Embedding:
                return "/opt/ComfyUI/models/embeddings"
            if self.model == ModelType.ClipVision:
                return "/opt/ComfyUI/models/clip_vision"
            if self.model == ModelType.IPAdapter:
                return "/opt/ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus/models"
        raise ValueError("Dir Models unknown!")
    
class ModelInstComfyUi:
    def __init__(self) -> None:
        t = TargetType.Comfy
        models: list[ModelInst] = [
            ModelInst(t, ModelType.Checkpoint, DownloadMethod.Wget, "https://civitai.com/api/download/models/256915", "cyberrealistic"),
            ModelInst(t, ModelType.Checkpoint, DownloadMethod.Wget, "https://civitai.com/api/download/models/245598?type=Model&format=SafeTensor&size=pruned&fp=fp16", "realisticvision"),
            ModelInst(t, ModelType.Checkpoint, DownloadMethod.Wget, "https://civitai.com/api/download/models/128713?type=Model&format=SafeTensor&size=pruned&fp=fp16", "dreamshaper"),
            ModelInst(t, ModelType.Checkpoint, DownloadMethod.Wget, "https://civitai.com/api/download/models/143906?type=Model&format=SafeTensor&size=pruned&fp=fp16", "epic_realism_vae"),
            ModelInst(t, ModelType.Checkpoint, DownloadMethod.Wget, "https://civitai.com/api/download/models/251662", "dreamshaper_xl"),
            ModelInst(t, ModelType.Lora, DownloadMethod.Wget, "https://drive.usercontent.google.com/download?id=1WOAizZJY4g4qO8nGWOW2UuMLvbI3bWsM&export=download&authuser=0&confirm=t&uuid=2754e049-8f00-4b61-af55-974da0d86cf4&at=APZUnTVuxLuA5FGY9HgGSYyqScEe%3A1705351998875", "lara"),
            ModelInst(t, ModelType.Lora, DownloadMethod.Wget, "https://civitai.com/api/download/models/260383?type=Model&format=SafeTensor", "Muscle_bimbo"),
            ModelInst(t, ModelType.Lora, DownloadMethod.Wget, "https://civitai.com/api/download/models/281780?type=Model&format=SafeTensor", "Muscle_mgm"),
            ModelInst(t, ModelType.Lora, DownloadMethod.Wget, "https://civitai.com/api/download/models/87153?type=Model&format=SafeTensor", "Adetailer"),
            ModelInst(t, ModelType.Embedding, DownloadMethod.Wget, "https://civitai.com/api/download/models/77169?type=Model&format=PickleTensor", "BadDream", ext="pt"),
            ModelInst(t, ModelType.Embedding, DownloadMethod.Wget, "https://civitai.com/api/download/models/77173?type=Model&format=PickleTensor", "UnrealisticDream", ext="pt"),
            ModelInst(t, ModelType.ClipVision, DownloadMethod.Wget, "https://huggingface.co/InvokeAI/ip_adapter_sd_image_encoder/resolve/main/model.safetensors?download=true", "ip_adapter_sd_image_encoder"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15.safetensors", "ip-adapter_sd15"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_light.safetensors", "ip-adapter_sd15_light"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus_sd15.safetensors", "ip-adapter-plus_sd15"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus-face_sd15.safetensors", "ip-adapter-plus-face_sd15"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-full-face_sd15.safetensors", "ip-adapter-full-face_sd15"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_vit-G.safetensors", "ip-adapter_sd15_vit-G"),
            ModelInst(t, ModelType.Controlnet, DownloadMethod.Wget, "https://huggingface.co/webui/ControlNet-modules-safetensors/resolve/main/control_depth-fp16.safetensors?download=true", "control_depth-fp16"),
            ModelInst(t, ModelType.Controlnet, DownloadMethod.Wget, "https://huggingface.co/lllyasviel/control_v11f1e_sd15_tile/resolve/main/diffusion_pytorch_model.bin?download=true", "control_tile-fp16", ext="pth"),
            ModelInst(t, ModelType.Controlnet, DownloadMethod.Wget, "https://huggingface.co/lllyasviel/ControlNet-v1-1/resolve/main/control_v11p_sd15_softedge.pth?download=true", "control_softedge-fp16", ext="pth"),
            ModelInst(t, ModelType.CustomNode, DownloadMethod.Git, "https://github.com/ssitu/ComfyUI_UltimateSDUpscale", "ComfyUI_UltimateSDUpscale"),
        ]
        for model in models:
            model.install

ModelInstComfyUi()

# https://huggingface.co/lllyasviel/ControlNet-v1-1/tree/main #ctrlnet models
#https://huggingface.co/h94/IP-Adapter-FaceID/tree/main
# custom nodes
# - ComfyUI-Impact-Pack
# - controlnet
# - Essentials
# - Efficiency nodes 2.0+
# - Nimbus pack
# - ipadapter plus
# - reactor
# - sdultimtaeupscale
# - clipseg