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

model = 'qwen'
variant = '2512-gts-app'
gpu = '5090'
# gpu = 'h100'
trigger = 'xlhairy'
num_repeats = 1

# ──────────────────────────────────────────────────────
gpu_config = {
    '5090': {
        'micro_batch_size_per_gpu': 2,  # maybe 1
    },
    'h100': {
        'micro_batch_size_per_gpu': 12,  # maybe 1
    },
}

# ──────────────────────────────────────────────────────
config_trainer_qwen_default = {
    'epochs': 30,  # sentinel, manual cancel ~3K steps
    'micro_batch_size_per_gpu': gpu_config[gpu].get('micro_batch_size_per_gpu', 1),
    'warmup_steps': 50,  # small cushion for LR=2e-4 early-spike risk
    'save_every_n_epochs': 1,  # ~225 steps/epoch → ~5 ckpts at 3K cancel
    'checkpoint_every_n_epochs': 1,
    'caching_batch_size': 4,
    'steps_per_print': 10,
    'adapter___rank': 16,  # 32 for xlasm, 16 for xlasm-childs
    'optimizer___lr': 5e-5,
}

config_trainer_qwen_gts_atomic = {
    'epochs': 30,  # sentinel, manual cancel ~3K steps
    'micro_batch_size_per_gpu': gpu_config[gpu].get('micro_batch_size_per_gpu', 1),
    'warmup_steps': 50,  # small cushion for LR=2e-4 early-spike risk
    'save_every_n_epochs': 1,  # ~225 steps/epoch → ~5 ckpts at 3K cancel
    'checkpoint_every_n_epochs': 1,
    'caching_batch_size': 4,
    'steps_per_print': 10,
    'adapter___rank': 4,  # 32 for xlasm, 16 for xlasm-childs
    #'adapter___alpha': 4,  # will break; is set automatically!
    'optimizer___lr': 5e-5,
}

config_trainer_qwen_gts_domain = {
    'epochs': 30,  # sentinel, manual cancel ~3K steps
    'micro_batch_size_per_gpu': gpu_config[gpu].get('micro_batch_size_per_gpu', 1),
    'warmup_steps': 50,  # small cushion for LR=2e-4 early-spike risk
    'save_every_n_epochs': 1,  # ~225 steps/epoch → ~5 ckpts at 3K cancel
    'checkpoint_every_n_epochs': 1,
    'caching_batch_size': 4,
    'steps_per_print': 10,
    'adapter___rank': 16,  # 32 for xlasm, 16 for xlasm-childs
    #'adapter___alpha': 4,  # will break; is set automatically!
    'optimizer___lr': 5e-5,
}

config_trainer_qwen_gts_app = {
    'epochs': 30,  # sentinel, manual cancel ~3K steps
    'micro_batch_size_per_gpu': gpu_config[gpu].get('micro_batch_size_per_gpu', 1),
    'warmup_steps': 50,  # small cushion for LR=2e-4 early-spike risk
    'save_every_n_epochs': 1,  # ~225 steps/epoch → ~5 ckpts at 3K cancel
    'checkpoint_every_n_epochs': 1,
    'caching_batch_size': 4,
    'steps_per_print': 10,
    'adapter___rank': 8,  # 32 for xlasm, 16 for xlasm-childs
    #'adapter___alpha': 4,  # will break; is set automatically!
    'optimizer___lr': 5e-5,
}

config_trainer = {
    'gts-atomic': config_trainer_qwen_gts_atomic,
    'gts-domain': config_trainer_qwen_gts_domain,
    'gts-app': config_trainer_qwen_gts_app,
}

# config_trainer = config_trainer_qwen_h100
config_dataset = {
    'num_repeats': num_repeats,
    # The 7 distinct (w, h) pairs in the compiled gts_v3 training set.
    # All max-side 1024, AR bucketed: 1:1, 3:4/4:3, 2:3/3:2, 3:5/5:3.
    'resolutions': [1024],
    #'resolutions_arr': [
    #    [1024, 1024],  # 137 images
    #    [768, 1024],  # 27
    #    [1024, 768],  # 12
    #    [682, 1024],  # 5
    #    [1024, 682],  # 7
    #    [614, 1024],  # 26
    #    [1024, 614],  # 11
    # ],
}


