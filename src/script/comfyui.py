from enum import Enum, auto
import os
import shutil
from typing import Final
from huggingface_hub import hf_hub_download
import requests
import wget
import gdown

class DownloadMethod(Enum):
    Hugging = auto()
    Wget = auto()
    GDrive = auto()
class TargetType(Enum):
    Comfy = auto()
    SD = auto()
    Kohyass = auto()
class ModelType(Enum):
    Checkpoint = auto()
    Controlnet = auto()
    Lora = auto()
    ClipVision = auto()
    IPAdapter = auto()


class ModelInst:
    UrlStorageModels: Final = "/workspace/storage/stable_diffusion/models"
    def __init__(self, target: TargetType, model: ModelType, method: DownloadMethod, url: str, name: str) -> None:
        self.target = target
        self.model = model
        self.method = method
        self.url = url
        self.ext = "safetensors"
        self.name = name
    

    def url_download(self, url: str) -> str:
        local_filename = url.split('/')[-1]
        with requests.get(url, stream=True) as r:
            with open(local_filename, 'wb') as f:
                shutil.copyfileobj(r.raw, f)

        return local_filename
    
    @classmethod
    def url_exit(cls, url: str) -> bool:
        return os.path.isfile(url) or os.path.isdir(url)
    
    @property
    def install(self, force: bool = False) -> None:
        url_model = f"{self.url_models}/{self.name}.{self.ext}"
        
        if not force:
            if ModelInst.url_exit(url_model):
                return
        
        if self.method == DownloadMethod.Hugging:
            print(f"installing from hugging: {self.url} -> {url_model}")
            url_split = self.url.split("/")
            filename = hf_hub_download(repo_id = f"{url_split[0]}/{url_split[1]}", filename = url_split[2])
            shutil.move(filename, url_model)
            
        if self.method == DownloadMethod.Wget:
            print(f"installing by wget: {self.url} -> {url_model}")
            #filename = wget.download(self.url)
            filename = self.url_download(self.url)
            shutil.move(filename, url_model)

        if self.method == DownloadMethod.GDrive:
            print(f"installing from gdrive: {self.url} -> {url_model}")
            gdown.download(id = self.url, output = url_model)

    @property
    def url_models(self) -> str:
        if self.target == TargetType.Comfy:
            if self.model == ModelType.Checkpoint:
                return "/opt/ComfyUI/models/checkpoints"
            if self.model == ModelType.Controlnet:
                return "/opt/ComfyUI/models/controlnet"
            if self.model == ModelType.Lora:
                return "/opt/ComfyUI/models/loras"
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
            ModelInst(t, ModelType.Checkpoint, DownloadMethod.Wget, "https://civitai.com/api/download/models/128713?type=Model&format=SafeTensor&size=pruned&fp=fp16", "dreamshaper"),
            #ModelInst(t, ModelType.Lora, DownloadMethod.GDrive, "1WOAizZJY4g4qO8nGWOW2UuMLvbI3bWsM", "lara"),
            ModelInst(t, ModelType.Lora, DownloadMethod.Wget, "https://drive.usercontent.google.com/download?id=1WOAizZJY4g4qO8nGWOW2UuMLvbI3bWsM&export=download&authuser=0&confirm=t&uuid=2754e049-8f00-4b61-af55-974da0d86cf4&at=APZUnTVuxLuA5FGY9HgGSYyqScEe%3A1705351998875", "lara"),
            ModelInst(t, ModelType.Lora, DownloadMethod.Wget, "https://civitai.com/api/download/models/260383?type=Model&format=SafeTensor", "Muscle_bimbo"),
            ModelInst(t, ModelType.ClipVision, DownloadMethod.Wget, "https://huggingface.co/InvokeAI/ip_adapter_sd_image_encoder/resolve/main/model.safetensors?download=true", "ip_adapter_sd_image_encoder"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15.safetensors", "ip-adapter_sd15"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_light.safetensors", "ip-adapter_sd15_light"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus_sd15.safetensors", "ip-adapter-plus_sd15"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus-face_sd15.safetensors", "ip-adapter-plus-face_sd15.safetensors"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-full-face_sd15.safetensors", "ip-adapter-full-face_sd15"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_vit-G.safetensors", "ip-adapter_sd15_vit-G"),
            ModelInst(t, ModelType.Controlnet, DownloadMethod.Wget, "https://huggingface.co/webui/ControlNet-modules-safetensors/resolve/main/control_depth-fp16.safetensors?download=true", "control_depth-fp16.safetensors"),
            ModelInst(t, ModelType.Controlnet, DownloadMethod.Wget, "https://huggingface.co/webui/ControlNet-modules-safetensors/resolve/main/control_tiles-fp16.safetensors?download=true", "control_tiles-fp16.safetensors"),
        ]
        for model in models:
            model.install

ModelInstComfyUi()

# https://huggingface.co/lllyasviel/ControlNet-v1-1/tree/main #ctrlnet models