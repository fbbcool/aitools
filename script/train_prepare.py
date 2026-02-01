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
    'epochs': 1000,
    'micro_batch_size_per_gpu': 4,
    'warmup_steps': 20,
    'save_every_n_epochs': 1,
    'caching_batch_size': 4,
    'steps_per_print': 10,
    'adapter___rank': 32,
    'optimizer___lr': 2e-4,
}
config_dataset = {'num_repeats': 8, 'resolutions': [1024]}


# dataset_repo_ids = [('fbbcool/1gts-xlasm-01', 0)]
# dataset_repo_ids = [('fbbcool/1fbb_02', 150)]
# dataset_repo_ids = [
#    ('fbbcool/1busty', 100),
#    ('fbbcool/1legsemp', 100),
#    ('fbbcool/1fem', 100),
#    ('fbbcool/1fbb_02', 100),
# ]
# dataset_repo_ids = [
#    ('fbbcool/1busty', 150),
#    ('fbbcool/1busty-gts', 150),
#    ('fbbcool/1fem', 150),
# ]
# dataset_repo_ids = [
#    ('fbbcool/1legsemp', 0),
#    ('fbbcool/1fbb_02', 200),
# ]
dataset_repo_ids = [
    ('fbbcool/1fem_alexandra', 0),
]
# Trainer(
#    'qwen',
#    dataset_repo_ids,
#    # variant='2512-1gts',
#    variant='2512',
#    config_trainer=config_trainer,
#    config_dataset=config_dataset,
#    multithread=True,
# )
Trainer(
    'zimage',
    dataset_repo_ids,
    variant='base',
    config_trainer=config_trainer,
    config_dataset=config_dataset,
    multithread=True,
)

"""
    NOTES ZIMAGE Base:
    - lr 5e-5 seems too less
    - rank 32 seems too less
"""
