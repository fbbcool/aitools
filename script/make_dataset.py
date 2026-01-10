import os
from pathlib import Path

from aidb.dbmanager import DBManager
from aidb.dbstatistics import Statistics
from aidb.query import Query

config_file = Path(os.environ['HOME_AIT']) / 'conf/aidb/dbmanager.yaml'
path_pool = Path('/home/misw/Data/AI/pool')
name_collection = '1gts_xlasm_01'
path_train = path_pool / f'___train_{name_collection}'
path_collection = path_pool / name_collection

dbm = DBManager(config_file=str(config_file))

dbm.add_container(path_collection, collection=name_collection)
sta = Statistics(dbm)
dbm.set_collection(name_collection)

for img in dbm.images:
    img.init_tags()
    img.thumbnail
    sta.img_statistics_init(img, force=True)

q = Query(dbm)
imgs = q.query_by_rating(-2, 5)
print(f'found {len(imgs)} imgs.')

for img in imgs:
    img.train_image
    img.export_train(str(path_train), export_cap_files=False, trigger='1gts')
