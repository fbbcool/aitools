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
# ─── qwen-5090 (32 GB) ───────────────────────────────────────────────────
# Local card. mb=2 fits tight at 1024² rank=32 float8. ~5-7 s/step.
# 3K-step test ≈ 4 h.
config_trainer_qwen_5090 = {
    'epochs': 1000,  # sentinel, manual cancel ~3K steps
    'micro_batch_size_per_gpu': 2,
    'warmup_steps': 50,  # small cushion for LR=2e-4 early-spike risk
    'save_every_n_epochs': 3,  # ~225 steps/epoch → ~5 ckpts at 3K cancel
    'caching_batch_size': 4,
    'steps_per_print': 10,
    'adapter___rank': 32,
    'optimizer___lr': 2e-4,
}

# ─── qwen-H100 80GB ──────────────────────────────────────────────────────
# Rental ($2-3/hr). mb=8 with full 80 GB headroom. ~3-4 s/step at mb=8,
# 10× higher samples-per-second throughput vs 5090 mb=1.
# 3K-step test ≈ 1 h, 24K samples seen (= ~107 effective epochs over 225 imgs × 2).
config_trainer_qwen_h100 = {
    'epochs': 1000,  # sentinel, manual cancel ~3K steps
    'micro_batch_size_per_gpu': 8,  # H100 80GB has the headroom; 4× the 5090 mb=2
    'warmup_steps': 100,  # longer warmup for 1.5× LR and 4× effective batch
    'save_every_n_epochs': 10,  # mb=8 → ~56 steps/epoch; 10 epochs = ~560 steps → ~5 ckpts at 3K
    'caching_batch_size': 8,  # match mb for fast initial latent cache pass
    'steps_per_print': 10,
    'adapter___rank': 32,
    'optimizer___lr': 4e-4,  # mild bump for 4× larger effective batch (linear-scaling would suggest 8e-4; LoRA-on-pretrained is less sensitive)
}

# Pick which GPU you're training on. Swap this single line to switch configs.
config_trainer = config_trainer_qwen_5090
# config_trainer = config_trainer_qwen_h100
config_dataset = {
    'num_repeats': 2,
    # The 7 distinct (w, h) pairs in the compiled gts_v3 training set.
    # All max-side 1024, AR bucketed: 1:1, 3:4/4:3, 2:3/3:2, 3:5/5:3.
    'resolutions': [
        [1024, 1024],  # 137 images
        [768, 1024],  # 27
        [1024, 768],  # 12
        [682, 1024],  # 5
        [1024, 682],  # 7
        [614, 1024],  # 26
        [1024, 614],  # 11
    ],
}


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
    ('fbbcool/gts-v3', 0),
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
    'qwen',
    dataset_repo_ids,
    variant='2512-snofs',
    config_trainer=config_trainer_qwen_h100,
    config_dataset=config_dataset,
    multithread=True,
)

"""
    NOTES ZIMAGE Base:
    - lr 5e-5 seems too less
    - rank 32 seems too less
"""
