
from enum import Enum, auto
from glob import glob
import os
from random import random
from typing import Final

import macos_tags

from ..defines import Defines

class ImgSelectorMode(Enum):
    UseTags = auto()
    IngoreTags = auto()

class ImgSelectorCategory():
    NONE: Final = ""
    Orig: Final = "origs"
    Face: Final = "faces"

class ImgSelector:
    TagPrefix : Final = "ai_"
    TagOk : Final = f"{TagPrefix}ok"
    TagNok : Final = f"{TagPrefix}not"
    TagBody : Final = f"{TagPrefix}body"
    TagFace : Final = f"{TagPrefix}face"

    def __init__(self, url_crawl: str, category: ImgSelectorCategory, num_img: int, mode: ImgSelectorMode) -> None:
        self.url_crawl = url_crawl
        self.category = category
        self.num_img = num_img
        self.mode = mode
        
        self.url_src_folders = []
        self.url_img_selected = []
    
    @property
    def result(self) -> list[str]:
        all = [glob(f"{dir}/*.{Defines.TypeImgSource}") for dir in self._url_src_folders]
        url_img_pooled = [x for xs in all for x in xs] # flattened list
        url_img_selected = []
        #split pool by tags
        for url_img in url_img_pooled:
            if self._url_img_select_by_tag(url_img):
                url_img_selected.append(url_img)
        
        # select from pooled with remaining propability
        prob = (self.num_img - len(url_img_selected)) / len(url_img_pooled)
        return url_img_selected + [url_img for url_img in url_img_pooled
            if prob > random()]
        
    @property
    def _url_src_folders(self) -> list[str]:
        ret = os.listdir(self.url_crawl)
        # filter dot folders
        ret = [dir for dir in ret
               if dir[0] != '.']
        # make paths absolute
        ret = [os.path.join(self.url_crawl, dir) for dir in ret]
        # filter by tags
        if ImgSelectorMode.UseTags == self.mode:
            for dir in ret:
                tags = macos_tags.get_all(dir)
                b = ImgSelector.TagNok in tags
            ret = [dir for dir in ret
                if ImgSelector.TagNok not in ImgSelector._tags_url(dir)]

        return [self.url_crawl] + ret # also use imgs which are not in s subfolder
    
    """
    HELPERS
    """
    @staticmethod
    def _tags_url(url: str) -> list[str]:
        tags = macos_tags.get_all(url)
        return [tag.name for tag in tags]
    
    def _url_img_select_by_tag(self, url: str):
        if ImgSelectorMode.IngoreTags == self.mode:
            return True
        if ImgSelectorCategory.NONE == self.category:
                return True
        if ImgSelectorCategory.Orig == self.category:
            if ImgSelector.TagBody in self._tags_url(url):
                return True
        if ImgSelectorCategory.Face == self.category:
            if ImgSelector.TagFace in self._tags_url(url):
                return True
        return False
        