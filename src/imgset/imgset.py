import os
from pathlib import Path
from typing import Final
import pandas as pd
from PIL import Image


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
                Defines.DF_FILE_CRAWL: "",
                Defines.DF_POOL: pool,
                Defines.DF_POOL_ID: pool_id,
                Defines.DF_FILE_IMG: self._get_img_file(pool, pool_id),
                Defines.DF_TAG_BLIP: [],
                Defines.DF_TAG_WD14: [],
            })
        self.df = pd.DataFrame(df_data, columns=Defines.DF_COLUMNS)

    def _initialize_new(self):
        paths = []
        dirs = [dir[0] for dir in os.walk(self.path_crawl)]
        for dir in dirs:
            path = Path(dir)
            paths += list(set(path.glob("*.jpg")))
        
        df_data = []
        for file_crawl in paths:
            df_data.append({
                Defines.DF_FILE_CRAWL: file_crawl,
                Defines.DF_POOL: "",
                Defines.DF_POOL_ID: "",
                Defines.DF_FILE_IMG: "",
                Defines.DF_TAG_BLIP: [],
                Defines.DF_TAG_WD14: [],
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
    
    def _get_pool_id_file(self, pool_id: str) -> str:
        return f"{pool_id}.png"
    
    def _get_img_file(self, pool: str, pool_id: str) -> str:
        return f"{self._get_build_path}/{self._get_pool_dir(pool)}/{self._get_pool_id_file(pool_id)}"
    
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