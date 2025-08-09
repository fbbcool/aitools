from enum import Enum, auto
import os
import sys
import shutil
from typing import Final
from huggingface_hub import hf_hub_download
import requests
from tqdm import tqdm
from git import Repo  # pip install gitpython
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote


class DownloadMethod(Enum):
    Hugging = auto()
    Hugging2 = auto()
    Civitai = auto()
    Wget = auto()
    GDrive = auto()
    Git = auto()
class DownloadGroup(Enum):
    SD15 = auto()
    SDXL = auto()
    SDALL = auto()
    FLUX = auto()
    FLUX_REFINE = auto()
    HIDREAM = auto()
    KOHYASS_FLUX = auto()
    KOHYASS_SDXL = auto()
    FLUXGYM = auto()
    QWEN = auto()
    WAN21 = auto()
    WAN22 = auto()
    CURRENT = auto()
class TargetType(Enum):
    Comfy = auto()
    Kohyass = auto()
    Fluxgym = auto()
class ModelType(Enum):
    Checkpoint = auto()
    Controlnet = auto()
    Lora = auto()
    Embedding = auto()
    ClipVision = auto()
    Clip = auto()
    IPAdapter = auto()
    CustomNode = auto()
    Upscale = auto()
    VAE = auto()
    Unet = auto()
    DiffusionModel = auto()
    TextEncoder = auto()


