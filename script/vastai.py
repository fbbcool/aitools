from enum import Enum, auto
import os
import sys
from typing import Final
from huggingface_hub import hf_hub_download, snapshot_download
import requests
from tqdm import tqdm
from git import Repo  # pip install gitpython
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote


class DownloadMethod(Enum):
    Hugging = auto()
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
    QWEN_EDIT = auto()
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
    Vae = auto()
    Unet = auto()
    DiffusionModel = auto()
    TextEncoder = auto()


class ModelInst:
    token_cai = os.environ.get("CAI_TOKEN", "")

    CHUNK_SIZE: Final = 1638400
    USER_AGENT: Final = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"  # noqa

    def __init__(
        self,
        target: TargetType,
        model: ModelType,
        method_dl: DownloadMethod,
        repo_id: str,
        file: str = "",
        method_gen: str | None = None,
    ) -> None:
        self.target = target
        self.model = model
        self.method_dl = method_dl
        self.method_gen = method_gen
        self.url = repo_id
        self.repo = repo_id
        self.path_local = file
        self.name = file
        if not file:
            self.name = os.path.basename(self.url)
            self.ext = ""

    def download_hf(self, repo_id: str, filename: str, ofolder: str | Path) -> Path:
        ofolder_str = ""
        if isinstance(ofolder, Path):
            ofolder_str = str(ofolder)
        elif isinstance(ofolder, str):
            ofolder_str = ofolder
            ofolder = Path(ofolder)
        else:
            raise TypeError("ofolder has no correct type")

        if not filename:
            # use snaphot download
            link = snapshot_download(repo_id=repo_id, local_dir=ofolder_str)
        else:
            # use hf download
            link = hf_hub_download(
                repo_id=self.repo, filename=self.path_local, local_dir=ofolder_str
            )

        return Path(link)

    def download_wget(self, url: str, fname: str):
        resp = requests.get(url, stream=True)
        total = int(resp.headers.get("content-length", 0))

        fopath, _ = os.path.split(fname)
        if not os.path.exists(fopath):
            os.makedirs(fopath)
        try:
            with (
                open(fname, "wb") as file,
                tqdm(
                    desc=fname,
                    total=total,
                    unit="iB",
                    unit_scale=True,
                    unit_divisor=1024,
                ) as bar,
            ):
                for data in resp.iter_content(chunk_size=1024):
                    size = file.write(data)
                    bar.update(size)
        except Exception as e:
            print(f"Url download went wrong: {url}")
            print(e)

    def download_civitai(self, url: str, fname: str):
        opath = str(Path(fname).parent)
        token = self.token_cai

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": self.USER_AGENT,
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
            redirect_url = response.getheader("Location")

            # Extract filename from the redirect URL
            parsed_url = urlparse(redirect_url)
            query_params = parse_qs(parsed_url.query)
            content_disposition = query_params.get(
                "response-content-disposition", [None]
            )[0]

            if content_disposition:
                filename = unquote(content_disposition.split("filename=")[1].strip('"'))
            else:
                raise Exception("Unable to determine filename")

            response = urllib.request.urlopen(redirect_url)
        elif response.status == 404:
            raise Exception("File not found")
        else:
            raise Exception("No redirect found, something went wrong")

        total_size = response.getheader("Content-Length")

        if total_size is not None:
            total_size = int(total_size)

        output_file = os.path.join(opath, filename)

        with open(output_file, "wb") as f:
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
                    speed = len(buffer) / chunk_time / (1024**2)  # Speed in MB/s

                if total_size is not None:
                    progress = downloaded / total_size
                    sys.stdout.write(
                        f"\rDownloading: {filename} [{progress * 100:.2f}%] - {
                            speed:.2f} MB/s"
                    )
                    sys.stdout.flush()

        end_time = time.time()
        time_taken = end_time - start_time
        hours, remainder = divmod(time_taken, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            time_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
        elif minutes > 0:
            time_str = f"{int(minutes)}m {int(seconds)}s"
        else:
            time_str = f"{int(seconds)}s"

        sys.stdout.write("\n")
        print(f"Download completed. File saved as: {filename}")
        print(f"Downloaded in {time_str}")

    def git_clone(self, url: str, folder: str) -> None:
        try:
            Repo.clone_from(url, folder, recursive=True)
        except Exception as e:
            print(f"Url git clone went wrong: {url} -> {folder}")
            print(e)

    @classmethod
    def url_exit(cls, url: str) -> bool:
        return os.path.isfile(url) or os.path.isdir(url)

    @property
    def install(self) -> None:
        self.path_model.mkdir(parents=True, exist_ok=True)
        try:
            if self.method_dl == DownloadMethod.Hugging:
                repo_id = self.repo
                filename = self.path_local
                print(
                    f"installing from HF: {repo_id} / {filename} -> {self.path_model}"
                )
                if not filename:
                    # use snaphot download
                    snapshot_download(
                        repo_id=self.repo,
                        local_dir=self.path_model,
                    )
                else:
                    # use hf download
                    hf_hub_download(
                        repo_id=self.repo,
                        filename=self.path_local,
                        local_dir=self.path_model,
                    )

            if self.method_dl == DownloadMethod.Wget:
                url_model = self.path_model / self.name
                print(f"installing from wget: {self.url} -> {url_model}")
                self.download_wget(self.url, str(url_model))

            if self.method_dl == DownloadMethod.Civitai:
                print(f"installing from hugging: {self.url} -> {url_model}")
                self.download_civitai(self.url, url_model)

            if self.method_dl == DownloadMethod.GDrive:
                print(f"(NO)installing from gdrive: {self.url} -> {url_model}")
                # gdown.download(id = self.url, output = url_model)

            if self.method_dl == DownloadMethod.Git:
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
        # get from comfyui environment
        home_comfy: str | None = os.environ.get("HOME_COMFY", None)
        if home_comfy is None:
            # get from ENV_WORKSPACE environment
            home_comfy = Path(os.environ.get("ENV_WORKSPACE", "/workspace")) / "ComfyUI"

        path_models = Path(home_comfy)

        map_dir_models = {
            ModelType.Checkpoint: "ckpt",
            ModelType.Vae: "vae",
            ModelType.Controlnet: "controlnet",
            ModelType.CustomNode: "../custom_nodes",
            ModelType.Lora: "loras",
            ModelType.Embedding: "embeddings",
            ModelType.Clip: "clip",
            ModelType.ClipVision: "clip_vision",
            ModelType.IPAdapter: "ipadapter",
            ModelType.Unet: "unet",
            ModelType.Upscale: "upscale_models",
            ModelType.DiffusionModel: "diffusion_models",
            ModelType.TextEncoder: "text_encoders",
        }

        if self.target == TargetType.Comfy:
            path_models = path_models / "ComfyUI/models"
            dir_model = map_dir_models.get(self.model, None)

        if self.target == TargetType.Kohyass:
            path_models = path_models / "kohya_ss/models"
            dir_model = map_dir_models.get(self.model, None)

        if not dir_model:
            raise ValueError("Dir Models unknown!")

        return path_models / dir_model


class ModelInstComfyUi:
    def __init__(self, group=DownloadGroup.SD15, method_gen: str | None = None) -> None:
        hf = DownloadMethod.Hugging
        git = DownloadMethod.Git
        # wget = DownloadMethod.Wget
        # cai = DownloadMethod.Civitai

        #
        # COMMON
        #
        t = TargetType.Comfy
        models_common: list[ModelInst] = [
            # MVP first
            # checkpoint
            # ModelInst(t, ModelType.DiffusionModel, hf, "", "", ""),
            # VAE
            # ModelInst(t, ModelType.VAE, hf, "", "", ""),
            # clip
            # ModelInst(t, ModelType.TextEncoder, hf, "", "", ""),
            # lora
            # ModelInst(t, ModelType.Lora, hf, "", "", ""),
            # upscale
            ModelInst(
                t,
                ModelType.Upscale,
                hf,
                "ai-forever/Real-ESRGAN",
                "RealESRGAN_x2.pth",
                "",
            ),
            ModelInst(
                t,
                ModelType.Upscale,
                hf,
                "ai-forever/Real-ESRGAN",
                "RealESRGAN_x4.pth",
                "",
            ),
            # additional checkpoints
            # additional loras
            # clip vision
            # custom nodes
            # to comfyui-frame-interpolation/ckpts/stmfnet/
            # ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            # ModelInst(t, ModelType.CustomNode, git, "github.com/city96", "ComfyUI-GGUF", ""),
            ModelInst(
                t, ModelType.CustomNode, git, "github.com/rgthree", "rgthree-comfy", ""
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/yolain",
                "ComfyUI-Easy-Use",
                "",
            ),
            ModelInst(
                t, ModelType.CustomNode, git, "github.com/kijai", "ComfyUI-KJNodes", ""
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/ssitu",
                "ComfyUI_UltimateSDUpscale",
                "",
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/cubiq",
                "ComfyUI_essentials",
                "",
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/ltdrdata",
                "ComfyUI-Inspire-Pack",
                "",
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/Derfuu",
                "Derfuu_ComfyUI_ModdedNodes",
                "",
            ),
        ]

        #
        # qwen
        #
        t = TargetType.Comfy
        models_qwen: list[ModelInst] = [
            # MVP first
            # checkpoint
            # ModelInst(t, ModelType.DiffusionModel, hf, "", "", ""),
            ModelInst(
                t,
                ModelType.DiffusionModel,
                hf,
                "Comfy-Org/Qwen-Image_ComfyUI",
                "split_files/diffusion_models/qwen_image_fp8_e4m3fn.safetensors",
                "",
            ),
            # https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_fp8_e4m3fn.safetensors?download=true
            # VAE
            # ModelInst(t, ModelType.VAE, hf, "", "", ""),
            ModelInst(
                t,
                ModelType.Vae,
                hf,
                "Comfy-Org/Qwen-Image_ComfyUI",
                "split_files/vae/qwen_image_vae.safetensors",
                "",
            ),
            # clip
            # ModelInst(t, ModelType.TextEncoder, hf, "", "", ""),
            ModelInst(
                t,
                ModelType.TextEncoder,
                hf,
                "Comfy-Org/Qwen-Image_ComfyUI",
                "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "",
            ),
            # lora lightning
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "lightx2v/Qwen-Image-Lightning",
                "Qwen-Image-Lightning-4steps-V2.0.safetensors",
                "",
            ),
            # lora
            # ModelInst(t, ModelType.Lora, hf, "", "", ""),
            ModelInst(t, ModelType.Lora, hf, "fbbcool/qwen-image", "", ""),
            # ModelInst(t, ModelType.Lora, hf, "fbbcool/qwen01", "1fbb-07.safetensors", ""),
            # ModelInst(t, ModelType.Lora, hf, "fbbcool/qwen01", "1fbb-14.safetensors", ""),
            # ModelInst(t, ModelType.Lora, hf, "fbbcool/qwen01", "1gts_r5-06.safetensors", ""),
            # upscale
            # ModelInst(t, ModelType.Upscale, hf, "ai-forever/Real-ESRGAN", "RealESRGAN_x2.pth", ""), # noqa
            # additional checkpoints
            # additional loras
            # clip vision
            # custom nodes
            # ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            # https://github.com/SXQBW/ComfyUI-Qwen-Omni
        ]

        #
        # QWEN-EDIT
        #
        t = TargetType.Comfy
        models_qwen_edit: list[ModelInst] = [
            # MVP first
            # checkpoint
            # ModelInst(t, ModelType.DiffusionModel, hf, "", "", ""),
            ModelInst(
                t,
                ModelType.Checkpoint,
                hf,
                "Phr00t/Qwen-Image-Edit-Rapid-AIO",
                "v7/Qwen-Rapid-AIO-NSFW-v7.1.safetensors",
                "",
            ),
            # ModelInst(
            #    t,
            #    ModelType.DiffusionModel,
            #    hf,
            #    "Comfy-Org/Qwen-Image-Edit_ComfyUI",
            #    "split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors",
            #    "",
            # ),
            # VAE
            # ModelInst(t, ModelType.VAE, hf, "", "", ""),
            ModelInst(
                t,
                ModelType.Vae,
                hf,
                "Comfy-Org/Qwen-Image_ComfyUI",
                "split_files/vae/qwen_image_vae.safetensors",
                "",
            ),
            # clip
            # ModelInst(t, ModelType.TextEncoder, hf, "", "", ""),
            ModelInst(
                t,
                ModelType.TextEncoder,
                hf,
                "Comfy-Org/Qwen-Image_ComfyUI",
                "split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "",
            ),
            # lora lightning
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "lightx2v/Qwen-Image-Lightning",
                "Qwen-Image-Lightning-4steps-V2.0.safetensors",
                "",
            ),
            # lora
            # ModelInst(t, ModelType.Lora, hf, "", "", ""),
            ModelInst(t, ModelType.Lora, hf, "fbbcool/qwen-image", "", ""),
            # ModelInst(t, ModelType.Lora, hf, "fbbcool/qwen01", "1fbb-07.safetensors", ""),
            # ModelInst(t, ModelType.Lora, hf, "fbbcool/qwen01", "1fbb-14.safetensors", ""),
            # ModelInst(t, ModelType.Lora, hf, "fbbcool/qwen01", "1gts_r5-06.safetensors", ""),
            # upscale
            # additional checkpoints
            # additional loras
            # clip vision
            # custom nodes
            # ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            # https://github.com/SXQBW/ComfyUI-Qwen-Omni
        ]

        #
        # wan21
        #
        t = TargetType.Comfy
        models_wan21: list[ModelInst] = [
            # MVP first
            # checkpoint
            ModelInst(
                t,
                ModelType.Unet,
                hf,
                "NSFW-API/NSFW_Wan_14b",
                "nsfw_wan_14b_e15_fp8.safetensors",
                "t2v",
            ),
            # VAE
            ModelInst(
                t,
                ModelType.Vae,
                hf,
                "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
                "split_files/vae/wan_2.1_vae.safetensors",
                "",
            ),
            # clip
            ModelInst(
                t,
                ModelType.Clip,
                hf,
                "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
                "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "",
            ),
            # lora
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "Kijai/WanVideo_comfy",
                "Pusa/Wan21_PusaV1_LoRA_14B_rank512_bf16.safetensors",
                "t2v",
            ),
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "lightx2v/Wan2.1-T2V-14B-StepDistill-CfgDistill-Lightx2v",
                "loras/Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors",
                "t2v",
            ),
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "lightx2v/Wan2.1-I2V-14B-StepDistill-CfgDistill-Lightx2v",
                "loras/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors",
                "i2v",
            ),
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "vrgamedevgirl84/Wan14BT2VFusioniX",
                "FusionX_LoRa/Wan2.1_T2V_14B_FusionX_LoRA.safetensors",
                "t2v",
            ),
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "vrgamedevgirl84/Wan14BT2VFusioniX",
                "FusionX_LoRa/Wan2.1_I2V_14B_FusionX_LoRA.safetensors",
                "i2v",
            ),
            ModelInst(
                t, ModelType.Lora, hf, "fbbcool/1gts_wan", "1gts_mid.safetensors", ""
            ),
            ModelInst(
                t, ModelType.CustomNode, hf, "camenduru/stmfnet", "stmfnet.pth", ""
            ),
            # checkpoint
            # VAE
            # clip
            # clip vision
            # lora
            ModelInst(t, ModelType.Lora, hf, "fbbcool/wan21", "", ""),
            # ModelInst(t, ModelType.Lora, hf, "fbbcool/1gts_wan", "1dreamplay.safetensors", ""),
            # custom nodes
            # ModelInst(t, ModelType.CustomNode, git, "", "", ""),
            ModelInst(
                t, ModelType.CustomNode, hf, "camenduru/stmfnet", "stmfnet.pth", ""
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/Zehong-Ma",
                "ComfyUI-MagCache",
                "",
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/Kosinkadink",
                "ComfyUI-VideoHelperSuite",
                "",
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/kijai",
                "ComfyUI-WanVideoWrapper",
                "",
            ),
        ]

        #
        # wan22
        #
        t = TargetType.Comfy
        models_wan22: list[ModelInst] = [
            # MVP first
            # checkpoint
            # ModelInst(t, ModelType.Unet, hf, "", "", ""),
            ModelInst(
                t,
                ModelType.Unet,
                hf,
                "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
                "split_files/diffusion_models/wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors",
                "t2v",
            ),
            ModelInst(
                t,
                ModelType.Unet,
                hf,
                "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
                "split_files/diffusion_models/wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors",
                "t2v",
            ),
            # https://huggingface.co/FX-FeiHou/wan2.2-Remix/resolve/main/NSFW/Wan2.2_Remix_NSFW_t2v_14b_high_lighting_v2.0.safetensors
            ModelInst(
                t,
                ModelType.Unet,
                hf,
                "FX-FeiHou/wan2.2-Remix",
                "NSFW/Wan2.2_Remix_NSFW_t2v_14b_high_lighting_v2.0.safetensors",
                "t2v",
            ),
            ModelInst(
                t,
                ModelType.Unet,
                hf,
                "FX-FeiHou/wan2.2-Remix",
                "NSFW/Wan2.2_Remix_NSFW_t2v_14b_low_lighting_v2.0.safetensors",
                "t2v",
            ),
            # https://huggingface.co/FX-FeiHou/wan2.2-Remix/resolve/main/NSFW/Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors
            ModelInst(
                t,
                ModelType.Unet,
                hf,
                "FX-FeiHou/wan2.2-Remix",
                "NSFW/Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors",
                "i2v",
            ),
            ModelInst(
                t,
                ModelType.Unet,
                hf,
                "FX-FeiHou/wan2.2-Remix",
                "NSFW/Wan2.2_Remix_NSFW_i2v_14b_low_lighting_v2.0.safetensors",
                "i2v",
            ),
            # https://huggingface.co/NSFW-API/NSFW-Wan-UMT5-XXL/resolve/main/nsfw_wan_umt5-xxl_fp8_scaled.safetensors?download=true
            ModelInst(
                t,
                ModelType.Clip,
                hf,
                "NSFW-API/NSFW-Wan-UMT5-XXL",
                "nsfw_wan_umt5-xxl_fp8_scaled.safetensors",
                "",
            ),
            # lora
            # ModelInst(t, ModelType.Lora, hf, "", "", ""),
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
                "split_files/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors",
                "t2v",
            ),
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
                "split_files/loras/wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors",
                "t2v",
            ),
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
                "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
                "i2v",
            ),
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
                "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors",
                "i2v",
            ),
            ModelInst(t, ModelType.Lora, hf, "fbbcool/wan22", "", ""),
            ModelInst(
                t, ModelType.CustomNode, hf, "camenduru/stmfnet", "stmfnet.pth", ""
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/Zehong-Ma",
                "ComfyUI-MagCache",
                "",
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/Kosinkadink",
                "ComfyUI-VideoHelperSuite",
                "",
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/stduhpf",
                "ComfyUI-WanMoeKSampler",
                "",
            ),
            ModelInst(
                t,
                ModelType.CustomNode,
                git,
                "github.com/ClownsharkBatwing",
                "RES4LYF",
                "",
            ),
        ]

        #
        # flux refine
        #
        t = TargetType.Comfy
        models_flux_refine: list[ModelInst] = [
            # 1gts
            ModelInst(
                t, ModelType.Unet, hf, "fbbcool/1gts", "1gts_base.safetensors", ""
            ),
            # VAE
            ModelInst(
                t,
                ModelType.Vae,
                hf,
                "black-forest-labs/FLUX.1-dev",
                "ae.safetensors",
                "",
            ),
            # clip
            ModelInst(
                t,
                ModelType.Clip,
                hf,
                "comfyanonymous/flux_text_encoders",
                "clip_l.safetensors",
                "",
            ),
            ModelInst(
                t,
                ModelType.Clip,
                hf,
                "city96/t5-v1_1-xxl-encoder-gguf",
                "t5-v1_1-xxl-encoder-Q8_0.gguf",
                "",
            ),
            ModelInst(
                t,
                ModelType.Lora,
                hf,
                "fbbcool/1gts",
                "1gts_r5_afro-mid.safetensors",
                "",
            ),
            ModelInst(
                t, ModelType.Lora, hf, "fbbcool/1gts", "1gts_r5-low.safetensors", ""
            ),
            ModelInst(
                t, ModelType.Lora, hf, "fbbcool/1gts", "1gts_chloe.safetensors", ""
            ),
            ModelInst(
                t, ModelType.Lora, hf, "fbbcool/1gts", "1gts_cock.safetensors", ""
            ),
            ModelInst(
                t, ModelType.Lora, hf, "fbbcool/1gts", "1gts_breast.safetensors", ""
            ),
            ModelInst(
                t, ModelType.Lora, hf, "fbbcool/1gts", "1gts_chubby.safetensors", ""
            ),
            ModelInst(
                t, ModelType.Lora, hf, "fbbcool/1gts", "1gts_muscle.safetensors", ""
            ),
            ModelInst(
                t, ModelType.Lora, hf, "fbbcool/1gts", "1gts_nhj.safetensors", ""
            ),
            ModelInst(
                t, ModelType.Lora, hf, "fbbcool/1gts", "1gts_cumshot.safetensors", ""
            ),
            # flux fill
            ModelInst(
                t,
                ModelType.Unet,
                hf,
                "YarvixPA/FLUX.1-Fill-dev-gguf",
                "flux1-fill-dev-Q8_0.gguf",
                "",
            ),
        ]

        #
        # current
        #
        t = TargetType.Comfy
        models_current: list[ModelInst] = [
            # MVP first
            # checkpoint
            # ModelInst(t, ModelType.DiffusionModel, hf, "", "", ""),
            # VAE
            # ModelInst(t, ModelType.VAE, hf, "", "", ""),
            # clip
            # ModelInst(t, ModelType.TextEncoder, hf, "", "", ""),
            # lora
            # ModelInst(t, ModelType.Lora, hhf, "", "", ""),
            # upscale
            ModelInst(
                t,
                ModelType.Upscale,
                hf,
                "ai-forever/Real-ESRGAN",
                "RealESRGAN_x2.pth",
                "",
            ),
            ModelInst(
                t,
                ModelType.Upscale,
                hf,
                "ai-forever/Real-ESRGAN",
                "RealESRGAN_x4.pth",
                "",
            ),
        ]

        model_db = {
            DownloadGroup.FLUX_REFINE: models_flux_refine,
            DownloadGroup.CURRENT: models_current,
            DownloadGroup.WAN21: models_wan21,
            DownloadGroup.WAN22: models_wan22,
            DownloadGroup.QWEN: models_qwen,
            DownloadGroup.QWEN_EDIT: models_qwen_edit,
        }

        if not method_gen:
            method_gen = None

        downloads = models_common + model_db[group]
        for download in downloads:
            install = True
            if not download.method_gen:
                download.method_gen = None

            if download.method_gen is not None:
                if method_gen is not None:
                    if download.method_gen != method_gen:
                        install = False

        if install:
            download.install


