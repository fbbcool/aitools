from enum import Enum, auto
import os
import shutil
from typing import Final
from huggingface_hub import hf_hub_download
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
            filename = wget.download(self.url)
            shutil.move(filename, url_model)

        if self.method == DownloadMethod.GDrive:
            print(f"installing from gdrive: {self.url} -> {url_model}")
            gdown.download(id = self.url, output = url_model)

    @property
    def url_models(self) -> str:
        if self.target == TargetType.Comfy:
            if self.model == ModelType.Checkpoint:
                return "/opt/ComfyUi/models/ckpt"
            if self.model == ModelType.Controlnet:
                return "/opt/ComfyUi/models/controllnet"
            if self.model == ModelType.Lora:
                return "/opt/ComfyUi/models/loras"
            if self.model == ModelType.ClipVision:
                return "/opt/ComfyUi/models/clip_vision"
            if self.model == ModelType.IPAdapter:
                return "/opt/ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus/models"
        raise ValueError("Dir Models unknown!")
    
class ModelInstComfyUi:
    def __init__(self) -> None:
        t = TargetType.Comfy
        models: list[ModelInst] = [
            ModelInst(t, ModelType.Checkpoint, DownloadMethod.Wget, "https://civitai.com/api/download/models/256915", "cyberrealistic"),
            ModelInst(t, ModelType.Checkpoint, DownloadMethod.Wget, "https://civitai.com/api/download/models/128713?type=Model&format=SafeTensor&size=pruned&fp=fp16", "dreamshaper"),
            ModelInst(t, ModelType.Lora, DownloadMethod.GDrive, "1WOAizZJY4g4qO8nGWOW2UuMLvbI3bWsM", "lara"),
            ModelInst(t, ModelType.Lora, DownloadMethod.Wget, "https://civitai.com/api/download/models/260383?type=Model&format=SafeTensor", "Muscle_bimbo"),
            ModelInst(t, ModelType.ClipVision, DownloadMethod.Hugging, "InvokeAI/ip_adapter_sd_image_encoder/model.safetensors", "ip_adapter_sd_image_encoder"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15.safetensors", "ip-adapter_sd15"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_light.safetensors", "ip-adapter_sd15_light"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus_sd15.safetensors", "ip-adapter-plus_sd15"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-plus-face_sd15.safetensors", "ip-adapter-plus-face_sd15.safetensors"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter-full-face_sd15.safetensors", "ip-adapter-full-face_sd15"),
            ModelInst(t, ModelType.IPAdapter, DownloadMethod.Wget, "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15_vit-G.safetensors", "ip-adapter_sd15_vit-G"),
        ]
        for model in models:
            model.install

ModelInstComfyUi()