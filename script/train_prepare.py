from trainer import Trainer
repo_id="fbbcool/1gts_03_1k"
Trainer(repo_id, type_model="wan21", load_models=True, cache_full_dataset=True, multithread=True, caption_missing=False)