import os
from pathlib import Path
from typing import Final
import numpy as np
import pandas as pd
from PIL import Image
import tarfile
import shutil
import subprocess
import random


from .defines import Defaults, Defines
from ..tags import Tags

class ImgSet:
    def __init__(self,
                 pool_name: str,
                 dir: str = "",
                 init_tags: bool = False,
                 ) -> None:
        self.pool_name = pool_name

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
                for _, url in self._url_pool_id_list(pool, use_type=Defines.EXT_WD14):
                    shutil.move(url, url_pool_tags)
    
    @classmethod
    def _convert2png(cls, _from, _to):
        image = Image.open(_from)
        image = image.convert('RGB')
        image.save(_to)

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
    
    def _url_pool_id_tags(self, pool: int, pool_id: int, use_type: str = Defines.EXT) -> str:
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
        if Defines.EXT not in type_tags:
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
        if Defines.EXT not in from_type:
            print(f"Warning: no tags copied because of unvalid tags extension given: {from_type}!")
            return
        if Defines.EXT not in to_type:
            print(f"Warning: no tags copied because of unvalid tags extension given: {to_type}!")
            return
        for pool, _ in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=from_type):
                shutil.copy(url_pool_id_tags, self._url_change_type(url_pool_id_tags, to_type))
    
    def tags_remove(self, type_tags: str):
        if Defines.EXT not in type_tags:
            print(f"Warning: no tags removed because of unvalid tags extension given: {type_tags}!")
            return
        for pool, _ in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=type_tags):
                os.remove(url_pool_id_tags)
    

    def tags_link(self, type_tags: str):
        if Defines.EXT not in type_tags:
            print(f"Warning: no tags linked because of unvalid tags extension given: {type_tags}!")
            return
        for pool, url_pool in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=type_tags):
                shutil.copy(url_pool_id_tags, url_pool)


    def tags_link_save(self, type_tags: str):
        if Defines.EXT not in type_tags:
            print(f"Warning: no tags linked because of unvalid tags extension given: {type_tags}!")
            return
        for pool, _ in self._url_pool_list:
            url_pool_tags = self._url_pool_tags(pool)
            for _, url in self._url_pool_id_list(pool, use_type=type_tags):
                shutil.copy(url, url_pool_tags)


    def tags_unlink(self, type_tags: str):
        if Defines.EXT not in type_tags:
            print(f"Warning: no tags unlinked because of unvalid tags extension given: {type_tags}!")
            return
        
        for _, url_pool in self._url_pool_list:
            ls = os.listdir(url_pool)
            for item in ls:
                if item.endswith(f".{type_tags}"):
                    #print(f"will delete {os.path.join(url_pool, item)}")
                    os.remove(os.path.join(url_pool, item))
    
    """
    caps
    """
    def _tags_to_caps(self, pool: int, pool_id: int, use_type: str = Defines.EXT) -> list[str]:
        url = self._url_pool_id_tags(pool, pool_id, use_type = use_type)
        try:
            with open(url) as f:
                caps = f.readline()
        except FileNotFoundError:
            print(f"Warning: no tags file {url} found.")
            return []
        return caps.split(",") 

    def _caps_to_tags(self, _list: list[str], pool: int, pool_id: int, use_type: str = Defines.EXT) -> None:
        tags_str = []
        for tag in _list:
            tags_str += f",{tag}"
        tags_str = tags_str[1:]
        
        url = self._url_pool_id_tags(pool, pool_id, use_type = use_type)
        try:
            with open(url,'w') as f:
                    f.write(tags_str)
        except:
            print(f"Warning: write tags {url} failed.")

    def _caps_clean(self, caps: list[str]) -> list[str]:
        caps_clean = []
        for cap in caps:
            clean = True
            for sub_cab in cap.strip().split(" "):
                for del_tag in Tags.DEL:
                    if del_tag in sub_cab:
                        clean = False
            if clean:
                caps_clean.append(cap)
        return caps_clean

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
    API
    """
    def build(self, use_pools : list[int], use_type : str, num_steps : int, perc : float = 1.0) -> None:
        if os.path.isdir(Defines.DIR_TMP):
            yes = input(f"Really want to delete {Defines.DIR_TMP} [y/n]? ")
            if yes not in ["y"]:
                return
            shutil.rmtree(Defines.DIR_TMP, ignore_errors=False)
        dir_root = f"{Defines.DIR_TMP}/{self.pool_name}"
        Path(dir_root).mkdir(parents=True, exist_ok=True)

        # build output pool structure
        img_count = 0
        sum_count = 0
        for pool, _ in self._url_pool_list:
            select_pool = False
            if not use_pools: # empty list selects all pools
                select_pool = True
            if pool in use_pools:
                select_pool = True
            
            if select_pool:
                # build pool
                pool_dir = f"{dir_root}/{num_steps:02d}_{pool:02d}"
                Path(pool_dir).mkdir(parents=True, exist_ok=True)
                # copy all images and write tags from pool
                for pool_id, url_pool_id in self._url_pool_id_list(pool):
                    sum_count += 1
                    # process procinfo
                    procinfo = self._tags_to_caps(pool, pool_id, use_type=Defines.EXT_PROCINFO)
                    if Tags.SKIP in procinfo:
                        #print(f"Info: skipping due to procinfo {self.pool_name}/{pool:02d}/{pool_id:04d}")
                        continue
                    # chance to skip
                    rand = random.random()
                    if perc < rand:
                        #print(f"Info: skipping due to random({rand} > {perc}) {self.pool_name}/{pool:02d}/{pool_id:04d}")
                        continue

                    img_count += 1
                    # copy img
                    shutil.copy(url_pool_id, pool_dir)
                    # write tags
                    caps_cropped = self._tags_to_caps(pool, pool_id, use_type=Defines.EXT_CROPPED)
                    caps = self._tags_to_caps(pool, pool_id, use_type)
                    caps = self._caps_clean(caps)
                    caps = Tags.HEADER + caps_cropped + caps + Tags.FOOTER
                    tags_str = ""
                    for cap in caps:
                        tags_str += f",{cap}"
                    tags_str = tags_str[1:]
                    tags_file = f"{pool_dir}/{pool_id:04d}.{Defines.EXT}"
                    try:
                        with open(tags_file,'w') as f:
                                f.write(tags_str)
                    except:
                        print(f"Warning: write tags {tags_file} failed.")

        # tar output pool structure
        print(f"Info: build done with {img_count}/{sum_count} imgs ({img_count / sum_count * 100.0}%)")
        tar_file = f"{Defines.DIR_TMP}/{self.pool_name}_imgset_{int(perc*100.0):03d}_{num_steps:02d}.tar"
        with tarfile.open(tar_file, "a") as tf:
            tf.add(dir_root)


    # depr
    @property
    def caps_hist(self) -> pd.DataFrame:
        caps_all = self.caps_all
        caps_unique = np.unique(caps_all)
        caps_ser = pd.Series(np.array(caps_all))
        return caps_ser.value_counts(ascending=True)
        
        