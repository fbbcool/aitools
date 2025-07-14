import shutil
from pathlib import Path
from aidb.trainer import TrainerKohya

folder_train = TrainerKohya.ROOT
from_file = Path(TrainerKohya.FILENAME_CONFIG)
to_file = folder_train / TrainerKohya.FILENAME_CONFIG
# copy train config to train folder
shutil.copy(str(from_file), str(to_file))

TrainerKohya(folder_train)