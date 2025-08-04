#from aidb.trainer_kohya import Trainer
from aidb.trainer_diffpipe import Trainer
repo_id="fbbcool/1gts_wan01"
Trainer(repo_id, cache_full_dataset=True, mutlitread=True)