class PostInstHook:
    def __init__(self) -> None:
        URL_HOOK: Final = "/tmp"
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
                os.chmod(self.path, 0o755)  # Make the script executable
        print(f"Post-install hook script written to\n{self.path}")


POST_HOOK: Final = PostInstHook()


def _hook_wan21():
    # print the name of this method
    # print(sys._getframe(0).f_code.co_name)
    POST_HOOK.add_line("# hook by current")
    dir_fi_model = (
        "/workspace/ComfyUI/custom_nodes/comfyui-frame-interpolation/ckpts/stmfnet"
    )
    POST_HOOK.add_line(f"mkdir -p {dir_fi_model}")
    POST_HOOK.add_line(f"cp /workspace/ComfyUI/custom_nodes/stmfnet.pth {dir_fi_model}")
    print("\t!!!_hook_current!!!")


map_download_group = {
    "sd15": {
        "group": DownloadGroup.SD15,
    },
    "sdxl": {
        "group": DownloadGroup.SDXL,
    },
    "sdall": {"group": DownloadGroup.SDALL},
    "flux": {"group": DownloadGroup.FLUX},
    "flux_refine": {"group": DownloadGroup.FLUX_REFINE},
    "hidream": {"group": DownloadGroup.HIDREAM},
    "fluxgym": {"group": DownloadGroup.FLUXGYM},
    "kohyass_flux": {"group": DownloadGroup.KOHYASS_FLUX},
    "kohyass_sdxl": {"group": DownloadGroup.KOHYASS_SDXL},
    "qwen": {"group": DownloadGroup.QWEN},
    "qwen_edit": {"group": DownloadGroup.QWEN_EDIT},
    "wan21": {"hook": _hook_wan21, "group": DownloadGroup.WAN21},
    "wan22": {"method_gen": "t2v", "group": DownloadGroup.WAN22},
    "wan22_i2v": {"method_gen": "i2v", "group": DownloadGroup.WAN22},
    "current": {"group": DownloadGroup.CURRENT},
}

if __name__ == "__main__":
    str_group = sys.argv[1]
    data_group = map_download_group.get(str_group, None)

    if data_group is not None:
        group = data_group.get("group", None)
        method_gen = data_group.get("method_gen", None)
        hook = data_group.get("hook", None)

    if group is not None:
        print(f"using download group {str_group}.")
        ModelInstComfyUi(group=group, method_gen=method_gen)

    if hook is not None:
        print("creating post hook.")
        hook()
        POST_HOOK.save()
