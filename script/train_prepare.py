from trainer import Trainer

# config_trainer = {
#    'output_dir': '/workspace/train/output',
#    'dataset': '/workspace/train/dataset.toml',
#    'epochs': 40,
#    'micro_batch_size_per_gpu': 1,
#    'warmup_steps': 20,
#    'save_every_n_epochs': 1,
#    'save_dtype': 'bfloat16',
#    'caching_batch_size': 1,
#    'steps_per_print': 10,
#    'blocks_to_swap': '',
#    'model___type': 'qwen_image',
#    'model___ckpt_path': '',
#    'model___transformer_path': '',
#    'model___llm_path': '',
#    'model___vae_path': '',
#    'model___transformer_dtype': 'float8',
#    'model___dtype': 'bfloat16',
#    'model___min_t': '',
#    'model___max_t': '',
#    'adapter___rank': 16,
#    'adapter___dtype': 'bfloat16',
#    'optimizer___lr': 2e-5,
#    'optimizer___weight_decay': 0.01,
#    'optimizer___type': 'adamw_optimi',
# }
config_trainer = {
    'epochs': 40,
    'micro_batch_size_per_gpu': 1,
    'warmup_steps': 20,
    'save_every_n_epochs': 1,
    'save_dtype': 'bfloat16',
    'caching_batch_size': 1,
    'steps_per_print': 10,
    'blocks_to_swap': '',
    'model___type': 'qwen_image',
    'adapter___rank': 16,
    'optimizer___lr': 5e-5,
}
config_dataset = {'num_repeats': 1, 'resolutions': [1024]}


dataset_repo_ids = ['fbbcool/1legsemp']
Trainer(
    'qwen',
    dataset_repo_ids,
    variant='2512',
    config_trainer=config_trainer,
    config_dataset=config_dataset,
    multithread=True,
)
