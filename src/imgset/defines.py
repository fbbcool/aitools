from typing import Final

class Defines():
    DIR_BUILD : Final = "build"
    DIR_TMP : Final = f"{DIR_BUILD}/tmp"
    DIR_POOLS : Final = f"{DIR_BUILD}/pools"
    DIR_TRAINS : Final = f"{DIR_BUILD}/trains"
    DIR_POOL_ORIGS : Final = "origs"
    DIR_POOL_TAGS : Final = DIR_POOL_ORIGS
    DIR_POOL_FACES : Final = "faces"
    
    TYPE_IMG_TARGET : Final = "png"
    TYPE_IMG_SOURCE : Final = "jpg"
    TYPE_CAP : Final = "caption"
    TYPE_CAP_WD14 : Final = f"{TYPE_CAP}_wd14"
    TYPE_CAP_BLIP : Final = f"{TYPE_CAP}_blip"
    TYPE_CAP_CROPPED : Final = f"{TYPE_CAP}_cropped"
    TYPE_CAP_PROCINFO : Final = f"{TYPE_CAP}_procinfo"
    
    CROPPED : Final = "cropped"
    SKIP : Final = "skip it"
    PROCINFO = [SKIP,]

    MAX_POOLS : Final = 20
    MAX_POOL_IDS : Final = 2000