env_inst() {
    pip install -r $ENV_HOME/requirements.txt
    env_pools_inst https://drive.google.com/file/d/1wdS5ULSgHV6KaaH9y6vHZY_-O6m5AXpB/view?usp=sharing
}
env_pools_inst() {
    if [ "$#" -eq 0 ]; then
    echo "using local pools tar"
    else
    echo "downloading gdrive pools tar"
    gdown --fuzzy $1 -O $ENV_POOLS_TAR
    fi
    tar xf $ENV_POOLS_TAR -C $ENV_HOME
}
env_cap() {
    accelerate launch\
        "$ENV_DIR_KOHYA/finetune/tag_images_by_wd14_tagger.py"\
        --batch_size=8 --general_threshold=0.65\
        --character_threshold=0.65\
        --caption_extension=".caption_wd14"\
        --model="SmilingWolf/wd-v1-4-convnextv2-tagger-v2"\
        --max_data_loader_n_workers="2" --recursive --debug\
        --remove_underscore\
        --frequency_tags "/root/train/build/pools"
}
env_help_train() {
    echo '#env_train pool trigger profile sd_version model epochs version'
}
env_train() {
    pool=$1
    trigger=$2
    profile=$3
    sd_version=$4
    model=$5
    epochs=$6
    version=$7
    url_model=$ENV_MODELS/$model
    train_dir=$ENV_TRAINS/$pool
    
    accelerate launch\
        --num_cpu_threads_per_process=2\
        "$ENV_DIR_KOHYA/train_network.py"\
        --enable_bucket\
        --min_bucket_reso=256\
        --max_bucket_reso=2048\
        --pretrained_model_name_or_path="$url_model"\
        --train_data_dir="$train_dir"\
        --resolution="768,768"\
        --output_dir="$train_dir"\
        --logging_dir="$train_dir"\
        --network_alpha="128"\
        --save_model_as=safetensors\
        --network_module=networks.lora\
        --text_encoder_lr=0.00015\
        --unet_lr=0.00015\
        --network_dim=256\
        --output_name="$pool-$trigger-v$version"\
        --lr_scheduler_num_cycles="$epochs"\
        --no_half_vae\
        --learning_rate="0.00015"\
        --lr_scheduler="cosine"\
        --lr_warmup_steps="11"\
        --train_batch_size="8"\
        --max_train_steps="107"\
        --save_every_n_epochs="1"\
        --mixed_precision="bf16"\
        --save_precision="bf16"\
        --caption_extension=".caption"\
        --cache_latents\
        --cache_latents_to_disk\
        --optimizer_type="AdamW8bit"\
        --max_data_loader_n_workers="0"\
        --bucket_reso_steps=64\
        --gradient_checkpointing\
        --xformers\
        --bucket_no_upscale\
        --noise_offset=0.0\
        --sample_sampler=euler_a\
        --sample_prompts="$train_dir/sample/prompt.txt"\
        --sample_every_n_epochs="1"
}

export ENV_POOLS=$ENV_HOME/pools
export ENV_TRAINS=$ENV_HOME/trains
export ENV_MODELS=$ENV_HOME/models
export ENV_TMP=$ENV_HOME/tmp
export ENV_POOLS_TAR=$ENV_TMP/pools.tar
export ENV_DIR_KOHYA=/kohya_ss

mkdir -p $ENV_POOLS
mkdir -p $ENV_TRAINS
mkdir -p $ENV_MODELS
mkdir -p $ENV_TMP

source $ENV_DIR_KOHYA/venv/bin/activate