from trainer import Trainer
repo_ids=["fbbcool/1gts_03_1k", "fbbcool/1man", "fbbcool/1fem"]
Trainer(repo_ids, type_model="wan22_high", multithread=True)