import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Final
from urllib.parse import parse_qs, unquote, urlparse
import threading

from huggingface_hub import hf_hub_download, snapshot_download
import urllib

from more_itertools import chunked_even

from aidb.hfdataset import HFDatasetImg

class Trainer:
    #ROOT: Final = Path("/workspace/train")
    ROOT: Final = Path("/Volumes/data/Project/AI/REPOS/aitools/build/train")
    FILENAME_CONFIG: Final = "config_trainer.json"
    FILE_CONFIG: Final = ROOT / FILENAME_CONFIG
    FOLDER_DATASET: Final = ROOT / "dataset"
    FOLDER_OUTPUT: Final = ROOT / "output"
    FOLDER_MODELS: Final = ROOT / "../models"
    FILE_SAMPLE_PROMPTS: Final = ROOT / "sample_prompts.txt"
    FILE_CONFIG_DIFFPIPE: Final = ROOT / "diffpipe.toml"
    FILE_CONFIG_DATASET: Final = ROOT / "dataset.toml"
    FILE_TRAIN_SCRIPT: Final = ROOT / "train.sh"
    MODEL_REPO_ID_FLUX: Final = "Kijai/flux-fp8"
    MODEL_FILE_FLUX: Final = "flux1-dev-fp8.safetensors"
    MODEL_REPO_ID_WAN: Final = "NSFW-API/NSFW_Wan_14b"
    MODEL_FILE_WAN: Final = "nsfw_wan_14b_e15_fp8.safetensors"
    CHUNK_SIZE: Final = 1638400
    USER_AGENT: Final = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'

    def __init__(self, repo_id: str, load_models: bool = True, cache_full_dataset: bool = False, mutlitread: bool = False) -> None:
        self._repo_id = repo_id

        self._config: dict = {}
        self._ids_img: list[str] = []
        self._hfd: HFDatasetImg = None
        self._trigger = []
        self._name = ""
        self._ids_used = []
        self._batch_size = 1

        #self._hfdl_ckpt: tuple[str,str] | None = ("black-forest-labs/FLUX.1-dev", "flux1-dev.safetensors")
        self._hfdl_ckpt_flux: tuple[str,str] | None = (self.MODEL_REPO_ID_FLUX, self.MODEL_FILE_FLUX)
        self._hfdl_vae_flux: tuple[str,str] = ("black-forest-labs/FLUX.1-dev", "ae.safetensors")
        self._hfdl_clipl_flux: tuple[str,str] = ("comfyanonymous/flux_text_encoders", "clip_l.safetensors")
        self._hfdl_llm_flux: tuple[str,str] = ("comfyanonymous/flux_text_encoders", "t5xxl_fp16.safetensors")
        #self._hfdl_t5xxl: tuple[str,str] = ("comfyanonymous/flux_text_encoders", "t5xxl_fp8_e4m3fn_scaled.safetensors")
        
        self._hfdl_ckpt_wan: tuple[str,str] | None = (self.MODEL_REPO_ID_WAN, self.MODEL_FILE_WAN)
        self._hfdl_llm_wan: tuple[str,str] = ("Kijai/WanVideo_comfy", "umt5-xxl-enc-fp8_e4m3fn.safetensors")
        
        self._file_ckpt: str = ""
        self._file_vae: str = ""
        self._file_transformer: str = ""
        self._file_llm: str = ""
        self._folder_ckpt_base: str = "" # base ckpt full checkout w/o models, only config (e.eg. for WAN)
        
        self._caidl_ckpt: tuple[str,str] | None = None
        
        self.ROOT.mkdir(exist_ok=True)
        # download train config
        hf_hub_download(repo_id=self._repo_id, filename=self.FILENAME_CONFIG, repo_type="dataset", force_download=True, local_dir=self.ROOT)

        # read config file with pathlib and store the dict
        try:
            with self.FILE_CONFIG.open('r', encoding='utf-8') as f:
                self._config = json.load(f)
        except Exception as e:
            print(f"{e}\nError: config json not loadable!")
            return
        
        # set members
        self._ids_img = self._config.get("imgs", [])
        self._trigger = self._config.get("trigger", "")
        self._name = self._config.get("name", "")
        self._batch_size = self._config.get("batch_size", 1)

        # if model key doesnt exist do nothing
        if "model" in self._config:
            model = self._config["model"]
            self._hfdl_ckpt_flux = None
            self._caidl_ckpt = None
            
            # if cai model is given, it is used first
            if "cai" in model:
                url_cai = model["cai"].get("url", "")
                if url_cai:
                    self._caidl_ckpt = (url_cai, "")
            
            if self._caidl_ckpt is None:
                if "hf" in model:
                    file_ = model["hf"].get("file", "")
                    repo_id_ = model["hf"].get("repo_id", "")
                    if file_ and repo_id_:
                        self._hfdl_ckpt_flux = (model["hf"]["repo_id"], model["hf"]["file"])
                if self._hfdl_ckpt_flux is None:
                    raise ValueError("model section is given in config but not set!")

        # load HF dataset
        self._hfd = HFDatasetImg(self._repo_id, force_meta_dl=True)
        if not self._ids_img:
            self._ids_img = self._hfd.ids
        
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
            #self._download_models_flux()
            self._download_models_wan()

        self._make_dataset(cache_full_dataset=cache_full_dataset, multithread=mutlitread)
        #self._make_file_sample_prompts()
        self._make_file_dataset_config()
        self._make_file_diffpipe_config()
        self._make_file_train_script()




    def _download_models_flux(self, force: bool = False) -> None:
        if self._hfdl_ckpt_flux:
            self._file_ckpt = hf_hub_download(repo_id=self._hfdl_ckpt_flux[0], filename=self._hfdl_ckpt_flux[1], cache_dir=self.FOLDER_MODELS)
        elif self._caidl_ckpt:
            self._file_ckpt = self._download_civitai(self._caidl_ckpt[0])
        self._file_transformer = hf_hub_download(repo_id=self._hfdl_clipl_flux[0], filename=self._hfdl_clipl_flux[1], cache_dir=self.FOLDER_MODELS)
        self._file_llm = hf_hub_download(repo_id=self._hfdl_llm_flux[0], filename=self._hfdl_llm_flux[1], cache_dir=self.FOLDER_MODELS)
        self._file_vae = hf_hub_download(repo_id=self._hfdl_vae_flux[0], filename=self._hfdl_vae_flux[1], cache_dir=self.FOLDER_MODELS)
    
    def _download_models_wan(self, force: bool = False) -> None:
        if self._hfdl_ckpt_wan:
            self._file_ckpt = hf_hub_download(repo_id=self._hfdl_ckpt_wan[0], filename=self._hfdl_ckpt_wan[1], cache_dir=self.FOLDER_MODELS)
        elif self._caidl_ckpt:
            self._file_ckpt = self._download_civitai(self._caidl_ckpt[0])
        self._file_transformer = None
        self._file_llm = hf_hub_download(repo_id=self._hfdl_llm_wan[0], filename=self._hfdl_llm_wan[1], cache_dir=self.FOLDER_MODELS)
        self._file_vae = None
        self._folder_ckpt_base = snapshot_download(repo_id="Wan-AI/Wan2.1-T2V-14B", ignore_patterns=["diffusion_pytorch_model*", "models_t5*"])

    
    def _make_dataset(self, cache_full_dataset: bool = False, multithread: bool = False) -> None:
        lost = 0
        
        if cache_full_dataset:
            self._hfd.cache()
        
        if not self._ids_img:
            raise ValueError("dataset: empty img list!")

        # non multi-threaded
        if not multithread:
            self._process_imgs(self._ids_img)
        else:
            # multi-threaded
            n = 8
            m = len(self._ids_img)
            ids = []
            for batch in chunked_even(self._ids_img,(m//n)+1):
                ids.append(batch)
            if (len(ids) != n):
                raise ValueError("dataset multithreading failed!")

            threads = []
            for i in range(n):
                thread = threading.Thread(target=self._process_imgs, args=[ids[i],])
                print(f" dataset thread[{i}]: {len(ids[i])} imgs")
                threads.append(thread)
                thread.start()
            for i in range(n):
                threads[i].join()
                print(f" dataset thread[{i}]: joined.")
    
    def _process_imgs(self, ids: list[str]) -> None:
        if not ids:
            return

        lost = 0
        success = 0
        for id in ids:
            if not id:
                continue
            idx = self._hfd.id2idx(id)
            if not idx:
                continue
            
            # caption or prompt fetch
            #caption = self._hfd.captions[idx]
            caption = self._hfd.prompts[idx]
            if not caption:
                caption = self._trigger
                lost += 1
                print(f"{id}: caption missed!")
                continue

            # TODO more generic, and take care that the dataset isnt polluted with trigger words
            caption = caption.replace("1gts,", "")
            caption = caption.replace("1woman,", "")

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
            success += 1
        print(f"dataset thread finished: {success} successes, {lost} losses")


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
            

    def _make_file_dataset_config(self) -> None:
        str_file = f"""
# Resolutions to train on, given as the side length of a square image. You can have multiple sizes here.
# !!!WARNING!!!: this might work differently to how you think it does. Images are first grouped to aspect ratio
# buckets, then each image is resized to ALL of the areas specified by the resolutions list. This is a way to do
# multi-resolution training, i.e. training on multiple total pixel areas at once. Your dataset is effectively duplicated
# as many times as the length of this list.
# If you just want to use predetermined (width, height, frames) size buckets, see the example cosmos_dataset.toml
# file for how you can do that.
#resolutions = [1024]
resolutions = [768]

# You can give resolutions as (width, height) pairs also. This doesn't do anything different, it's just
# another way of specifying the area(s) (i.e. total number of pixels) you want to train on.
# resolutions = [[720,1280]]

# Enable aspect ratio bucketing. For the different AR buckets, the final size will be such that
# the areas match the resolutions you configured above.
enable_ar_bucket = true

# The aspect ratio and frame bucket settings may be specified for each [[directory]] entry as well.
# Directory-level settings will override top-level settings.

# Min and max aspect ratios, given as width/height ratio.
min_ar = 0.5
max_ar = 2.0
# Total number of aspect ratio buckets, evenly spaced (in log space) between min_ar and max_ar.
num_ar_buckets = 16

# Can manually specify ar_buckets instead of using the range-style config above.
# Each entry can be width/height ratio, or (width, height) pair. But you can't mix them, because of TOML.
# ar_buckets = [[512, 512], [448, 576]]
# ar_buckets = [1.0, 1.5]

# For video training, you need to configure frame buckets (similar to aspect ratio buckets). There will always
# be a frame bucket of 1 for images. Videos will be assigned to the longest frame bucket possible, such that the video
# is still greater than or equal to the frame bucket length.
# But videos are never assigned to the image frame bucket (1); if the video is very short it would just be dropped.
frame_buckets = [1]
# If you have >24GB VRAM, or multiple GPUs and use pipeline parallelism, or lower the spatial resolution, you could maybe train with longer frame buckets
# frame_buckets = [1, 33, 65, 97]

# Shuffle tags before caching, 0 to keep original caption (unless shuffle_tags is set to true). Increases caching time a tiny bit for higher values.
# cache_shuffle_num = 10
# Delimiter for tags, only used if cache_shuffle_num is not 0. Defaults to ", ".
# "tag1, tag2, tag3" has ", " as delimiter and will possibly be shuffled like "tag3, tag1, tag2". "tag1;tag2;tag3" has ";" as delimiter and will possibly be shuffled like "tag2;tag1;tag3".
# cache_shuffle_delimiter = ", "

[[directory]]
# Path to directory of images/videos, and corresponding caption files. The caption files should match the media file name, but with a .txt extension.
# A missing caption file will log a warning, but then just train using an empty caption.
path = '{self.FOLDER_DATASET}'

# You can do masked training, where the mask indicates which parts of the image to train on. The masking is done in the loss function. The mask directory should have mask
# images with the same names (ignoring the extension) as the training images. E.g. training image 1.jpg could have mask image 1.jpg, 1.png, etc. If a training image doesn't
# have a corresponding mask, a warning is printed but training proceeds with no mask for that image. In the mask, white means train on this, black means mask it out. Values
# in between black and white become a weight between 0 and 1, i.e. you can use a suitable value of grey for mask weight of 0.5. In actuality, only the R channel is extracted
# and converted to the mask weight.
# The mask_path can point to any directory containing mask images.
#mask_path = '/home/anon/data/images/grayscale/masks'

# How many repeats for 1 epoch. The dataset will act like it is duplicated this many times.
# The semantics of this are the same as sd-scripts: num_repeats=1 means one epoch is a single pass over all examples (no duplication).
num_repeats = 1

# Example of overriding some settings, and using ar_buckets to directly specify ARs.
# ar_buckets = [[448, 576]]
# resolutions = [[448, 576]]
# frame_buckets = [1]
"""
        with self.FILE_CONFIG_DATASET.open("w", encoding="utf-8") as f:
            f.write(str_file)

    def _make_file_diffpipe_config(self) -> None:
        str_file = f"""
# Output path for training runs. Each training run makes a new directory in here.
output_dir = '{self.FOLDER_OUTPUT}'
dataset = '{self.FILE_CONFIG_DATASET}'

# training settings

# I usually set this to a really high value because I don't know how long I want to train.
epochs = 40
# Batch size of a single forward/backward pass for one GPU.
micro_batch_size_per_gpu = {self._batch_size}
# For mixed video / image training, you can have a different batch size for images.
#image_micro_batch_size_per_gpu = 4
# Pipeline parallelism degree. A single instance of the model is divided across this many GPUs.
pipeline_stages = 1
# Number of micro-batches sent through the pipeline for each training step.
# If pipeline_stages > 1, a higher GAS means better GPU utilization due to smaller pipeline bubbles (where GPUs aren't overlapping computation).
gradient_accumulation_steps = 1
# Grad norm clipping.
gradient_clipping = 1.0
# Learning rate warmup.
warmup_steps = 100
# Force the learning rate to be this value, regardless of what the optimizer or anything else says.
# Can be used to change learning rate even when resuming from checkpoint.
#force_constant_lr = 1e-5

# Block swapping is supported for Wan, HunyuanVideo, Flux, and Chroma. This value controls the number
# of blocks kept offloaded to RAM. Increasing it lowers VRAM use, but has a performance penalty. The
# exactly performance penalty depends on the model and the type of training you are doing (e.g. images vs video).
# Block swapping only works for LoRA training, and requires pipeline_stages=1.
#blocks_to_swap = 20

# eval settings

eval_every_n_epochs = 1
eval_before_first_step = true
# Might want to set these lower for eval so that less images get dropped (eval dataset size is usually much smaller than training set).
# Each size bucket of images/videos is rounded down to the nearest multiple of the global batch size, so higher global batch size means
# more dropped images. Usually doesn't matter for training but the eval set is much smaller so it can matter.
eval_micro_batch_size_per_gpu = 1
# Batch size for images when doing mixed image / video training. Will be micro_batch_size_per_gpu if not set.
#image_eval_micro_batch_size_per_gpu = 4
eval_gradient_accumulation_steps = 1
# If using block swap, you can disable it for eval. Eval uses less memory, so depending on block swapping amount you can maybe get away with
# doing this, and then eval is much faster.
#disable_block_swap_for_eval = true

# misc settings

# Probably want to set this a bit higher if you have a smaller dataset so you don't end up with a million saved models.
save_every_n_epochs = 1
# Can checkpoint the training state every n number of epochs or minutes. Set only one of these. You can resume from checkpoints using the --resume_from_checkpoint flag.
#checkpoint_every_n_epochs = 1
#checkpoint_every_n_minutes = 120
# Always set to true unless you have a huge amount of VRAM.
# This can also be 'unsloth' to reduce VRAM even more, with a slight performance hit.
activation_checkpointing = true
# Use reentrant activation checkpointing method (set this in addition to `activation_checkpointing`). Might be required for some models
# when using pipeline parallelism (pipeline_stages>1). Otherwise recommended to not use it.
#reentrant_activation_checkpointing = true

# Controls how Deepspeed decides how to divide layers across GPUs. Probably don't change this.
partition_method = 'parameters'
# Alternatively you can use 'manual' in combination with partition_split, which specifies the split points for dividing
# layers between GPUs. For example, with two GPUs, partition_split=[10] puts layers 0-9 on GPU 0, and the rest on GPU 1.
# With three GPUs, partition_split=[10, 20] puts layers 0-9 on GPU 0, layers 10-19 on GPU 1, and the rest on GPU 2.
# Length of partition_split must be pipeline_stages-1.
#partition_split = [N]

# dtype for saving the LoRA or model, if different from training dtype
save_dtype = 'bfloat16'
# Batch size for caching latents and text embeddings. Increasing can lead to higher GPU utilization during caching phase but uses more memory.
caching_batch_size = 1

# Number of parallel processes to use in map() calls when caching the dataset. Defaults to min(8, num_cpu_cores) if unset.
# If you have a lot of cores and multiple GPUs, raising this can increase throughput of caching, but it may use more memory,
# especially for video data.
#map_num_proc = 32

# Use torch.compile on the model. Can speed up training throughput by a decent amount. Not tested on all models.
#compile = true

# How often deepspeed logs to console.
steps_per_print = 1
# How to extract video clips for training from a single input video file.
# The video file is first assigned to one of the configured frame buckets, but then we must extract one or more clips of exactly the right
# number of frames for that bucket.
# single_beginning: one clip starting at the beginning of the video
# single_middle: one clip from the middle of the video (cutting off the start and end equally)
# multiple_overlapping: extract the minimum number of clips to cover the full range of the video. They might overlap some.
# default is single_beginning
video_clip_mode = 'single_beginning'

# This is how you configure WAN video. Other models will be different. See docs/supported_models.md for
# details on the configuration and options for each model.
[model]
type = 'wan'
# this is the config checkout for the checkpoint but w/o the specific model
ckpt_path = '{self._folder_ckpt_base}'
# this is the used checkpoint model (compatible with the base checkpoint config!)
transformer_path = '{self._file_ckpt}'
# this is the used text encoder model (compatible with the base checkpoint config!)
llm_path = '{self._file_llm}'
dtype = 'bfloat16'
transformer_dtype = 'float8'
timestep_sample_method = 'logit_normal'

# For models that support full fine tuning, simply delete or comment out the [adapter] table to FFT.
[adapter]
type = 'lora'
rank = {self._config["netdim"]}
# Dtype for the LoRA weights you are training.
dtype = 'bfloat16'
# You can initialize the lora weights from a previously trained lora.
#init_from_existing = '/data/diffusion_pipe_training_runs/something/epoch50'
# Experimental. Can fuse LoRAs into the base weights before training. Right now only for Flux.

[optimizer]
# AdamW from the optimi library is a good default since it automatically uses Kahan summation when training bfloat16 weights.
# Look at train.py for other options. You could also easily edit the file and add your own.
type = 'adamw_optimi'
lr = 2e-5
betas = [0.9, 0.99]
weight_decay = 0.01
eps = 1e-8

# Can use this optimizer for a bit less memory usage.
# [optimizer]
# type = 'AdamW8bitKahan'
# lr = 2e-5
# betas = [0.9, 0.99]
# weight_decay = 0.01
# stabilize = false

# Automagic optimizer from AI-Toolkit.
# In my experience, this gives slightly worse results than AdamW with a properly tuned LR, but you can try it.

# [optimizer]
# type = 'automagic'
# weight_decay = 0.01

# Any optimizer not explicitly supported will be dynamically loaded from the pytorch-optimizer library.
# [optimizer]
# type = 'Prodigy'
# lr = 1
# betas = [0.9, 0.99]
# weight_decay = 0.01
"""
        with self.FILE_CONFIG_DIFFPIPE.open("w", encoding="utf-8") as f:
            f.write(str_file)

    def _make_file_train_script(self) -> None:
        str_file = f"""
NCCL_P2P_DISABLE="1" NCCL_IB_DISABLE="1" deepspeed --num_gpus=1 train.py --deepspeed --config {self.FILE_CONFIG_DIFFPIPE}
""" 
        # save train string to train script and chmod 777 it.
        with self.FILE_TRAIN_SCRIPT.open("w", encoding="utf-8") as f:
            f.write(str_file)
        self.FILE_TRAIN_SCRIPT.chmod(0o777)
    

    @classmethod
    def make_config(cls, imgs: list[str]) -> None:
        """ takes a list of image ids and makes a default config file"""
        config: dict = {}
        
        # 1gts
        config["repo_id"] = "fbbcool/1gts_wan01"
        config["trigger"] = "1gts"
        config["name"] = "1gts_wan01"
        config["netdim"] = 48
        config["batch_size"] = 2
        config["prompts"] = []
        config["model"] = {"hf": {"repo_id": cls.MODEL_REPO_ID_WAN, "file": cls.MODEL_FILE_WAN}, "cai": {"url": ""}}
        config["imgs"] = imgs

        # 1woman
        #config["repo_id"] = "fbbcool/1woman_lara02"
        #config["trigger"] = "1woman"
        #config["name"] = "lara02"
        #config["netdim"] = 32
        #config["batch_size"] = 1
        #config["prompts"] = []
        #config["model"] = {"hf": {"repo_id": cls.MODEL_REPO_ID_WAN, "file": cls.MODEL_FILE_WAN}, "cai": {"url": ""}}
        #config["imgs"] = imgs

        configfile = Path(f"./{Trainer.FILENAME_CONFIG}")

        # write config file with pathlib
        try:
            with configfile.open('w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            print(f"Config successfully saved to {configfile}")
        except Exception as e:
            print(f"Error saving config to JSON: {e}")
    
    def _download_civitai(self, url: str) -> Path:
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

        output_file = self.FOLDER_MODELS / filename

        if output_file.exists():
            print(f"\t already downloaded: {output_file.name}")
            return output_file

        with output_file.open('wb') as f:
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

        return output_file
