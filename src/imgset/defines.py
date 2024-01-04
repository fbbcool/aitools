from typing import Final

class Defaults():
    NAME = "lara"
    CELEB : Final = "rakhee thakar"
    CLASS : Final = "woman"
    V_MINOR : Final = 1
    V_MAJOR : Final = 0
    V_BUILD : Final = 1
    STEPS : Final = 20

class Defines():
    DF_FILE_IMG : Final = "file_img"
    DF_FILE_CRAWL : Final = "file_crawl"
    DF_POOL : Final = "pool"
    DF_POOL_ID : Final = "pool_id"
    DF_TAG_BLIP : Final = "tag_blip"
    DF_TAG_WD14 : Final = "tag_wd14"
    DF_COLUMNS : Final = [
        DF_FILE_IMG,
        DF_POOL_ID,
        DF_POOL,
        DF_TAG_BLIP,
        DF_TAG_WD14,
        DF_FILE_CRAWL,
    ]
    DIR_BUILD : Final = "build"