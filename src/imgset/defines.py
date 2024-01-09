from typing import Final

class Defines():
    DF_POOL : Final = "pool"
    DF_POOL_ID : Final = "pool_id"
    DF_TAGS : Final = "tags"
    DF_TAGS_NEG : Final = "tags_neg"
    DF_COUNT : Final = "count"
    DF_COLUMNS : Final = [
        DF_POOL,
        DF_POOL_ID,
        DF_TAGS,
        DF_TAGS_NEG,
    ]
    DF_COLUMNS_CAP_HIST : Final = [
        DF_COUNT,
        DF_TAGS,
    ]
    DIR_BUILD : Final = "build"
    DIR_TMP : Final = f"{DIR_BUILD}/tmp"
    DIR_POOLS : Final = f"{DIR_BUILD}/pools"
    DIR_TAGS : Final = "_tags"
    TYPE_TAGS : Final = "caption"
    TYPE_TAGS_WD14 = f"{TYPE_TAGS}_wd14"
    TYPE_TAGS_BLIP = f"{TYPE_TAGS}_blip"
    TYPE_TAGS_CROPPED = f"{TYPE_TAGS}_cropped"
    TYPE_TAGS_PROCINFO = f"{TYPE_TAGS}_procinfo"
    IMG_TARGET_FORMAT : Final = "png"
    IMG_SOURCE_FORMAT : Final = "jpg"
    SCRIPT_TAGS : Final = "src/script/cap.sh"
    MAX_POOLS : Final = 20
    MAX_POOL_IDS : Final = 2000


class Defaults():
    NAME : Final = "lara"
    POOL_NAME : Final = NAME
    TRIGGER : Final = f"x{NAME}"
    V_MINOR : Final = 1
    V_MAJOR : Final = 0
    V_BUILD : Final = 1
    STEPS : Final = 20