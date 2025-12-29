from trainer import Trainer

dataset_repo_ids = ['fbbcool/1man']
Trainer('train_zimage:turbo', dataset_repo_ids, multithread=True)