# 25 hand-picked negative-reinforcement images from gts-v3: xlasm-man-visible
# scenes WITHOUT the trigger in caption. Mix is 5 visually-<trait> + 20 non-<trait>
# so the LoRA learns "trigger word controls direction; no trigger means leave
# the base alone" — without anti-<trait> overcorrection.
# Seed-42 deterministic picks (see chat 2026-05-15 / 2026-05-16). One list per
# child LoRA trigger; reusable structure for future variants.
GTS_V3_NEUTRAL_IDS_XLBUSTY = [
    # visually-busty (5)
    '699819274d0d7eab18d0b74e',
    '699ff1d6fe4c5b5e9428c3d4',
    '69a010eee34f3773c3e11627',
    '69a04fa35d1034e14b4ff9ca',
    '69ba76acc3661e57c85b5d50',
    # non-busty (20)
    '699249a83badfdf5ebc2dec2',
    '699249f84400748d775af6ed',
    '699b2f55d9a2092bd3697ba3',
    '69a03b057d06620c736d5a7e',
    '69a15a40b4eba93e5a5be5f3',
    '69aaccab38ae0d7573d34519',
    '69abfba83a7b447484e8675d',
    '69abfbe4be8b30e6df2ca05b',
    '69b46c631492d0320e58b759',
    '69b55166633fc9d7148052fb',
    '69b80b6c3c7514168ba3e9a7',
    '69b91a1a699de0ba852d765b',
    '69d6628b1ef71f3a869cf13a',
    '69f1ba2be6f43bff7281e70b',
    '69f4c536f51e90857c7cc041',
    '69f4c70cf7b7f5b04564e5f6',
    '69f4ca43f7b7f5b04564e600',
    '69f4d0aff7b7f5b04564e609',
    '69f4f699f7b7f5b04564e625',
    '6a01834201706560d646e09c',
]

GTS_V3_NEUTRAL_IDS_XLFBB = [
    # visually-muscular (5) — top muscle-vocab scores in caption
    '69b7ce8912e8afd94e30a7aa',
    '69e733fd5786b77c674f03c5',
    '69a0b39a60d12c61bf20cf3c',
    '6985aec92cfffda31ac30177',
    '69a0a47a1cb05ee4c46856e4',
    # non-muscular (20) — zero muscle-vocab hits
    '69924a9b384cdb179424498f',
    '69924ab43fa460b64d3e0fa5',
    '69924ac7da9f782aa6b027da',
    '699b2efefc58e585ac50316c',
    '699b2f55d9a2092bd3697ba3',
    '699d84049e97b6ad8d907b5f',
    '699fec7a7ea0a6b3ad6d2ba3',
    '699fefda7488868ef9fff6c5',
    '69a02284b5f1df6db04bd2a9',
    '69a03289d2eaae22ae7d7b63',
    '69a039d7de5bd8d5d0cfb1ce',
    '69a054415a1ed000dc67b233',
    '69a07074b442fc21c04557d5',
    '69b5f91dc44371f1c8fd9c1e',
    '69f1b9e4dd176af24c7c43aa',
    '69f4c17447f2f7cb69ea4779',
    '69f4f5e0f7b7f5b04564e622',
    '69f5ee1a2ace974433a05899',
    '69fcdab1fa205eb4e836a73a',
    '69fd0eb66954ff47171d2a25',
]

GTS_V3_NEUTRAL_IDS_XLHAIRY = [
    # visually-hairy (5) — top body-hair-vocab scores; mostly "hairy vagina" /
    # "pubic hair" — the dominant body-hair signal in gts-v3
    '69924d8809529408668e3fae',
    '699d726bd3279c7d6d664e29',
    '69a06f268ef8ca9601240b41',
    '69d65e329cf7031b2f76a866',
    '69f4d0aff7b7f5b04564e609',
    # non-hairy (20) — zero body-hair-vocab hits
    '699249f84400748d775af6ed',
    '699249f84400748d775af6ee',
    '69924a763047462eed28448b',
    '69984f68eb78023edc3f7d5a',
    '6999e4e9849eb45a408f1d73',
    '699b2efefc58e585ac50316c',
    '699d7cc7265f47abbf93bc92',
    '699fefb0d0027a60909d56ec',
    '69a039d7de5bd8d5d0cfb1ce',
    '69a04f56aea6c37833a7a42b',
    '69a054415a1ed000dc67b233',
    '69a056d15296c46da2b12233',
    '69a0af479d4bfb80e1fc9dac',
    '69b6953643ce44f7ed645e7c',
    '69f4b1f8f94a40ee841afc06',
    '69f4ca43f7b7f5b04564e600',
    '69f5155af7b7f5b04564e63c',
    '69fc4ff6a1bb53c7b873f998',
    '69ff04df963c529e79b984f3',
    '6a00c12e91745ea668752f19',
]

