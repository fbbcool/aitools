import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Final
from urllib.parse import parse_qs, unquote, urlparse

from huggingface_hub import hf_hub_download
import urllib

from aidb.hfdataset import HFDatasetImg

class TrainerKohya:
    ROOT: Final = Path("/workspace/train")
    #ROOT: Final = Path("/Volumes/data/Project/AI/REPOS/aitools/build/train")
    FILENAME_CONFIG: Final = "config_trainer.json"
    FILE_CONFIG: Final = ROOT / FILENAME_CONFIG
    FOLDER_DATASET: Final = ROOT / "dataset"
    FOLDER_OUTPUT: Final = ROOT / "output"
    FOLDER_MODELS: Final = ROOT / "models"
    FILE_SAMPLE_PROMPTS: Final = ROOT / "sample_prompts.txt"
    FILE_CONFIG_DATASET: Final = ROOT / "dataset.toml"
    FILE_TRAIN_SCRIPT: Final = ROOT / "train.sh"
    CHUNK_SIZE: Final = 1638400
    USER_AGENT: Final = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'

    def __init__(self, load_models: bool = True) -> None:
        self._config: dict = {}
        self._ids_img: list[str] = []
        self._hfd: HFDatasetImg = None
        self._trigger = []
        self._name = ""
        self._ids_used = []
        self._batch_size = 1

        self._hfdl_ckpt: tuple[str,str] | None = ("black-forest-labs/FLUX.1-dev", "flux1-dev.safetensors")
        self._hfdl_vae: tuple[str,str] = ("black-forest-labs/FLUX.1-dev", "ae.safetensors")
        self._hfdl_clipl: tuple[str,str] = ("comfyanonymous/flux_text_encoders", "clip_l.safetensors")
        self._hfdl_t5xxl: tuple[str,str] = ("comfyanonymous/flux_text_encoders", "t5xxl_fp16.safetensors")
        self._file_ckpt: str = ""
        self._file_vae: str = ""
        self._file_clipl: str = ""
        self._file_t5xxl: str = ""
        
        self._caidl_ckpt: tuple[str,str] | None = None
        
        # read config file with pathlib and store the dict
        try:
            with self.FILE_CONFIG.open('r', encoding='utf-8') as f:
                self._config = json.load(f)
        except Exception as e:
            print(f"{e}\nError: config json not loadable!")
            return
        
        # set members
        self._ids_img = self._config["imgs"]
        self._trigger = self._config["trigger"]
        self._name = self._config["name"]
        self._batch_size = self._config["batch_size"]

        # if model key doesnt exist do nothing
        if "model" in self._config:
            model = self._config["model"]
            self._hfdl_ckpt = None
            self._caidl_ckpt = None
            if "hf" in model:
                self._hfdl_ckpt = (model["hf"]["repo_id"], model["hf"]["file"])
            elif "cai" in model:
                self._caidl_ckpt = (model["cai"]["url"], "")



        # load HF dataset
        repo_id = self._config["repo_id"]
        self._hfd = HFDatasetImg(repo_id)
        
        # make datatset folder
        if self.FOLDER_DATASET.exists():
            # remove it
            shutil.rmtree(self.FOLDER_DATASET)
        self.FOLDER_DATASET.mkdir()
        # make output folder
        if self.FOLDER_OUTPUT.exists():
            # remove it
            shutil.rmtree(self.FOLDER_OUTPUT)
        self.FOLDER_OUTPUT.mkdir()

        self.FOLDER_MODELS.mkdir(exist_ok=True)

        if load_models:
            self._download_models()

        self._make_dataset()
        self._make_file_sample_prompts()
        self._make_file_train_config()
        self._make_file_train_script()




    def _download_models(self, force: bool = False) -> None:
        if self._hfdl_ckpt:
            self._file_ckpt = hf_hub_download(repo_id=self._hfdl_ckpt[0], filename=self._hfdl_ckpt[1], cache_dir=self.FOLDER_MODELS)
        elif self._caidl_ckpt:
            self._file_ckpt = self._download_civitai(self._caidl_ckpt[0], self.FOLDER_MODELS)
        self._file_clipl = hf_hub_download(repo_id=self._hfdl_clipl[0], filename=self._hfdl_clipl[1], cache_dir=self.FOLDER_MODELS)
        self._file_t5xxl = hf_hub_download(repo_id=self._hfdl_t5xxl[0], filename=self._hfdl_t5xxl[1], cache_dir=self.FOLDER_MODELS)
        self._file_vae = hf_hub_download(repo_id=self._hfdl_vae[0], filename=self._hfdl_vae[1], cache_dir=self.FOLDER_MODELS)

    
    def _make_dataset(self) -> None:
        lost = 0
        for id in self._ids_img:
            idx = self._hfd.id2idx(id)
            if not idx:
                continue
            
            # caption fetch
            caption = self._hfd.captions[idx]
            if not caption:
                caption = self._trigger
                lost += 1
                print(f"{id}: caption missed!")
                continue
            caption = f"{self._trigger}," + caption
            
            # img file
            try:
                img_file_dl = self._hfd.img_download(idx)
            except Exception as e:
                lost += 1
                print(f"{e}\n{id} not downloadable!")
                continue
            
            # copy file to dataset folder
            img_file = self.FOLDER_DATASET / img_file_dl.name
            shutil.copy(str(img_file_dl), str(img_file))

            # write caption to file
            cap_file = img_file.with_suffix(".txt")
            with cap_file.open("w", encoding="utf-8") as f:
                f.write(caption)
            
            # ok
            print(f"{id}: successfully added.")
            self._ids_used.append(id)
        print(f"dataset created with {len(self._ids_used)} items and {lost} lost items.")

    def _make_file_sample_prompts(self) -> None:
        str_prompt = []
        for prompt in self._config["prompts"]:
            # every prompt items is put in its own line
            str_prompt.append(prompt)
            str_prompt.append(f"{self._trigger}," + prompt)
        
        # delete file if exists
        if self.FILE_SAMPLE_PROMPTS.exists():
            self.FILE_SAMPLE_PROMPTS.unlink()
        
        with self.FILE_SAMPLE_PROMPTS.open("w", encoding="utf-8") as f:
            f.write("\n\n".join(str_prompt))
            

    def _make_file_train_config(self) -> None:
        str_file = f"""
[general]
shuffle_caption = false
caption_extension = '.txt'
keep_tokens = 1

[[datasets]]
resolution = 1024
batch_size = {self._batch_size}
keep_tokens = 1

  [[datasets.subsets]]
  image_dir = '{self.FOLDER_DATASET}'
  class_tokens = '{self._trigger}'
  num_repeats = 1
"""
        with self.FILE_CONFIG_DATASET.open("w", encoding="utf-8") as f:
            f.write(str_file)

    def _make_file_train_script(self) -> None:
        str_file = f"""
accelerate launch \\
    --mixed_precision bf16 \\
    --num_cpu_threads_per_process 1 \\
    sd-scripts/flux_train_network.py \\
    --pretrained_model_name_or_path "{self._file_ckpt}" \\
    --clip_l "{self._file_clipl}" \\
    --t5xxl "{self._file_t5xxl}" \\
    --ae "{self._file_vae}" \\
    --cache_latents_to_disk \\
    --save_model_as safetensors \\
    --sdpa --persistent_data_loader_workers \\
    --max_data_loader_n_workers 2 \\
    --seed 42 \\
    --gradient_checkpointing \\
    --mixed_precision bf16 \\
    --save_precision bf16 \\
    --network_module networks.lora_flux \\
    --network_dim {self._config["netdim"]} \\
    --network_alpha {self._config["netdim"]} \\
    --optimizer_type adamw8bit \\
    --sample_prompts="{self.FILE_SAMPLE_PROMPTS}" \\
    --sample_every_n_steps="100" \\
    --learning_rate 8e-4 \\
    --cache_text_encoder_outputs \\
    --cache_text_encoder_outputs_to_disk \\
    --fp8_base \\
    --highvram \\
    --max_train_epochs 16 \\
    --save_every_n_epochs 1 \\
    --dataset_config "{self.FILE_CONFIG_DATASET}" \\
    --output_dir "{self.FOLDER_OUTPUT}" \\
    --output_name {self._name} \\
    --timestep_sampling shift \\
    --discrete_flow_shift 3.1582 \\
    --model_prediction_type raw \\
    --guidance_scale 1 \\
    --loss_type l2
""" 
        # save train string to train script and chmod 777 it.
        with self.FILE_TRAIN_SCRIPT.open("w", encoding="utf-8") as f:
            f.write(str_file)
        self.FILE_TRAIN_SCRIPT.chmod(0o777)
    

    @staticmethod
    def make_config(imgs: list[str]) -> None:
        """ takes a list of image ids and makes a default config file"""
        config: dict = {}
        config["repo_id"] = "fbbcool/gts01_r35"
        config["trigger"] = "1gts"
        config["name"] = "gts"
        config["netdim"] = 32
        config["batch_size"] = 1
        config["prompts"] = ["a muscular giantess female bride is towering in a bright wedding empty cathedral. she is wearing black sandal high heels. at her feet is her small groom."]
        config["imgs"] = imgs

        configfile = Path(f"./{TrainerKohya.FILENAME_CONFIG}")

        # write config file with pathlib
        try:
            with configfile.open('w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            print(f"Config successfully saved to {configfile}")
        except Exception as e:
            print(f"Error saving config to JSON: {e}")
    
    def _download_civitai(self, url: str, ofolder: Path) -> Path:
        opath = str(ofolder)
        # get token from env TOKEN_CIVITAI
        #token = os.environ.get("CAI_TOKEN", "")
        token = os.environ.get("CAI_TOKEN", "2c1cdcc01625085bff329ba907d64948")
        

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

        return self.FOLDER_MODELS / filename
