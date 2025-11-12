import os
import json
from pathlib import Path
import shutil
from typing import Final, Literal
import threading

from huggingface_hub import hf_hub_download, snapshot_download

from more_itertools import chunked_even

from aidb.hfdataset import HFDatasetImg


class Trainer:
    WORKSPACE: Final = Path(os.environ.get("ENV_WORKSPACE", "/workspace"))
    AITOOLS: Final = Path(os.environ.get("AITOOLS_DIR", str(WORKSPACE / "___aitools")))
    ROOT: Final = WORKSPACE / "train"

    MODEL_TYPES: list[Literal["base", "ckpt", "text_encoder", "vae", "clipl"]] = [
        "base",
        "ckpt",
        "text_encoder",
        "vae",
        "clipl",
    ]

    FILENAME_CONFIG_BASE: Final = "config_base.json"
    FILENAME_CONFIG_TRAIN: Final = "config_trainer.json"
    FILE_CONFIG_BASE: Final = AITOOLS / "src/trainer" / FILENAME_CONFIG_BASE
    FILE_CONFIG_TRAIN: Final = ROOT / FILENAME_CONFIG_TRAIN
    FOLDER_DATASET: Final = ROOT / "dataset"
    FOLDER_OUTPUT: Final = ROOT / "output"
    FOLDER_MODELS: Final = ROOT / "../models"
    FILE_SAMPLE_PROMPTS: Final = ROOT / "sample_prompts.txt"
    FILE_CONFIG_DIFFPIPE: Final = ROOT / "diffpipe.toml"
    FILE_CONFIG_DATASET: Final = ROOT / "dataset.toml"
    FILE_TRAIN_SCRIPT: Final = ROOT / "train.sh"

    def __init__(
        self,
        repo_ids_hfd: str | list[str],
        type_model: str | None = None,
        load_models: bool = True,
        multithread: bool = False,
    ) -> None:
        if isinstance(repo_ids_hfd, str):
            repo_ids_hfd = [repo_ids_hfd]
        self._repo_ids_hfd: list[str] = repo_ids_hfd

        self._config_base: dict = {}
        self._config_train: dict = {}

        self._type_model = None
        self._trigger = ""
        self._name = ""
        self._netdim = 4
        self._batch_size = 1
        self._num_repeats = 1
        self._lr = 2e-5

        # make root folder
        self.ROOT.mkdir(exist_ok=True)

        #
        # set train config
        #
        hf_hub_download(
            repo_id=self._repo_ids_hfd[0],
            filename=self.FILENAME_CONFIG_TRAIN,
            repo_type="dataset",
            force_download=True,
            local_dir=self.ROOT,
        )
        # read train config file with pathlib and store the dict
        try:
            with self.FILE_CONFIG_TRAIN.open("r", encoding="utf-8") as f:
                self._config_train = json.load(f)
        except Exception as e:
            print(f"{e}\nError: config json not loadable!")
            return
        # set train config members
        if type_model is not None:
            self._type_model = type_model
        else:
            self._type_model = self._config_train.get("type", None)
        self._name = self._config_train.get("name", "")
        self._trigger = self._config_train.get("trigger", "")
        self._netdim = int(self._config_train.get("netdim", 4))
        self._batch_size = int(self._config_train.get("batch_size", 1))
        self._num_repeats = int(self._config_train.get("num_repeats", 1))
        self._lr = float(self._config_train.get("lr", 2e-5))

        #
        # set base config
        #
        try:
            with self.FILE_CONFIG_BASE.open("r", encoding="utf-8") as f:
                self._config_base = json.load(f)
        except Exception as e:
            print(f"{e}\nError: config json not loadable!")
            return
        _base_models_all: dict = self._config_base.get("models", {})
        self._models: dict[str, dict] | None = _base_models_all.get(
            self._type_model, None
        )
        self._model_links: dict[str, str] = {}

        #
        # folders
        #
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

        #
        # prepare training toolchain
        #
        if load_models:
            self._download_models()

        self._make_dataset(multithread=multithread)
        # self._make_file_sample_prompts()
        self._make_file_dataset_config()
        self._make_file_diffpipe_config()
        self._make_file_train_script()

    def _download_models(self) -> None:
        if self._models is None:
            print(f"Error: no models found for type {self._type_model}")
            return None
        else:
            print(f"downloading models for type {self._type_model}:")

        for _type in self.MODEL_TYPES:
            print(f"\ttrying model {_type} ...")
            if _type in self._models:
                print(f"\tdownloading model {_type} ...")
                _model = self._models.get(_type, {})
                _repo_id = _model.get("repo_id", None)
                _ignore_patterns = _model.get("ignore_patterns", None)
                _file = _model.get("file", None)
                _link = self._download_model(
                    _repo_id, file=_file, ignore_patterns=_ignore_patterns
                )
                self._model_links[_type] = _link
            else:
                self._model_links[_type] = ""
                print(f"\tno config found for {_type}")

    def _download_model(
        self,
        repo_id: str,
        file: str | None = None,
        ignore_patterns: list[str] | None = None,
    ) -> str | None:
        if file is not None:
            link = hf_hub_download(
                repo_id=repo_id, filename=file, cache_dir=self.FOLDER_MODELS
            )
        elif ignore_patterns is not None:
            link = snapshot_download(
                repo_id=repo_id,
                ignore_patterns=ignore_patterns,
                cache_dir=self.FOLDER_MODELS,
            )
        else:
            return None
        return link

    def _make_dataset(self, multithread: bool = False) -> None:
        for repo_id in self._repo_ids_hfd:
            hfd = HFDatasetImg(repo_id, force_meta_dl=True)
            hfd.cache()
            self._make_dataset_hfd(hfd, multithread=multithread)

    def _make_dataset_hfd(self, hfd: HFDatasetImg, multithread: bool = False) -> None:
        # non multi-threaded
        ids_img = hfd.ids
        if not multithread:
            self._process_imgs(ids_img, hfd)
        else:
            # multi-threaded
            n = 8
            m = len(ids_img)
            ids = []
            for batch in chunked_even(ids_img, (m // n) + 1):
                ids.append(batch)
            if len(ids) != n:
                raise ValueError("dataset multithreading failed!")

            threads = []
            for i in range(n):
                thread = threading.Thread(
                    target=self._process_imgs,
                    args=[
                        ids[i],
                        hfd,
                    ],
                )
                print(f" dataset thread[{i}]: {len(ids[i])} imgs")
                threads.append(thread)
                thread.start()
            for i in range(n):
                threads[i].join()
                print(f" dataset thread[{i}]: joined.")

    def _process_imgs(self, ids: list[str], hfd: HFDatasetImg) -> None:
        if not ids:
            return

        lost = 0
        success = 0
        for id in ids:
            if not id:
                continue
            idx = hfd.id2idx(id)
            if not idx:
                continue

            # caption or prompt fetch
            prompt = hfd.prompts[idx]
            caption = hfd.captions[idx]
            if not caption:
                caption = prompt
            if not prompt:
                prompt = caption

            if not caption:
                lost += 1
                print(f"caption missing for {id}!")
                continue

            # TODO more generic, and take care that the dataset isnt polluted with trigger words
            caption = caption.replace("1gts,", "")
            caption = caption.replace("1woman,", "")

            caption = f"{self._trigger}," + caption

            # img file
            try:
                img_file_dl = hfd.img_download(idx)
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
        for prompt in self._config_train["prompts"]:
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
resolutions = [1024]
#resolutions = [768]

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
num_repeats = {self._num_repeats}

# Example of overriding some settings, and using ar_buckets to directly specify ARs.
# ar_buckets = [[448, 576]]
# resolutions = [[448, 576]]
# frame_buckets = [1]
"""
        with self.FILE_CONFIG_DATASET.open("w", encoding="utf-8") as f:
            f.write(str_file)

    #
    # diffpipe configs
    #
    def _make_file_diffpipe_config(self) -> None:
        if self._type_model == "wan21":
            self._make_file_diffpipe_config_wan21()
        elif self._type_model == "wan22_high":
            self._make_file_diffpipe_config_wan22_high()
        elif self._type_model == "wan22_low":
            self._make_file_diffpipe_config_wan22_low()
        elif self._type_model == "qwen_image":
            self._make_file_diffpipe_config_qwen_image()
        elif self._type_model == "qwen_jib":
            self._make_file_diffpipe_config_qwen_image()
        else:
            raise ValueError(f"unknown training type: {self._type_model}")

    #
    # wan22_high diffpipe config
    #
    def _make_file_diffpipe_config_wan22_high(self) -> None:
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
caching_batch_size = {self._batch_size}

# Number of parallel processes to use in map() calls when caching the dataset. Defaults to min(8, num_cpu_cores) if unset.
# If you have a lot of cores and multiple GPUs, raising this can increase throughput of caching, but it may use more memory,
# especially for video data.
#map_num_proc = 32

# Use torch.compile on the model. Can speed up training throughput by a decent amount. Not tested on all models.
#compile = true

# How often deepspeed logs to console.
steps_per_print = 10
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
ckpt_path = '{self._model_links["base"]}'
# this is the used checkpoint model (compatible with the base checkpoint config!)
transformer_path = '{self._model_links["ckpt"]}'
# this is the used text encoder model (compatible with the base checkpoint config!)
llm_path = '{self._model_links["text_encoder"]}'
dtype = 'bfloat16'
transformer_dtype = 'float8'
timestep_sample_method = 'logit_normal'
min_t = 0.875
max_t = 1

# For models that support full fine tuning, simply delete or comment out the [adapter] table to FFT.
[adapter]
type = 'lora'
rank = {int(self._config_train["netdim"])}
# Dtype for the LoRA weights you are training.
dtype = 'bfloat16'
# You can initialize the lora weights from a previously trained lora.
#init_from_existing = '/data/diffusion_pipe_training_runs/something/epoch50'
# Experimental. Can fuse LoRAs into the base weights before training. Right now only for Flux.

[optimizer]
# AdamW from the optimi library is a good default since it automatically uses Kahan summation when training bfloat16 weights.
# Look at train.py for other options. You could also easily edit the file and add your own.
type = 'adamw_optimi'
lr = {self._lr}
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

    #
    # wan22_low diffpipe config
    #
    def _make_file_diffpipe_config_wan22_low(self) -> None:
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
caching_batch_size = {self._batch_size}

# Number of parallel processes to use in map() calls when caching the dataset. Defaults to min(8, num_cpu_cores) if unset.
# If you have a lot of cores and multiple GPUs, raising this can increase throughput of caching, but it may use more memory,
# especially for video data.
#map_num_proc = 32

# Use torch.compile on the model. Can speed up training throughput by a decent amount. Not tested on all models.
#compile = true

# How often deepspeed logs to console.
steps_per_print = 10
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
ckpt_path = '{self._model_links["base"]}'
# this is the used checkpoint model (compatible with the base checkpoint config!)
transformer_path = '{self._model_links["ckpt"]}'
# this is the used text encoder model (compatible with the base checkpoint config!)
llm_path = '{self._model_links["text_encoder"]}'
dtype = 'bfloat16'
transformer_dtype = 'float8'
timestep_sample_method = 'logit_normal'
min_t = 0.0
max_t = 0.875

# For models that support full fine tuning, simply delete or comment out the [adapter] table to FFT.
[adapter]
type = 'lora'
rank = {int(self._config_train["netdim"])}
# Dtype for the LoRA weights you are training.
dtype = 'bfloat16'
# You can initialize the lora weights from a previously trained lora.
#init_from_existing = '/data/diffusion_pipe_training_runs/something/epoch50'
# Experimental. Can fuse LoRAs into the base weights before training. Right now only for Flux.

[optimizer]
# AdamW from the optimi library is a good default since it automatically uses Kahan summation when training bfloat16 weights.
# Look at train.py for other options. You could also easily edit the file and add your own.
type = 'adamw_optimi'
# for low noise training, double the learning rate
lr = {2.0 * self._lr}
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

    #
    # wan21 diffpipe config
    #
    def _make_file_diffpipe_config_wan21(self) -> None:
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
caching_batch_size = {self._batch_size}

# Number of parallel processes to use in map() calls when caching the dataset. Defaults to min(8, num_cpu_cores) if unset.
# If you have a lot of cores and multiple GPUs, raising this can increase throughput of caching, but it may use more memory,
# especially for video data.
#map_num_proc = 32

# Use torch.compile on the model. Can speed up training throughput by a decent amount. Not tested on all models.
#compile = true

# How often deepspeed logs to console.
steps_per_print = 10
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
ckpt_path = '{self._model_links["base"]}'
# this is the used checkpoint model (compatible with the base checkpoint config!)
transformer_path = '{self._model_links["ckpt"]}'
# this is the used text encoder model (compatible with the base checkpoint config!)
llm_path = '{self._model_links["text_encoder"]}'
dtype = 'bfloat16'
transformer_dtype = 'float8'
timestep_sample_method = 'logit_normal'

# For models that support full fine tuning, simply delete or comment out the [adapter] table to FFT.
[adapter]
type = 'lora'
rank = {int(self._config_train["netdim"])}
# Dtype for the LoRA weights you are training.
dtype = 'bfloat16'
# You can initialize the lora weights from a previously trained lora.
#init_from_existing = '/data/diffusion_pipe_training_runs/something/epoch50'
# Experimental. Can fuse LoRAs into the base weights before training. Right now only for Flux.

[optimizer]
# AdamW from the optimi library is a good default since it automatically uses Kahan summation when training bfloat16 weights.
# Look at train.py for other options. You could also easily edit the file and add your own.
type = 'adamw_optimi'
lr = {self._lr}
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

    #
    # qwen-image diffpipe config
    #
    def _make_file_diffpipe_config_qwen_image(self) -> None:
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
gradient_accumulation_steps = 4
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
#blocks_to_swap = 8

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
caching_batch_size = 8

# Number of parallel processes to use in map() calls when caching the dataset. Defaults to min(8, num_cpu_cores) if unset.
# If you have a lot of cores and multiple GPUs, raising this can increase throughput of caching, but it may use more memory,
# especially for video data.
#map_num_proc = 32

# Use torch.compile on the model. Can speed up training throughput by a decent amount. Not tested on all models.
#compile = true

# How often deepspeed logs to console.
steps_per_print = 10

# How to extract video clips for training from a single input video file.
# The video file is first assigned to one of the configured frame buckets, but then we must extract one or more clips of exactly the right
# number of frames for that bucket.
# single_beginning: one clip starting at the beginning of the video
# single_middle: one clip from the middle of the video (cutting off the start and end equally)
# multiple_overlapping: extract the minimum number of clips to cover the full range of the video. They might overlap some.
# default is single_beginning
# video_clip_mode = 'single_beginning'

# This is how you configure WAN video. Other models will be different. See docs/supported_models.md for
# details on the configuration and options for each model.
[model]
type = 'qwen_image'
# this is the config checkout for the checkpoint but w/o the specific model
diffusers_path = '{self._model_links["base"]}'
# this is the used checkpoint model (compatible with the base checkpoint config!)
transformer_path = '{self._model_links["ckpt"]}'
# this is the used text encoder model (compatible with the base checkpoint config!)
#text_encoder_path = '{self._model_links["text_encoder"]}'
dtype = 'bfloat16'
transformer_dtype = 'float8'
timestep_sample_method = 'logit_normal'

# For models that support full fine tuning, simply delete or comment out the [adapter] table to FFT.
[adapter]
type = 'lora'
rank = {int(self._config_train["netdim"])}
# Dtype for the LoRA weights you are training.
dtype = 'bfloat16'
# You can initialize the lora weights from a previously trained lora.
#init_from_existing = '/data/diffusion_pipe_training_runs/something/epoch50'
# Experimental. Can fuse LoRAs into the base weights before training. Right now only for Flux.

[optimizer]
# AdamW from the optimi library is a good default since it automatically uses Kahan summation when training bfloat16 weights.
# Look at train.py for other options. You could also easily edit the file and add your own.
type = 'adamw_optimi'
lr = {self._lr}
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
#type = 'automagic'
#weight_decay = 0.01

# Any optimizer not explicitly supported will be dynamically loaded from the pytorch-optimizer library.
# [optimizer]
# type = 'Prodigy'
# lr = 1
# betas = [0.9, 0.99]
# weight_decay = 0.01
"""
        with self.FILE_CONFIG_DIFFPIPE.open("w", encoding="utf-8") as f:
            f.write(str_file)

    #
    # train script
    #
    def _make_file_train_script(self) -> None:
        str_file = f"""
NCCL_P2P_DISABLE="1" NCCL_IB_DISABLE="1" deepspeed --num_gpus=1 train.py --deepspeed --config {self.FILE_CONFIG_DIFFPIPE}
"""
        # save train string to train script and chmod 777 it.
        with self.FILE_TRAIN_SCRIPT.open("w", encoding="utf-8") as f:
            f.write(str_file)
        self.FILE_TRAIN_SCRIPT.chmod(0o777)
