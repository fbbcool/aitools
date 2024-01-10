from typing import Final

class Defines():
    DIR_BUILD : Final = "build"
    DIR_TMP : Final = f"{DIR_BUILD}/tmp"
    DIR_POOLS : Final = f"{DIR_BUILD}/pools"
    DIR_TAGS : Final = "_tags"
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