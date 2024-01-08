import os
from pathlib import Path
from typing import Final
import numpy as np
import pandas as pd
from PIL import Image
import tarfile
import shutil
import subprocess


from .defines import Defaults, Defines

class ImgSet:
    TEST_PATH_CRAWL : Final = "test/imgs"
    def __init__(self,
                 dir: str = "",
                 name:str = Defaults.NAME,
                 pool_name:str = Defaults.POOL_NAME,
                 celeb:str = Defaults.CELEB,
                 classobj:str = Defaults.CLASS,
                 steps:int = Defaults.STEPS,
                 v_maj:int = Defaults.V_MAJOR,
                 v_min:int = Defaults.V_MINOR,
                 v_build:int = Defaults.V_BUILD,
                 new_build: bool = False,
                 init_tags: bool = False,
                 ) -> None:
        self.name = name
        self.pool_name = pool_name
        self.celeb = celeb
        self.classobj = classobj
        self.steps = steps
        self.v_maj = v_maj
        self.v_min = v_min
        self.v_build = v_build

        self.df : pd.DataFrame


        if dir:
            if not os.path.isdir(dir):
                raise FileNotFoundError(f"Directory {dir} not found!")
            self._create_pool(dir)
        
        if init_tags:
            for pool, url_pool in self._url_pool_list:
                url_pool_abs = os.path.abspath(url_pool)
                print(f"tagging {url_pool}:")
                subprocess.call(['sh', os.path.abspath(Defines.SCRIPT_TAGS), url_pool_abs])
                
                url_pool_tags = self._url_pool_tags(pool)
                Path(url_pool_tags).mkdir(parents=True, exist_ok=True)
                print(f"moving tags to {url_pool_tags}:")
                for _, url in self._url_pool_id_list(pool, use_type=Defines.TYPE_TAGS_WD14):
                    shutil.move(url, url_pool_tags)

            #self._initialize_new()
        #elif True:
        #    if not os.path.isdir(self._get_build_path):
        #        raise FileNotFoundError(f"Build {self._get_build_path} not found!")
        #    self._initialize()

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
    
    @classmethod
    def _convert2png(cls, _from, _to):
        image = Image.open(_from)
        image = image.convert('RGB')
        image.save(_to)

    def _get_pool(self, row) -> tuple[str,str]:
        pool = Path(row[Defines.DF_FILE_CRAWL]).parts[-2]
        pool = pool.replace(" ", "_")
        pool = f"{self.steps}_{pool}"
        
        pool_id = Path(row[Defines.DF_FILE_CRAWL]).stem
        pool_id = pool_id.replace(" ", "_")
        
        return pool, pool_id
    
    def _create_pool(self, crawl_dir:str) -> None:
        if not os.path.isdir(crawl_dir):
            raise FileNotFoundError(f"Crawl directory {crawl_dir} not found!")
        # recreate pools dir
        url_pools = self._url_pools
        if os.path.isdir(url_pools):
            yes = input(f"Really want to delete {url_pools} [y/n]? ")
            if yes not in ["y"]:
                return
            shutil.rmtree(url_pools, ignore_errors=False)
        Path(url_pools).mkdir(parents=True, exist_ok=True)

        dirs = [dir[0] for dir in os.walk(crawl_dir)]
        idx_pool = -1

        for dir in dirs:
            path = Path(dir)
            imgs = list(set(path.glob(f"*.{Defines.IMG_SOURCE_FORMAT}")))
            if not imgs:
                continue

            idx_pool += 1
            url_pool = self._url_pool(idx_pool)
            Path(url_pool).mkdir(parents=False, exist_ok=False)

            for idx_img, img in enumerate(imgs):
                url_img = self._url_pool_id(idx_pool, idx_img)
                ImgSet._convert2png(img, url_img)


    def _load_pool(self):
        pass
    
    def _create_build_structure(self) -> None:
        while os.path.isdir(self._get_build_path):
            self.v_build += 1
        os.mkdir(self._get_build_path)
        for pool in self.pools:
            os.mkdir(f"{self._get_build_path}/{self._get_pool_dir(pool)}")

    """
    URLS
    """
    @property
    def _url_pools(self) -> str:
        return f"{Defines.DIR_POOLS}/{self.pool_name}"
    
    def _url_pool(self, pool: int) -> str:
        return f"{self._url_pools}/{pool:02d}"
    
    def _url_pool_id(self, pool: int, pool_id: int, use_type: str = Defines.IMG_TARGET_FORMAT) -> str:
        return f"{self._url_pool(pool)}/{pool_id:04d}.{use_type}"
    
    def _url_pool_tags(self, pool: int) -> str:
        return f"{self._url_pools}/{Defines.DIR_TAGS}/{pool:02d}"
    
    def _url_pool_id_tags(self, pool: int, pool_id: int, use_type: str = Defines.TYPE_TAGS) -> str:
        return f"{self._url_pool_tags(pool)}/{pool_id:04d}.{use_type}"
    
    def _url_exit(self, url: str) -> bool:
        return os.path.isfile(url) or os.path.isdir(url)
    
    def _url_change_type(self, url: str, to_type: str) -> str:
        return f"{os.path.splitext(url)[0]}.{to_type}"

    @property
    def _url_pool_list(self) -> tuple[int, str]:
        for pool in range(Defines.MAX_POOLS):
            url = self._url_pool(pool)
            if not self._url_exit(url):
                break
            yield pool, url

    def _url_pool_id_list(self, pool: int, use_type: str = Defines.IMG_TARGET_FORMAT) -> tuple[int, str]:
        for pool_id in range(Defines.MAX_POOL_IDS):
            url = self._url_pool_id(pool, pool_id, use_type=use_type)
            if not self._url_exit(url):
                break
            yield pool_id, url

    def _url_pool_id_tags_list(self, pool: int, use_type: str = Defines.IMG_TARGET_FORMAT, ignore_exist=False) -> tuple[int, str]:
        for pool_id, _ in self._url_pool_id_list(pool):
            url_tags = self._url_pool_id_tags(pool, pool_id, use_type=use_type)
            url_pool = self._url_pool_tags(pool)
            if not ignore_exist:
                if not self._url_exit(url_tags):
                    print(f"Warning: no tags found for {url_tags}")
                    continue
            yield pool_id, url_tags

    """
    tags
    """
    def tags_init(self, init_list: list[str], type_tags: str):
        if Defines.TYPE_TAGS not in type_tags:
            print(f"Warning: no tags initialized because of unvalid tags extension given: {type_tags}!")
            return
        if not init_list:
            return
        
        for pool, _ in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=type_tags, ignore_exist=True):
                tags_str = f"{init_list[0]}"
                for tag in init_list[1:]:
                    tags_str += f", {tag}"
                with open(url_pool_id_tags, "w") as text_file:
                    text_file.write(tags_str)

    def tags_copy(self, from_type: str, to_type: str):
        if Defines.TYPE_TAGS not in from_type:
            print(f"Warning: no tags copied because of unvalid tags extension given: {from_type}!")
            return
        if Defines.TYPE_TAGS not in to_type:
            print(f"Warning: no tags copied because of unvalid tags extension given: {to_type}!")
            return
        for pool, _ in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=from_type):
                shutil.copy(url_pool_id_tags, self._url_change_type(url_pool_id_tags, to_type))
    
    def tags_remove(self, type_tags: str):
        if Defines.TYPE_TAGS not in type_tags:
            print(f"Warning: no tags removed because of unvalid tags extension given: {type_tags}!")
            return
        for pool, _ in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=type_tags):
                os.remove(url_pool_id_tags)
    

    def tags_link(self, type_tags: str):
        if Defines.TYPE_TAGS not in type_tags:
            print(f"Warning: no tags linked because of unvalid tags extension given: {type_tags}!")
            return
        for pool, url_pool in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=type_tags):
                shutil.copy(url_pool_id_tags, url_pool)


    def tags_link_save(self, type_tags: str):
        if Defines.TYPE_TAGS not in type_tags:
            print(f"Warning: no tags linked because of unvalid tags extension given: {type_tags}!")
            return
        for pool, _ in self._url_pool_list:
            url_pool_tags = self._url_pool_tags(pool)
            for _, url in self._url_pool_id_list(pool, use_type=type_tags):
                shutil.copy(url, url_pool_tags)


    def tags_unlink(self, type_tags: str):
        if Defines.TYPE_TAGS not in type_tags:
            print(f"Warning: no tags unlinked because of unvalid tags extension given: {type_tags}!")
            return
        
        for _, url_pool in self._url_pool_list:
            ls = os.listdir(url_pool)
            for item in ls:
                if item.endswith(f".{type_tags}"):
                    #print(f"will delete {os.path.join(url_pool, item)}")
                    os.remove(os.path.join(url_pool, item))
    
    """
    pool
    """
    def pool_clean(self):
        """
        cleans everything from the pool image folders, except the images itself.
        """
        for _, url_pool in self._url_pool_list:
            ls = os.listdir(url_pool)
            for item in ls:
                if item.endswith(Defines.IMG_TARGET_FORMAT):
                    continue
                os.remove(os.path.join(url_pool, item))
        

    """
    """
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
        
        