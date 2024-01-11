import os
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

class ImgSet:
    def __init__(self,
                 pool_name: str,
                 dir: str = "",
                 count: int = 0,
                 ) -> None:
        self.pool_name = pool_name

        if dir:
            if not os.path.isdir(dir):
                raise FileNotFoundError(f"Directory {dir} not found!")
            self._create_pool(dir, count)
    
    @classmethod
    def _facecrop(cls, _from, width, height, ratio=1.0):
        image = face_recognition.load_image_file(_from)
        face_locations = face_recognition.face_locations(
            image
        )
        if not face_locations:
            return None
        (top, right, bottom, left) = face_locations[0]
        w2 = float(right - left) / 2.0
        h2 = float(bottom - top) / 2.0
        cu = float(left) + w2
        cv = float(top) + h2
        left = int(cu - (w2 * ratio))
        right = int(cu + (w2 * ratio))
        top = int(cv - (h2 * ratio))
        bottom = int(cv + (h2 * ratio))

        if left < 0:
            left = 0
        if top < 0:
            top = 0
        if right > width:
            right = width
        if bottom > height:
            bottom = height
        
        return (left, top, right, bottom)

    
    @classmethod
    def _proc_img(cls, _from, _to, _to_faces):
        im = Image.open(_from)
        width, height = im.size
        bbox = cls._facecrop(_from, width, height, 1.3)
        if not bbox:
            return
        im_face = im.crop(bbox)
        
        im.save(_to)
        im_face.save(_to_faces)

    def _create_pool(self, crawl_dir:str, count: int) -> None:
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
        pool = -1

        list_convert = []
        for dir in dirs:
            path = Path(dir)
            imgs_source = list(set(path.glob(f"*.{Defines.TYPE_IMG_SOURCE}")))
            imgs_target = list(set(path.glob(f"*.{Defines.TYPE_IMG_TARGET}")))
            imgs = imgs_source + imgs_target
            if not imgs:
                continue

            pool += 1
            Path(self._url_pool(pool)).mkdir(parents=True, exist_ok=False)
            Path(self._url_pool_origs(pool)).mkdir(parents=False, exist_ok=False)
            Path(self._url_pool_tags(pool)).mkdir(parents=False, exist_ok=False)
            Path(self._url_pool_faces(pool)).mkdir(parents=False, exist_ok=False)

            for idx_img, img in enumerate(imgs):
                url_img = self._url_origs_id(pool, idx_img)
                url_face = self._url_faces_id(pool, idx_img)
                list_convert.append((img, url_img, url_face))
        
        prob_convert = float(count) / float(len(list_convert))
        print(f"convert prob = {prob_convert}")
        for item in list_convert:
            convert = False
            if count == 0:
                convert = True
            elif prob_convert > random.random():
                convert = True

            if convert:
                ImgSet._proc_img(item[0], item[1], item[2])
                #_, _file_type = os.path.splitext(item[-1])
                ##print(f"{item[0]},{_file_type} -> {item[1]}")
                #if _file_type != Defines.TYPE_IMG_TARGET:
                #    #print("would convert!")
                #if _file_type == Defines.TYPE_IMG_TARGET:
                #    shutil.copy2(item[0], item[1])
                #    #print("would copy!")

    """
    URLS
    """
    @property
    def _url_pools(self) -> str:
        return f"{Defines.DIR_POOLS}/{self.pool_name}"
    
    def _pool_id(self, pool_id: int, use_type: str) -> str:
        return f"{pool_id:04d}.{use_type}"
    def _url_pool(self, pool: int) -> str:
        return f"{self._url_pools}/{pool:02d}"
    
    def _url_pool_folder(self, pool: int, folder: str) -> str:
        return f"{self._url_pool(pool)}/{folder}"
    def _url_pool_origs(self, pool: int) -> str:
        return f"{self._url_pool_folder(pool, Defines.DIR_POOL_ORIG)}"
    def _url_pool_tags(self, pool: int) -> str:
        return f"{self._url_pool_folder(pool, Defines.DIR_POOL_TAGS)}"
    def _url_pool_faces(self, pool: int) -> str:
        return f"{self._url_pool_folder(pool, Defines.DIR_POOL_FACES)}"
    
    def _url_origs_id(self, pool: int, pool_id: int, use_type: str = Defines.TYPE_IMG_TARGET) -> str:
        return f"{self._url_pool_origs(pool)}/{self._pool_id(pool_id, use_type)}"
    def _url_tags_id(self, pool: int, pool_id: int, use_type: str = Defines.TYPE_CAP) -> str:
        return f"{self._url_pool_tags(pool)}/{self._pool_id(pool_id, use_type)}"
    def _url_faces_id(self, pool: int, pool_id: int, use_type: str = Defines.TYPE_IMG_TARGET) -> str:
        return f"{self._url_pool_faces(pool)}/{self._pool_id(pool_id, use_type)}"
    
    
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

    def _url_pool_id_list(self, pool: int) -> tuple[int, str]:
        for pool_id in range(Defines.MAX_POOL_IDS):
            url = self._url_origs_id(pool, pool_id)
            if not self._url_exit(url):
                break
            yield pool_id, url

    def _url_pool_id_tags_list(self, pool: int, use_type: str, ignore_exist=False) -> tuple[int, str]:
        for pool_id, _ in self._url_pool_id_list(pool):
            url_tags = self._url_tags_id(pool, pool_id, use_type=use_type)
            if not ignore_exist:
                if not self._url_exit(url_tags):
                    print(f"Warning: no tags found for {url_tags}")
                    continue
            yield pool_id, url_tags

    def _url_pool_id_faces_list(self, pool: int, ignore_exist=False) -> tuple[int, str]:
        for pool_id, _ in self._url_pool_id_list(pool):
            url_tags = self._url_tags_id(pool, pool_id)
            if not ignore_exist:
                if not self._url_exit(url_tags):
                    print(f"Warning: no tags found for {url_tags}")
                    continue
            yield pool_id, url_tags

    """
    tags
    """
    def tags_init(self, caps_init: list[str], type_tags: str):
        if Defines.TYPE_CAP not in type_tags:
            print(f"Warning: no tags initialized because of unvalid tags extension given: {type_tags}!")
            return
        if not caps_init:
            return
        
        for pool, _ in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=type_tags, ignore_exist=True):
                tags_str = f"{caps_init[0]}"
                for tag in caps_init[1:]:
                    tags_str += f", {tag}"
                with open(url_pool_id_tags, "w") as text_file:
                    text_file.write(tags_str)

    def tags_copy(self, from_type: str, to_type: str):
        if Defines.TYPE_CAP not in from_type:
            print(f"Warning: no tags copied because of unvalid tags extension given: {from_type}!")
            return
        if Defines.TYPE_CAP not in to_type:
            print(f"Warning: no tags copied because of unvalid tags extension given: {to_type}!")
            return
        for pool, _ in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=from_type):
                shutil.copy(url_pool_id_tags, self._url_change_type(url_pool_id_tags, to_type))
    
    def tags_remove(self, type_tags: str):
        if Defines.TYPE_CAP not in type_tags:
            print(f"Warning: no tags removed because of unvalid tags extension given: {type_tags}!")
            return
        for pool, _ in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=type_tags):
                os.remove(url_pool_id_tags)
    

    def tags_link(self, type_tags: str):
        if Defines.TYPE_CAP not in type_tags:
            print(f"Warning: no tags linked because of unvalid tags extension given: {type_tags}!")
            return
        for pool, url_pool in self._url_pool_list:
            for _, url_pool_id_tags in self._url_pool_id_tags_list(pool, use_type=type_tags):
                shutil.copy(url_pool_id_tags, url_pool)


    def tags_link_save(self, type_tags: str):
        if Defines.TYPE_CAP not in type_tags:
            print(f"Warning: no tags linked because of unvalid tags extension given: {type_tags}!")
            return
        for pool, _ in self._url_pool_list:
            url_pool_tags = self._url_pool_tags(pool)
            for _, url in self._url_pool_id_list(pool, use_type=type_tags):
                shutil.copy(url, url_pool_tags)


    def tags_unlink(self, type_tags: str):
        if Defines.TYPE_CAP not in type_tags:
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
    def _tags_to_caps(self, pool: int, pool_id: int, use_type: str = Defines.TYPE_CAP) -> list[str]:
        url = self._url_tags_id(pool, pool_id, use_type = use_type)
        try:
            with open(url) as f:
                caps = f.readline()
        except FileNotFoundError:
            print(f"Warning: no tags file {url} found.")
            return []
        return caps.split(",") 

    def _caps_to_tags(self, _list: list[str], pool: int, pool_id: int, use_type: str = Defines.TYPE_CAP) -> None:
        tags_str = []
        for tag in _list:
            tags_str += f",{tag}"
        tags_str = tags_str[1:]
        
        url = self._url_tags_id(pool, pool_id, use_type = use_type)
        try:
            with open(url,'w') as f:
                    f.write(tags_str)
        except:
            print(f"Warning: write tags {url} failed.")

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
                if item.endswith(Defines.TYPE_IMG_TARGET):
                    continue
                os.remove(os.path.join(url_pool, item))
        

    """
    API
    """
    def build(self, use_pools : list[int], use_type : str, profile: TagsProfile, num_steps : int, perc : float = 1.0) -> None:
        dir_train_pool = f"{Defines.DIR_TRAINS}/{self.pool_name}"
        if os.path.isdir(dir_train_pool):
            yes = input(f"Really want to delete {dir_train_pool} [y/n]? ")
            if yes not in ["y"]:
                return
            shutil.rmtree(dir_train_pool, ignore_errors=False)
        Path(dir_train_pool).mkdir(parents=True, exist_ok=True)

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
                pool_dir = f"{dir_train_pool}/{num_steps:02d}_{pool:02d}"
                Path(pool_dir).mkdir(parents=True, exist_ok=True)
                # copy all images and write tags from pool
                for pool_id, url_pool_id in self._url_pool_id_list(pool):
                    sum_count += 1
                    # process procinfo
                    procinfo = self._tags_to_caps(pool, pool_id, use_type=Defines.TYPE_CAP_PROCINFO)
                    if Defines.SKIP in procinfo:
                        #print(f"Info: skipping due to procinfo {self.pool_name}/{pool:02d}/{pool_id:04d}")
                        continue
                    # chance to skip
                    rand = random.random()
                    if perc < rand:
                        #print(f"Info: skipping due to random({rand} > {perc}) {self.pool_name}/{pool:02d}/{pool_id:04d}")
                        continue

                    img_count += 1
                    # copy img
                    img_link = f"{pool_dir}/{pool_id:04d}.{Defines.TYPE_IMG_TARGET}"
                    os.symlink(os.path.abspath(url_pool_id), os.path.abspath(img_link))
                    # write tags
                    caps_cropped = self._tags_to_caps(pool, pool_id, use_type=Defines.TYPE_CAP_CROPPED)
                    caps = self._tags_to_caps(pool, pool_id, use_type)
                    caps = caps_cropped + caps
                    caps = build_caps(caps, profile)
                    tags_str = ""
                    for cap in caps:
                        tags_str += f",{cap}"
                    tags_str = tags_str[1:]
                    tags_file = f"{pool_dir}/{pool_id:04d}.{Defines.TYPE_CAP}"
                    try:
                        with open(tags_file,'w') as f:
                                f.write(tags_str)
                    except:
                        print(f"Warning: write tags {tags_file} failed.")

        # tar output pool structure
        print(f"Info: build done with {img_count}/{sum_count} imgs ({img_count / sum_count * 100.0}%)")

    # depr
    @property
    def caps_hist(self) -> pd.DataFrame:
        caps_all = self.caps_all
        caps_unique = np.unique(caps_all)
        caps_ser = pd.Series(np.array(caps_all))
        return caps_ser.value_counts(ascending=True)
        
        