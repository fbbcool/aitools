from typing import Final

class Defines():
    DF_FILE_IMG : Final = "file_img"
    DF_FILE_CRAWL : Final = "file_crawl"
    DF_POOL : Final = "pool"
    DF_POOL_ID : Final = "pool_id"
    DF_CAP : Final = "cap"
    DF_CAP_NEG : Final = "cap_neg"
    DF_TAG_BLIP : Final = "tag_blip"
    DF_TAG_WD14 : Final = "tag_wd14"
    DF_COUNT : Final = "count"
    DF_COLUMNS : Final = [
        DF_POOL,
        DF_POOL_ID,
        DF_CAP,
        DF_CAP_NEG,
        DF_TAG_WD14,
        DF_TAG_BLIP,
        DF_FILE_CRAWL,
        DF_FILE_IMG,
    ]
    DF_COLUMNS_CAP_HIST : Final = [
        DF_COUNT,
        DF_CAP,
    ]
    DIR_BUILD : Final = "build"
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
    CELEB : Final = "rakhee thakar"
    CELEB2 : Final = "tifa_lockhart"
    CLASS : Final = "woman"
    CROPPED : Final = "cropped"
    V_MINOR : Final = 1
    V_MAJOR : Final = 0
    V_BUILD : Final = 1
    STEPS : Final = 20
    CAP_NEG : Final = [
        "solo",
        "1boy",
        "hetero",
        "topless",
        "plump",
        "looking at viewer",
        "smile",
        "ass",
        "anus",
        "penis",
        "armpits",
        "feet",
        "soles",
        "clitoris",
        "tifa",
        "denim",
        "pantyhose",
        "navel",
        "cleavage",
        "sitting",
        "standing",
        "kneeling",
        "squatting",
        "lying",
        "masturbation",
        "lactation",
        "erection",
        "clitoral",
        "urethra",
        "clothes",
        "artist",
        "toe",
        "toes",
        "belly",
        "nose",
        "finger",
        "fingers",
        "fingering",
        "cum",
        "bra",
        "panties",
        "thong",
        "areolae",
        "censoring",
        "sandals",
        "fours",
        "grin",
        "tank",
        "yuri",
        "glasses",
        "jewelry",
        "necklace",
        "miniskirt",
        "fishnets",
        "underwear",
        "lingerie",
        "lace",
        "dress",
        "shorts",
        "shirt",
        "skirt",
        "polka",
        "earrings",
        "makeup",
        "pregnant",
        "mole",
        "username",
        "address",
    ]
    CAP_NEG_KEY : Final = [
        "girl",
        "boy",
        "female",
        "body",
        "nude",
        "boob",
        "breast",
        "nipple",
        "nipples",
        "pussy",
        "hair",
        "mouth",
        "tongue",
        "teeth",
        "eyes",
        "hand",
        "lips",
        "legs",
        "thighs",
        "foot",
        "shoulders",
        "nail",
        "arms",
        "looking",
        "panties",
        "pants",
        "underwear",
        "leotard",
        "swimsuit",
        "bracelet",
        "earring",
        "shoe",
        "heel",
        "solo",
        "control",
        "censored",
    ]
    CAP_NEG_COLOR : Final = [
        "black",
        "white",
        "red",
        "green",
        "blue",
        "pink",
        "brown",
        "orange",
        "yellow",
        "blonde",
        "lace",
        "grey",
        "denim",
        "short",
        "tied",
    ]