class ModelInst:
    token_cai = os.environ.get("CAI_TOKEN", "")
    
    CHUNK_SIZE: Final = 1638400
    USER_AGENT: Final = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'

    def __init__(self, target: TargetType, model: ModelType, method: DownloadMethod, url: str, name: str="", ext:str ="safetensors") -> None:
        self.target = target
        self.model = model
        self.method = method
        self.url = url
        self.ext = ext
        self.repo = url
        self.path_local = name
        self.name = name
        if not name:
            self.name = os.path.basename(self.url)
            self.ext = ""
    
    def download_wget(self, url: str, fname: str):
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

    def download_hf_2(self, repo_id: str, filename: str, ofolder: str | Path) -> Path:
        ofolder_str = ""
        if isinstance(ofolder, Path):
            ofolder_str = str(ofolder)
        elif isinstance(ofolder, str):
            ofolder_str = ofolder
            ofolder = Path(ofolder)
        else:
            raise TypeError("ofolder has no correct type")
        ofile_str = hf_hub_download(repo_id=self.repo, filename=self.path_local, local_dir=ofolder_str)
        return Path(ofile_str)
    
    def download_hf(self, url: str, fname: str):
        urlp = urlparse(url)
        path = Path(urlp.path)
        config = {
            "urlp": urlp,
            "path": path,
            "stem": path.stem,
            "name": path.name,
            "parts": path.parts[1],
            "repo_id": str(Path(path.parts[1],path.parts[2])),
        }
        opath = str(Path(fname).parent)
        #filename = hf_hub_download(repo_id = config["repo_id"], filename = config["name"], local_dir=opath)
        hf_hub_download(repo_id = config["repo_id"], filename = config["name"], local_dir=opath)

    def download_civitai(self, url: str, fname: str):
        opath = str(Path(fname).parent)
        token = self.token_cai

        headers = {
            'Authorization': f'Bearer {token}',
            'User-Agent': self.USER_AGENT,
        }

        # Disable automatic redirect handling
        class NoRedirection(urllib.request.HTTPErrorProcessor):
            def http_response(self, request, response):
                return response
            https_response = http_response

        request = urllib.request.Request(url, headers=headers)
        opener = urllib.request.build_opener(NoRedirection)
        response = opener.open(request)

        if response.status in [301, 302, 303, 307, 308]:
            redirect_url = response.getheader('Location')

            # Extract filename from the redirect URL
            parsed_url = urlparse(redirect_url)
            query_params = parse_qs(parsed_url.query)
            content_disposition = query_params.get('response-content-disposition', [None])[0]

            if content_disposition:
                filename = unquote(content_disposition.split('filename=')[1].strip('"'))
            else:
                raise Exception('Unable to determine filename')

            response = urllib.request.urlopen(redirect_url)
        elif response.status == 404:
            raise Exception('File not found')
        else:
            raise Exception('No redirect found, something went wrong')

        total_size = response.getheader('Content-Length')

        if total_size is not None:
            total_size = int(total_size)

        output_file = os.path.join(opath, filename)

        with open(output_file, 'wb') as f:
            downloaded = 0
            start_time = time.time()

            while True:
                chunk_start_time = time.time()
                buffer = response.read(self.CHUNK_SIZE)
                chunk_end_time = time.time()

                if not buffer:
                    break

                downloaded += len(buffer)
                f.write(buffer)
                chunk_time = chunk_end_time - chunk_start_time

                if chunk_time > 0:
                    speed = len(buffer) / chunk_time / (1024 ** 2)  # Speed in MB/s

                if total_size is not None:
                    progress = downloaded / total_size
                    sys.stdout.write(f'\rDownloading: {filename} [{progress*100:.2f}%] - {speed:.2f} MB/s')
                    sys.stdout.flush()

        end_time = time.time()
        time_taken = end_time - start_time
        hours, remainder = divmod(time_taken, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            time_str = f'{int(hours)}h {int(minutes)}m {int(seconds)}s'
        elif minutes > 0:
            time_str = f'{int(minutes)}m {int(seconds)}s'
        else:
            time_str = f'{int(seconds)}s'

        sys.stdout.write('\n')
        print(f'Download completed. File saved as: {filename}')
        print(f'Downloaded in {time_str}')

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
        self.path_model.mkdir(parents=True, exist_ok=True) 
        try:
            if self.method == DownloadMethod.Hugging2:
                repo_id = self.repo
                filename = self.path_local
                print(f"installing from hugging_2: {repo_id} / {filename} -> {self.path_model}")
                file_hf = hf_hub_download(repo_id=self.repo, filename=self.path_local)
                # symbolic link to of file_hf to self.path_model folder
                file_hf_path = Path(file_hf)
                target_path = self.path_model / file_hf_path.name
                
                # Check if the target file already exists and is a symlink to the correct source
                if target_path.is_symlink() and target_path.resolve() == file_hf_path.resolve():
                    print(f"Symlink already exists and is correct: {target_path} -> {file_hf_path}")
                elif target_path.exists():
                    # If it exists but is not a symlink or points to the wrong place, remove it
                    print(f"Removing existing file/symlink at {target_path} to create new symlink.")
                    if target_path.is_dir():
                        shutil.rmtree(target_path)
                    else:
                        os.remove(target_path)
                    os.symlink(file_hf_path, target_path)
                    print(f"Created symlink: {target_path} -> {file_hf_path}")
                else:
                    # If it doesn't exist, create the symlink
                    os.symlink(file_hf_path, target_path)
                    print(f"Created symlink: {target_path} -> {file_hf_path}")

            if self.method == DownloadMethod.Hugging:
                url_model = self.path_model / self.name
                print(f"installing from hugging: {self.url} -> {url_model}")
                self.download_hf(self.url, str(url_model))
            
            if self.method == DownloadMethod.Wget:
                url_model = self.path_model / self.name
                print(f"installing from wget: {self.url} -> {url_model}")
                self.download_wget(self.url, str(url_model))
                

            if self.method == DownloadMethod.Civitai:
                print(f"installing from hugging: {self.url} -> {url_model}")
                self.download_civitai(self.url, url_model)
                
            if self.method == DownloadMethod.GDrive:
                print(f"(NO)installing from gdrive: {self.url} -> {url_model}")
                #gdown.download(id = self.url, output = url_model)

            if self.method == DownloadMethod.Git:
                url_account = self.repo
                name_repo = self.path_local

                repo_ext = Path(url_account) / name_repo
                repo_local = Path(self.path_model) / name_repo
                POST_HOOK.add_line(f"git clone https://{repo_ext} {repo_local}")
                file_requirements = repo_local / "requirements.txt"
                POST_HOOK.add_line(f"if [ -e {str(file_requirements)} ]; then")
                POST_HOOK.add_line(f"\tpip install -r {str(file_requirements)}")
                POST_HOOK.add_line("fi")
        except Exception as e:
            print(f"sth went wrong:\n{e}")

    @property
    def path_model(self) -> Path:
        path_models = Path()
        folder_model = ""
        
        if self.target == TargetType.Comfy:
            path_models = Path("/workspace/ComfyUI/models")
            if self.model == ModelType.Checkpoint:
                folder_model = "ckpt"
            elif self.model == ModelType.VAE:
                folder_model = "vae"
            elif self.model == ModelType.Controlnet:
                folder_model = "controlnet"
            elif self.model == ModelType.CustomNode:
                folder_model = "../custom_nodes"
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
            elif self.model == ModelType.Upscale:
                folder_model = "upscale_models"
            elif self.model == ModelType.DiffusionModel:
                folder_model = "diffusion_models"
            elif self.model == ModelType.TextEncoder:
                folder_model = "text_encoders"
        
        if self.target == TargetType.Kohyass:
            path_models = Path("/workspace/kohya_ss/models")
            if self.model == ModelType.Checkpoint:
                folder_model = "ckpt"
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
        
        return path_models / folder_model
    
class ModelInstComfyUi:
    def __init__(self, group = DownloadGroup.SD15) -> None:
        wget = DownloadMethod.Wget
        hf = DownloadMethod.Hugging
        hf2 = DownloadMethod.Hugging2
        cai = DownloadMethod.Civitai
        git = DownloadMethod.Git

        t = TargetType.Comfy
        models_flux_refine: list[ModelInst] = [
            # flux1-dev fp16
            #ModelInst(t, ModelType.Checkpoint, hf, "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors?download=true", ""),
            # flux1-dev Q8
            #ModelInst(t, ModelType.Unet, hf, "https://huggingface.co/city96/FLUX.1-dev-gguf/resolve/main/flux1-dev-Q8_0.gguf?download=true", ""),
            # flux1-kontext Q8
            #ModelInst(t, ModelType.Unet, hf, "https://huggingface.co/QuantStack/FLUX.1-Kontext-dev-GGUF/resolve/main/flux1-kontext-dev-Q8_0.gguf?download=true", ""),
            # fluxed fp8
            #ModelInst(t, ModelType.Checkpoint, cai, "https://civitai.com/api/download/models/1938215?type=Model&format=SafeTensor&size=pruned&fp=fp8", ""),
            # aphrodite fp16
            #ModelInst(t, ModelType.Checkpoint, cai, "https://civitai.com/api/download/models/897489?type=Model&format=SafeTensor&size=full&fp=fp16", ""),
            # flux reality nsfw fp8
            #ModelInst(t, ModelType.Unet, cai, "https://civitai.com/api/download/models/1908093?type=Model&format=SafeTensor&size=full&fp=fp8", ""),
            # 1gts
            ModelInst(t, ModelType.Unet, hf2, "fbbcool/1gts", "1gts_base.safetensors", ""),

            # VAE
            ModelInst(t, ModelType.VAE, hf2, "black-forest-labs/FLUX.1-dev", "ae.safetensors", ""),

            # clip
            ModelInst(t, ModelType.Clip, hf2, "comfyanonymous/flux_text_encoders", "clip_l.safetensors", ""),
            ModelInst(t, ModelType.Clip, hf2, "city96/t5-v1_1-xxl-encoder-gguf", "t5-v1_1-xxl-encoder-Q8_0.gguf", ""),
            
            # control
            #ModelInst(t, ModelType.Controlnet, hf, "https://huggingface.co/Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro/resolve/main/diffusion_pytorch_model.safetensors?download=true", ""),
            
            # lora
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts", "1gts_r5_afro-mid.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts", "1gts_r5-low.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts", "1gts_chloe.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts", "1gts_cock.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts", "1gts_breast.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts", "1gts_chubby.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts", "1gts_muscle.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts", "1gts_nhj.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts", "1gts_cumshot.safetensors", ""),

            
            # flux fill
            ModelInst(t, ModelType.Unet, hf2, "YarvixPA/FLUX.1-Fill-dev-gguf", "flux1-fill-dev-Q8_0.gguf", ""),
        ]
        t = TargetType.Comfy
        models_current: list[ModelInst] = [
            # MVP first
            # checkpoint
            #ModelInst(t, ModelType.DiffusionModel, hf2, "", "", ""),
            
            # VAE
            #ModelInst(t, ModelType.VAE, hf2, "", "", ""),
            
            # clip
            #ModelInst(t, ModelType.TextEncoder, hf2, "", "", ""),
            
            # lora
            #ModelInst(t, ModelType.Lora, hf2, "", "", ""),
            
            # upscale
            ModelInst(t, ModelType.Upscale, hf2, "ai-forever/Real-ESRGAN", "RealESRGAN_x2.pth", ""),
            ModelInst(t, ModelType.Upscale, hf2, "ai-forever/Real-ESRGAN", "RealESRGAN_x4.pth", ""),

            # additional checkpoints
            
            # additional loras

            #clip vision
            
            # custom nodes
            # to comfyui-frame-interpolation/ckpts/stmfnet/
            #ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/city96", "ComfyUI-GGUF", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/rgthree", "rgthree-comfy", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/yolain", "ComfyUI-Easy-Use", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/kijai", "ComfyUI-KJNodes", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/ssitu", "ComfyUI_UltimateSDUpscale", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/cubiq", "ComfyUI_essentials", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/Zehong-Ma", "ComfyUI-MagCache", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/ltdrdata", "ComfyUI-Inspire-Pack", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/Derfuu", "Derfuu_ComfyUI_ModdedNodes", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/Kosinkadink", "ComfyUI-VideoHelperSuite", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/kijai", "ComfyUI-WanVideoWrapper", ""),
        ]

        models_qwen: list[ModelInst] = [
            # MVP first
            # checkpoint
            #ModelInst(t, ModelType.DiffusionModel, hf2, "", "", ""),
            ModelInst(t, ModelType.DiffusionModel, hf2, "Comfy-Org/Qwen-Image_ComfyUI", "split_files/diffusion_models/qwen_image_fp8_e4m3fn.safetensors", ""),
            
            # VAE
            #ModelInst(t, ModelType.VAE, hf2, "", "", ""),
            ModelInst(t, ModelType.VAE, hf2, "Comfy-Org/Qwen-Image_ComfyUI", "split_files/vae/qwen_image_vae.safetensors", ""),
            
            # clip
            #ModelInst(t, ModelType.TextEncoder, hf2, "", "", ""),
            ModelInst(t, ModelType.TextEncoder, hf2, "Comfy-Org/Qwen-Image_ComfyUI", "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors", ""),
            
            # lora
            #ModelInst(t, ModelType.Lora, hf2, "", "", ""),
            
            # upscale
            ModelInst(t, ModelType.Upscale, hf2, "ai-forever/Real-ESRGAN", "RealESRGAN_x2.pth", ""),
            ModelInst(t, ModelType.Upscale, hf2, "ai-forever/Real-ESRGAN", "RealESRGAN_x4.pth", ""),

            # additional checkpoints
            
            # additional loras

            #clip vision
            
            # custom nodes
            # to comfyui-frame-interpolation/ckpts/stmfnet/
            #ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/city96", "ComfyUI-GGUF", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/rgthree", "rgthree-comfy", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/yolain", "ComfyUI-Easy-Use", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/kijai", "ComfyUI-KJNodes", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/ssitu", "ComfyUI_UltimateSDUpscale", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/cubiq", "ComfyUI_essentials", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/Zehong-Ma", "ComfyUI-MagCache", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/ltdrdata", "ComfyUI-Inspire-Pack", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/Derfuu", "Derfuu_ComfyUI_ModdedNodes", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/Kosinkadink", "ComfyUI-VideoHelperSuite", ""),
            #ModelInst(t, ModelType.CustomNode, git, "github.com/kijai", "ComfyUI-WanVideoWrapper", ""),
        ]

        t = TargetType.Comfy
        models_wan21: list[ModelInst] = [
            # MVP first
            # checkpoint
            ModelInst(t, ModelType.Unet, hf2, "NSFW-API/NSFW_Wan_14b", "nsfw_wan_14b_e15_fp8.safetensors", ""),
            
            # VAE
            ModelInst(t, ModelType.VAE, hf2, "Kijai/WanVideo_comfy", "Wan2_1_VAE_bf16.safetensors", ""),
            #ModelInst(t, ModelType.VAE, hf2, "Kijai/WanVideo_comfy", "Wan2_1_VAE_fp32.safetensors", ""),
            
            # clip
            #ModelInst(t, ModelType.Clip, hf2, "Aitrepreneur/FLX", "umt5-xxl-encoder-Q5_K_S.gguf", ""),
            ModelInst(t, ModelType.Clip, hf2, "Kijai/WanVideo_comfy", "umt5-xxl-enc-fp8_e4m3fn.safetensors", ""),
            
            # lora
            ModelInst(t, ModelType.Lora, hf2, "Kijai/WanVideo_comfy", "Pusa/Wan21_PusaV1_LoRA_14B_rank512_bf16.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "lightx2v/Wan2.1-T2V-14B-StepDistill-CfgDistill-Lightx2v", "loras/Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts_wan", "1gts_mid.safetensors", ""),
            #ModelInst(t, ModelType.Lora, hf2, "Aitrepreneur/FLX", "Wan2.1_T2V_14B_FusionX_LoRA.safetensors", ""),
            #ModelInst(t, ModelType.Lora, hf2, "Aitrepreneur/FLX", "Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank32.safetensors", ""),
            
            # upscale
            ModelInst(t, ModelType.Upscale, hf2, "ai-forever/Real-ESRGAN", "RealESRGAN_x2.pth", ""),
            ModelInst(t, ModelType.Upscale, hf2, "ai-forever/Real-ESRGAN", "RealESRGAN_x4.pth", ""),
            # custom nodes
            ModelInst(t, ModelType.CustomNode, hf2, "camenduru/stmfnet", "stmfnet.pth", ""),

            # checkpoint

            # VAE

            # clip

            #clip vision
            
            # lora
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts_wan", "1woman_lara.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts_wan", "1gts_cum.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts_wan", "1gts_deepthroat.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts_wan", "1gts_SmokeMonday.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts_wan", "1gts_Sophie.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts_wan", "1gts_dreamjob.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts_wan", "1dreamplay.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts_wan", "1gts_boobphysics.safetensors", ""),
            ModelInst(t, ModelType.Lora, hf2, "fbbcool/1gts_wan", "SECRET_SAUCE_WAN2.1_14B_fp8.safetensors", ""),
        
            # custom nodes
            # to comfyui-frame-interpolation/ckpts/stmfnet/
            ModelInst(t, ModelType.CustomNode, hf2, "camenduru/stmfnet", "stmfnet.pth", ""),
            #ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/city96", "ComfyUI-GGUF", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/rgthree", "rgthree-comfy", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/yolain", "ComfyUI-Easy-Use", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/kijai", "ComfyUI-KJNodes", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/ssitu", "ComfyUI_UltimateSDUpscale", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/cubiq", "ComfyUI_essentials", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/Zehong-Ma", "ComfyUI-MagCache", ""),
            # do w/ comfyui manager
            #ModelInst(t, ModelType.CustomNode, git, "github.com/Fannovel16", "ComfyUI-Frame-Interpolation", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/ltdrdata", "ComfyUI-Inspire-Pack", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/Derfuu", "Derfuu_ComfyUI_ModdedNodes", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/Kosinkadink", "ComfyUI-VideoHelperSuite", ""),
            ModelInst(t, ModelType.CustomNode, git, "github.com/kijai", "ComfyUI-WanVideoWrapper", ""),
            ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            #ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            #git clone https://github.com/Fannovel16/comfyui_controlnet_aux
            #git clone https://github.com/wallish77/wlsh_nodes
            #git clone https://github.com/vrgamegirl19/comfyui-vrgamedevgirl
        ]

        model_db = {
            DownloadGroup.FLUX_REFINE: models_flux_refine,
            DownloadGroup.CURRENT: models_current,
            DownloadGroup.WAN21: models_wan21,
            DownloadGroup.QWEN: models_qwen,
        }
        for model in model_db[group]:
            model.install

class PostInstHook():
    def __init__(self) -> None:
        URL_HOOK: Final = os.environ.get("ENV_POST_HOOK")
        self.lines: list[str] = []
        self.path: Path = Path(URL_HOOK)
    
    def add_line(self, line: str) -> None:
        self.lines.append(line)

    def save(self) -> None:
        if not self.lines:
            return
        with self.path.open("w") as f:
            for line in self.lines:
                f.write(line + "\n")
        os.chmod(self.path, 0o755) # Make the script executable
        print(f"Post-install hook script written to\n{self.path}")

POST_HOOK: Final = PostInstHook()


def _hook_wan21():
    # print the name of this method
    #print(sys._getframe(0).f_code.co_name)

    POST_HOOK.add_line(f"# hook by current")
    dir_fi_model = "/workspace/ComfyUI/custom_nodes/comfyui-frame-interpolation/ckpts/stmfnet"
    POST_HOOK.add_line(f"mkdir -p {dir_fi_model}")
    POST_HOOK.add_line(f"cp /workspace/ComfyUI/custom_nodes/stmfnet.pth {dir_fi_model}")

            
    print("\t!!!_hook_current!!!")

hook = None
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
    elif str_group == "flux_refine":
        group = DownloadGroup.FLUX_REFINE
    elif str_group == "hidream":
        group = DownloadGroup.HIDREAM
    elif str_group == "fluxgym":
        group = DownloadGroup.FLUXGYM
    elif str_group == "kohyass_flux":
        group = DownloadGroup.KOHYASS_FLUX
    elif str_group == "kohyass_sdxl":
        group = DownloadGroup.KOHYASS_SDXL
    elif str_group == "qwen":
        group = DownloadGroup.QWEN
    elif str_group == "wan21":
        hook = _hook_wan21 
        group = DownloadGroup.WAN21
    elif str_group == "current":
        group = DownloadGroup.CURRENT
    else:
        str_group = "current"
        group = DownloadGroup.SD15
    

    print(f"using download group {str_group}.")
    ModelInstComfyUi(group=group)
    if hook is not None:
        print(f"creating post hook.")
        hook()
    POST_HOOK.save()
