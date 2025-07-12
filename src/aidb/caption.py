from aidb.caption_joy import CapJoy
from hfdataset import HFDatasetImg

caper = CapJoy(configure_ai=False)
hfd = HFDatasetImg(repo_id="fbbcool/gts01_r5")