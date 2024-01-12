import os
import glob
from pathlib import Path
from typing import Final
import numpy as np
import pandas as pd
import shutil
import random
from PIL import Image
import face_recognition
import imageio as iio

from .defines import Defines
from ..tags import Tags, build_caps, TagsProfile
from .imgpool import ImgPool

class ImgPools():
    def __init__(self,
                 pools_dict: dict,
                 num_pics:int = 100,
                 train_steps: int = 20,
                 epochs: int = 10,
                 crawl = False,
                 ) -> None:
        self.pools_dict = pools_dict
        self.num_pics = num_pics
        self.train_steps = train_steps
        self.epochs = epochs

        dict_rows = []
        for pool_name, crawl_dir in self.pools_dict.items():
            if not crawl:
                crawl_dir = ""
            pool = ImgPool(pool_name, self.num_pics, crawl_dir)
            if crawl:
                pool.pool_extract_faces
            dict_rows.append((pool_name, pool))
        self.pools = dict(dict_rows)