GTS_V3_NEUTRAL_IDS_XLLEGGY = [
    # visually-leggy (5) — only 2 are explicitly labeled `primary.attribute.leggy`
    # in gts-v3 (it's a thin label), so we round out with 3 `primary.attribute.slim`
    # images whose pose visually codes leg-prominent (standing/towering or
    # pantyhose+legs-spread). Same pedagogical purpose as the other sets: teach
    # "leggy aesthetic can occur without my trigger."
    '69ab30ca1acf6dfd69c33b25',  # labeled leggy; man embraces her calf
    '69a0b39a60d12c61bf20cf3c',  # labeled leggy + muscular, big calves
    '69890c7e6b0f7355de70e792',  # slim athletic standing
    '699249175a67682b0e40735b',  # slim athletic, towering pose
    '69924ac7da9f782aa6b027da',  # slim, pantyhose, legs spread
    # non-leggy (20) — excluded both `primary.attribute.leggy` and
    # `primary.attribute.slim` labels, then seed=42 random pick
    '699249f84400748d775af6ee',
    '69924a763047462eed28448b',
    '69924a9b384cdb179424498f',
    '699826f00eaf60eef719a303',
    '69984f68eb78023edc3f7d5a',
    '699b2ed64c23aa1ee21496c9',
    '699b2f55d9a2092bd3697ba3',
    '699fed1043950c1b1939c335',
    '69a017de528db275bb9d5aee',
    '69a01bbfbedc65ea2f80331c',
    '69a01dcfd36d82175984a6e7',
    '69a03289d2eaae22ae7d7b63',
    '69a056a3e505da2507125762',
    '69abfbe4be8b30e6df2ca05b',
    '69d65e228aaa547684912022',
    '69f1ba08b23149eaada60a0e',
    '69f4b223f94a40ee841afc09',
    '69f4d0aff7b7f5b04564e609',
    '69f5ee1a2ace974433a05899',
    '69f727d19f03180e9df1e288',
]

datasets = {
    'xlasm': [
        ('fbbcool/gts-v3', 0),
    ],
    'xlbusty': [
        ('fbbcool/1busty', 0),
        # max_imgs=len(ids) so every ID in the filter list gets picked; the 3rd
        # tuple element is the explicit ID filter (Trainer's _make_dataset_hfd
        # restricts the source pool to those before pick_chance is applied).
        ('fbbcool/gts-v3', len(GTS_V3_NEUTRAL_IDS_XLBUSTY), GTS_V3_NEUTRAL_IDS_XLBUSTY),
    ],
    'xlfbb': [
        ('fbbcool/1fbb_02', 0),
        ('fbbcool/gts-v3', len(GTS_V3_NEUTRAL_IDS_XLFBB), GTS_V3_NEUTRAL_IDS_XLFBB),
    ],
    'xlhairy': [
        ('fbbcool/xlhairy', 0),
        ('fbbcool/gts-v3', len(GTS_V3_NEUTRAL_IDS_XLHAIRY), GTS_V3_NEUTRAL_IDS_XLHAIRY),
    ],
    'xlleggy': [
        ('fbbcool/xlleggy', 0),
        ('fbbcool/gts-v3', len(GTS_V3_NEUTRAL_IDS_XLLEGGY), GTS_V3_NEUTRAL_IDS_XLLEGGY),
    ],
    'xlface_jez': [
        ('fbbcool/face-jez', 0),
    ],
}

Trainer(
    model,
    datasets[trigger],
    variant=variant,
    config_trainer=config_trainer_qwen_gts_app,
    config_dataset=config_dataset,
    multithread=True,
)

"""
    NOTES ZIMAGE Base:
    - lr 5e-5 seems too less
    - rank 32 seems too less
"""
