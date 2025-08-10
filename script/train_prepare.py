#from aidb.trainer_kohya import Trainer
from trainer import Trainer
repo_id="fbbcool/1fbb_02"
Trainer(repo_id, cache_full_dataset=True, multithread=True, caption_missing=True)