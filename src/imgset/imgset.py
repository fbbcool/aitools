import os
from pathlib import Path
from typing import Final
import numpy as np
import pandas as pd
from PIL import Image
import tarfile


from .defines import Defaults, Defines

class ImgSet:
    TEST_PATH_CRAWL : Final = "test/imgs"
    def __init__(self,
                 dir: str = "",
                 name:str = Defaults.NAME,
                 celeb:str = Defaults.CELEB,
                 classobj:str = Defaults.CLASS,
                 steps:int = Defaults.STEPS,
                 v_maj:int = Defaults.V_MAJOR,
                 v_min:int = Defaults.V_MINOR,
                 v_build:int = Defaults.V_BUILD,
                 new_build: bool = False,
                 ) -> None:
        self.path_crawl = dir
        self.name = name
        self.celeb = celeb
        self.classobj = classobj
        self.steps = steps
        self.v_maj = v_maj
        self.v_min = v_min
        self.v_build = v_build

        self.df : pd.DataFrame


        if self.path_crawl:
            if not os.path.isdir(self.path_crawl):
                raise FileNotFoundError(f"Directory {self.path_crawl} not found!")
            self._initialize_new()
        elif True:
            if not os.path.isdir(self._get_build_path):
                raise FileNotFoundError(f"Build {self._get_build_path} not found!")
            self._initialize()

    def _initialize(self):
        paths = []
        dirs = [dir[0] for dir in os.walk(self._get_build_path)]
        for dir in dirs:
            path = Path(dir)
            paths += list(set(path.glob("*.png")))
        
        df_data = []
        for img in paths:
            pool = Path(img).parts[-2]
            pool_id = Path(img).stem
            df_data.append({
                Defines.DF_POOL: pool,
                Defines.DF_POOL_ID: pool_id,
                Defines.DF_CAP: [],
                Defines.DF_CAP_NEG: [],
                Defines.DF_TAG_WD14: [],
                Defines.DF_TAG_BLIP: [],
                Defines.DF_FILE_IMG: self._get_img_file(pool, pool_id),
                Defines.DF_FILE_CRAWL: "",
            })

        self.df = pd.DataFrame(df_data, columns=Defines.DF_COLUMNS)
        self.reload_tags()

    def _initialize_new(self):
        paths = []
        dirs = [dir[0] for dir in os.walk(self.path_crawl)]
        for dir in dirs:
            path = Path(dir)
            paths += list(set(path.glob("*.jpg")))
        
        df_data = []
        for file_crawl in paths:
            df_data.append({
                Defines.DF_POOL: "",
                Defines.DF_POOL_ID: "",
                Defines.DF_CAP: [],
                Defines.DF_CAP_NEG: [],
                Defines.DF_TAG_WD14: [],
                Defines.DF_TAG_BLIP: [],
                Defines.DF_FILE_IMG: "",
                Defines.DF_FILE_CRAWL: file_crawl,
            })
        self.df = pd.DataFrame(df_data, columns=Defines.DF_COLUMNS)

        for idx, row in self.rows:
            pool, pool_id = self._get_pool(row)
            self.df.at[idx, Defines.DF_POOL] = pool
            self.df.at[idx, Defines.DF_POOL_ID] = pool_id

        self._create_build_structure()
        
        for idx, row in self.rows:
            self._convert2png(idx, row)
    
    def _convert2png(self, idx, row):
        image = Image.open(row[Defines.DF_FILE_CRAWL])
        image = image.convert('RGB')
        self.df.at[idx, Defines.DF_FILE_IMG] = self._get_img_file(row[Defines.DF_POOL], row[Defines.DF_POOL_ID])
        image.save(row[Defines.DF_FILE_IMG])

    def _get_pool(self, row) -> tuple[str,str]:
        pool = Path(row[Defines.DF_FILE_CRAWL]).parts[-2]
        pool = pool.replace(" ", "_")
        pool = f"{self.steps}_{pool}"
        
        pool_id = Path(row[Defines.DF_FILE_CRAWL]).stem
        pool_id = pool_id.replace(" ", "_")
        
        return pool, pool_id
    
    def _create_build_structure(self) -> None:
        while os.path.isdir(self._get_build_path):
            self.v_build += 1
        os.mkdir(self._get_build_path)
        for pool in self.pools:
            os.mkdir(f"{self._get_build_path}/{self._get_pool_dir(pool)}")

    def _get_pool_dir(self, pool: str) -> str:
        return f"{pool}"
    
    def _get_pool_id_img_file(self, pool_id: str) -> str:
        return f"{pool_id}.png"
    
    def _get_pool_id_tag_file(self, pool_id: str) -> str:
        return f"{pool_id}.txt"
    
    def _get_pool_id_cap_file(self, pool_id: str) -> str:
        return f"{pool_id}.caption"
    
    def _get_img_file(self, pool: str, pool_id: str) -> str:
        return f"{self._get_build_path}/{self._get_pool_dir(pool)}/{self._get_pool_id_img_file(pool_id)}"
    
    @property
    def _get_descr(self) -> str:
        return f"{self.name}_v{self.v_maj}_{self.v_min}_{self.v_build}"
    
    @property
    def _get_build_path(self) -> str:
        return f"{Defines.DIR_BUILD}/{self._get_descr}"
    
    @property
    def rows(self):
        for idx, row in self.df.iterrows():
            yield idx, row
    
    @property
    def pools(self):
        return self.df[Defines.DF_POOL].unique()
    
    def _get_tags(self, row) -> list[str]:
        pool = row[Defines.DF_POOL]
        pool_id = row[Defines.DF_POOL_ID]
        tags_file = self._get_tag_file(pool, pool_id)
        try:
            with open(tags_file) as f:
                tags = f.readline()
        except FileNotFoundError:
            print(f"no tags file for {pool}/{pool_id}: {tags_file}")
            return []
        return tags.split(", ") 
    
    def _get_tag_file(self, pool: str, pool_id: str):
        return f"{self._get_build_path}/{Defines.DIR_TAGS}/{self._get_pool_dir(pool)}/{self._get_pool_id_tag_file(pool_id)}"
    

    def _get_caps(self, row) -> list[str]:
        caps = [Defaults.TRIGGER, Defaults.CLASS, Defaults.CELEB, Defaults.CROPPED]
        tags = row[Defines.DF_TAG_WD14]
        for tag in tags:
            cap = self._tag2cap(tag)
            if cap:
                caps.append(cap)
        return caps

    def _get_cap_file(self, pool: str, pool_id: str):
        return f"{self._get_build_path}/{self._get_pool_dir(pool)}/{self._get_pool_id_cap_file(pool_id)}"
    
    def _tag2cap(self, tag : str) -> str:
        tag = tag.strip()

        cap = ""
        tag_split = tag.split(" ")
        
        # remove color prefix
        if len(tag_split) > 1:
            if tag_split[0] in Defaults.CAP_NEG_COLOR:
                tag = tag_split[1]
        
        for subtag in tag_split:
            if subtag in Defaults.CAP_NEG:
                return cap
            if subtag in Defines.DF_CAP_NEG:
                return cap
        
        for key in Defaults.CAP_NEG_KEY:
            if key in tag:
                return cap
        
        cap = tag

        return cap

    """
    API
    """
    def reload_tags(self) -> None:
        for idx, row in self.rows:
            tags = self._get_tags(row)
            self.df.at[idx, Defines.DF_TAG_WD14] = tags
    
    def create_captions(self) -> None:
        for idx, row in self.rows:
            caps = self._get_caps(row)
            self.df.at[idx, Defines.DF_CAP] = caps
    
    def save_captions(self) -> None:
        for idx, row in self.rows:
            pool = row[Defines.DF_POOL]
            pool_id = row[Defines.DF_POOL_ID]
            caps = row[Defines.DF_CAP]
            caps_file = self._get_cap_file(pool, pool_id)
            caps_str = f"{caps[0]}"
            for cap in caps[1:]:
                caps_str += f", {cap}"
            with open(caps_file, "w") as text_file:
                text_file.write(caps_str)
    
    def create_dataset(self, pools=[]) -> None:
        _pools = []
        for pool in self.pools:
            if not pools:
                _pools.append(pool)
            elif pool in pools:
                _pools.append(pool)
        tar_file = f"{self._get_build_path}/loraset.tar"
        try:
            os.remove(tar_file)
        except OSError:
            pass

        with tarfile.open(tar_file, "a") as tf:
            for pool in pools:
                pool_dir = self._get_pool_dir(pool)
                tf.add(pool_dir)

    @property
    def caps_all(self):
        caps = []
        for idx, row in self.rows:
            caps += row[Defines.DF_CAP]
        return caps
    
    @property
    def caps_hist(self) -> pd.DataFrame:
        caps_all = self.caps_all
        caps_unique = np.unique(caps_all)
        caps_ser = pd.Series(np.array(caps_all))
        return caps_ser.value_counts(ascending=True)
        
        