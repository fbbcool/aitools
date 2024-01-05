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
    DIR_BUILD : Final = "build"
    DIR_TAGS : Final = "tags"


class Defaults():
    NAME = "lara"
    CELEB : Final = "rakhee thakar"
    CLASS : Final = "woman"
    V_MINOR : Final = 1
    V_MAJOR : Final = 0
    V_BUILD : Final = 1
    STEPS : Final = 20
    CAP_NEG : Final = [
        "solo",
        "1boy",
        "hetero",
        "topless",
        "looking at viewer",
        "smile",
        "ass",
        "anus",
        "penis",
        "armpits",
        "navel",
        "cleavage",
        "sitting",
        "standing",
        "kneeling",
        "squatting",
        "lying",
        "masturbation",
        "bra",
        "panties",
        "glasses",
        "jewelry",
        "underwear",
        "lingerie",
        "lace",
        "dress",
        "earrings",
        "makeup",
    ]
    CAP_NEG_KEY : Final = [
        "girl",
        "boy",
        "female",
        "body",
        "nude",
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
    ]
