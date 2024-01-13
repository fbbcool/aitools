import os
import glob
from pathlib import Path
from typing import Final, Generator
import numpy as np
import pandas as pd
import shutil
import random
from PIL import Image
import imageio as iio

from .img_select import ImgSelector, ImgSelectorCategory, ImgSelectorMode
from ..defines import Defines, Helpers
from ..tags import Tags, write_tags, TagsProfile

class ImgPool:
    def __init__(self,
                 pool_name: str,
                 num_img: int,
                 mode: ImgSelectorMode = ImgSelectorMode.IngoreTags,
                 url_crawl: str = "",
                 ) -> None:
        self.pool_name = f"{pool_name}_{num_img}"
        self.num_img = num_img
        self.mode = mode

        if url_crawl:
            if not os.path.isdir(url_crawl):
                raise FileNotFoundError(f"Directory {url_crawl} not found!")
            self._create_pool(url_crawl)
    
    @classmethod
    def _facecrop(cls, _from, width, height, ratio=1.0):
        import face_recognition
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
    def _proc_img(cls, _from: str, _to: str):
        im = Image.open(_from)
        im.save(_to)

    @classmethod
    def _proc_face(cls, _from: str, _to: str):
        im = Image.open(_from)
        width, height = im.size
        bbox = cls._facecrop(_from, width, height, 1.3)
        if not bbox:
            return
        im_face = im.crop(bbox)
        im_face.save(_to)

    def _create_pool(self, url_crawl: str) -> None:
        # recreate pools dir
        if os.path.isdir(self.url_pool):
            yes = input(f"Really want to delete {self.url_pool} [y/n]? ")
            if yes not in ["y"]:
                return
            shutil.rmtree(self.url_pool, ignore_errors=False)
        Path(self.url_pool).mkdir(parents=True, exist_ok=True)

        for id, url_src in enumerate(ImgSelector(url_crawl, ImgSelectorCategory.Orig, self.num_img, self.mode).result):
            url_orig = self.url_orig_id(id)
            self._proc_img(url_src, url_orig)
        for id, url_src in enumerate(ImgSelector(url_crawl, ImgSelectorCategory.Face, self.num_img, self.mode).result):
            url_orig = self.url_orig_id(id)
            self._proc_face(url_src, url_orig)


    """
    URLS
    """
    @property
    def url_pool(self) -> str:
        return f"{Defines.DirPools}/{self.pool_name}"
    @property
    def url_origs(self) -> str:
        return self._url_category(ImgSelectorCategory.Orig)
    @property
    def url_faces(self) -> str:
        return self._url_category(ImgSelectorCategory.Face)
    
    def url_orig_id(self, id: int) -> str:
        return self._url_id(id, ImgSelectorCategory.Orig, Defines.TypeImgTarget)
    def url_face_id(self, id: int) -> str:
        return self._url_id(id, ImgSelectorCategory.Face, Defines.TypeImgTarget)
    
    def url_orig_id_tag(self, id: int, use_type: str) -> str:
        return self._url_id_tag(id, ImgSelectorCategory.Orig, use_type)
    def url_face_id_tag(self, id: int, use_type: str) -> str:
        return self._url_id_tag(id, ImgSelectorCategory.Face, use_type)
    
    #  url helpers
    def _url_category(self, category: ImgSelectorCategory) -> str:
        return f"{self.url_pool}/{category}"
    def _url_id(self, id: int, category: ImgSelectorCategory, use_type: str):
        return f"{self._url_category(category)}/{id:04d}.{use_type}"
    def _url_id_tag(self, id: int, category: ImgSelectorCategory, use_type: str) -> str:
        Helpers.caption_check_type(use_type)
        return self._url_id(id, category, use_type)
    
    """
    LISTS
    """
    @property
    def url_orig_ids(self) -> Generator:
        for id in range(Defines.MaxIds):
            url = self.url_orig_id(id)
            if not Helpers.url_exit(url):
                continue
            yield url
    @property
    def url_face_ids(self) -> Generator:
        for id in range(Defines.MaxIds):
            url = self.url_face_id(id)
            if not Helpers.url_exit(url):
                continue
            yield url
    
    def url_orig_ids_tag(self, use_type: str) -> Generator:
        Helpers.caption_check_type(use_type)
        for url_orig_id in self.url_orig_ids:
            yield Helpers.url_change_type(url_orig_id, use_type)
    def url_face_ids_tag(self, use_type: str) -> Generator:
        Helpers.caption_check_type(use_type)
        for url_orig_id in self.url_face_ids:
            yield Helpers.url_change_type(url_orig_id, use_type)

    """
    API
    """
    def make_train(self, categories: list[ImgSelectorCategory], profile: TagsProfile, num_steps : int, perc : float = 1.1) -> None:

        url_train = f"{Defines.DirTrains}/{self.pool_name}"
        if os.path.isdir(url_train):
            yes = input(f"Really want to delete {url_train} [y/n]? ")
            if yes not in ["y"]:
                return
            shutil.rmtree(url_train, ignore_errors=False)
        Path(url_train).mkdir(parents=True, exist_ok=True)

        for category in categories:
            url_category = self._url_category(category)
            url_train_category = f"{url_train}/{num_steps}_{category}"
            Path(url_train_category).mkdir(parents=False, exist_ok=False)
            url_imgs = ImgSelector(
                url_category,
                ImgSelectorCategory.NONE,
                perc * len(url_category),
                ImgSelectorMode.IngoreTags,
                ).result
            for url_img in url_imgs:
                filename_img, _ = os.path.split(url_img)
                url_img_train = f"{url_train_category}/{filename_img}"
                # only symlink imgages
                os.symlink(os.path.abspath(url_img), os.path.abspath(url_img_train))
                # TODO
                write_tags(url_img, profile)



            #


        # build output pool structure
        selected_abs = 0
        count_abs = 0
        for pool, _ in self._url_pool_list:
            select_pool = False
            if not use_pools: # empty list selects all pools
                select_pool = True
            if pool in use_pools:
                select_pool = True
            
            if select_pool:
                # build pool
                for folder in folders:
                    src_dir = f"{self.url_pool(pool)}/{folder}"
                    dst_dir = f"{url_train}/{folder}/{num_steps:02d}_{pool:02d}"
                    (selected, count) = self._build_train_pool(src_dir, dst_dir, use_type, profile,perc)
                    selected_abs += selected
                    count_abs += count

        print(f"Info: build done with {selected_abs}/{count_abs} imgs ({selected_abs / count_abs * 100.0}%)")

    def _build_train_pool(self, src_dir: str, dst_dir: str, use_type: str, profile: TagsProfile, perc: float = 1.1) -> tuple[int, int]:
        Path(dst_dir).mkdir(parents=True, exist_ok=True)
        url_img_list = glob.glob(f"{src_dir}/*.{Defines.TYPE_IMG_TARGET}")
        count = len(url_img_list)
        selected = 0
        # copy all images and write tags from pool
        for url_img in url_img_list:
            # process procinfo
            procinfo = self._tags_to_caps(ImgPool.url_change_type(url_img, Defines.TYPE_CAP_PROCINFO))
            if Defines.SKIP in procinfo:
                #print(f"Info: skipping due to procinfo {self.pool_name}/{pool:02d}/{pool_id:04d}")
                continue
            # chance to skip
            rand = random.random()
            if perc < rand:
                #print(f"Info: skipping due to random({rand} > {perc}) {self.pool_name}/{pool:02d}/{pool_id:04d}")
                continue

            selected += 1
            # copy img
            _, filename = os.path.split(url_img)
            img_link = f"{dst_dir}/{filename}"
            os.symlink(os.path.abspath(url_img), os.path.abspath(img_link))
            # write tags
            caps_cropped = self._tags_to_caps(ImgPool.url_change_type(url_img, Defines.TYPE_CAP_CROPPED))
            caps = self._tags_to_caps(ImgPool.url_change_type(url_img, use_type))
            caps = caps_cropped + caps
            caps = build_caps(caps, profile)
            tags_str = ""
            for cap in caps:
                tags_str += f",{cap}"
            tags_str = tags_str[1:]
            tags_file = f"{dst_dir}/{ImgPool.url_change_type(filename, Defines.TypeCap)}"
            try:
                with open(tags_file,'w') as f:
                        f.write(tags_str)
            except:
                print(f"Warning: write tags {tags_file} failed.")
        return (selected, count)

    # depr
    @property
    def caps_hist(self) -> pd.DataFrame:
        caps_all = self.caps_all
        caps_unique = np.unique(caps_all)
        caps_ser = pd.Series(np.array(caps_all))
        return caps_ser.value_counts(ascending=True)
        
        