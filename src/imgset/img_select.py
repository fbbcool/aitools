
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
        if not url_img_pooled:
            return []

        url_img_selected = []
        url_img_later_use = []
        #split pool by tags
        for url_img in url_img_pooled:
            (selected, later_use) = self._url_img_select_by_tag(url_img)
            if selected:
                url_img_selected.append(url_img)
            if later_use:
                url_img_later_use.append(url_img)
        
        # select from pooled with remaining propability
        if not url_img_later_use:
            return url_img_selected
        prob = (self.num_img - len(url_img_selected)) / len(url_img_later_use)
        print(prob)
        return url_img_selected + [url_img for url_img in url_img_later_use
            if prob > random()]
        
    @property
    def _url_src_folders(self) -> list[str]:
        url_srcs = os.listdir(self.url_crawl)
        # filter dot folders
        url_srcs = [dir for dir in url_srcs
               if dir[0] != '.']
        # make paths absolute
        url_srcs = [os.path.join(self.url_crawl, dir) for dir in url_srcs]
        url_srcs =[self.url_crawl] + url_srcs # also use imgs which are not in a subfolder
        # filter by tags
        if ImgSelectorMode.UseTags == self.mode:
            ret = [url for url in url_srcs
                if self._url_select_by_tag(url)
                if ImgSelector.TagNok not in ImgSelector._tags_url(url)]
        elif ImgSelectorMode.IngoreTags == self.mode:
            ret = url_srcs
        elif True:
            ret = []
        return ret
    
    """
    HELPERS
    """
    @staticmethod
    def _tags_url(url: str) -> list[str]:
        tags = macos_tags.get_all(url)
        return [tag.name for tag in tags]
    
    def _url_select_by_tag(self, url: str) -> bool:
        tags_os = self._tags_url(url)
        if ImgSelector.TagNok in tags_os:
            return False
        if ImgSelectorMode.UseTags == self.mode:
            if ImgSelector.TagOk not in tags_os:
                return False
        return True
        
    def _url_img_select_by_tag(self, url: str) -> tuple[bool, bool]:
        """
        return (selected, later_use)
        """
        tags_os = self._tags_url(url)
        if ImgSelector.TagNok in tags_os:
            return (False, False)
        
        if ImgSelectorMode.IngoreTags == self.mode:
            return (False, True)
        if ImgSelectorMode.UseTags == self.mode:
            if ImgSelectorCategory.Orig == self.category:
                if ImgSelector.TagBody in tags_os:
                    return (True, False)
                elif True: # save for later use
                    return(False, True)
            if ImgSelectorCategory.Face == self.category:
                if ImgSelector.TagFace in tags_os:
                    return (True, False)
                elif True: # save for later use
                    return(False, True)
        
        return (False, True)
        