import os
from typing import Final

from ..defines import Defines, Helpers

class Tags:
    Header : Final = []
    Footer : Final = []
    NegCommon : Final = [
        "1girl",
        "2girls",
        "multiple girls",
        "mature female",
        "couple",
        "1boy",
        "2boys",
        "male",
        "penis",
        "hetero",
        "lactation",
        "urethra",
        "artist",
        "yuri",
        "pregnant",
        "mole",
        "username",
        "address",
        "tifa lockhart",
    ]

class TagsProfile(dict):
    KnownTypes = [
        "busty",
        "leggy",
        "fbb",
        "slave",
    ]
    def __init__(self, _type: str, trigger: str = ""):
        super().__init__({
            "header": [trigger],
            "negative": Tags.NegCommon.copy(),
            "replace": {},
            "footer": [],
        })
        
        if _type not in self.KnownTypes:
            print(f"Warning: unknown profile type ({_type}), empty profile created.")
            self.type = "empty"
            return

        self.type = _type
        getattr(self, f"make_{self.type}")

    @property
    def make_busty(self):
        self["header"] = ["woman"] + self["header"]
        self["negative"] = self["negative"] + ["large breasts", "huge breasts", "mature female"]
        self["replace"] = {
            "breasts": ["breasts", "small breasts"],
        }
        self["footer"] = [] + self["footer"]

    @property
    def make_leggy(self):
        self["header"] = ["woman"] + self["header"]
        self["negative"] = self["negative"] + ["xxx yyy"]
        self["replace"] = {
            "aaa": ["bbb", "ccc"],
        }
        self["footer"] = [] + self["footer"]

    @property
    def make_fbb(self):
        self["header"] = ["woman"] + self["header"]
        self["negative"] = self["negative"] + ["xxx yyy"]
        self["replace"] = {
            "aaa": ["bbb", "ccc"],
        }
        self["footer"] = [] + self["footer"]

    @property
    def make_slave(self):
        self["header"] = ["man"] + self["header"]
        self["negative"] = self["negative"] + ["xxx yyy"]
        self["replace"] = {
            "aaa": ["bbb", "ccc"],
        }
        self["footer"] = [] + self["footer"]

    def append_header(self, tags) -> None:
        if isinstance(tags, list):
            self["header"] = self["header"] + tags
        elif isinstance(tags, str):
            self["header"].append(tags)
    
    def append_footer(self, tags) -> None:
        if isinstance(tags, list):
            self["footer"] = self["footer"] + tags
        elif isinstance(tags, str):
            self["footer"].append(tags)
    
    def append_negative(self, tags) -> None:
        if isinstance(tags, list):
            self["negative"] = self["negative"] + tags
        elif isinstance(tags, str):
            self["negative"].append(tags)
    
    def append_replace(self, dict_replace) -> None:
        self["replace"] = self["replace"] | dict_replace
    
def build_tags(url_img: str, profile: TagsProfile, use_type=Defines.TypeCapWd14) -> None:
    Helpers.caps_to_tags(use_type)
    url_from_tags = Helpers.url_change_type(url_img, use_type)
    from_caps = []
    if not Helpers.url_exit(url_from_tags):
        print(f"Warning: not tags file found: {url_from_tags}.")
    elif True:
        from_caps = Helpers.tags_to_caps(url_from_tags)
    url_to_tags = f"{os.path.splitext(url_img)[0]}.{Defines.TypeCap}"
    to_caps = build_caps(from_caps, profile)
    Helpers.caps_to_tags(to_caps, url_to_tags)

def build_caps(from_caps: list[str], profile: TagsProfile) -> list[str]:
    # clean
    caps_clean = []
    for cap in from_caps:
        cap = cap.replace("_", " ")
        clean = True
        if cap in profile["negative"]:
            clean = False
        for sub_cab in cap.strip().split(" "):
            for del_tag in profile["negative"]:
                if del_tag in sub_cab:
                    clean = False
        if clean:
            # replace
            if cap in profile["replace"].keys():
                cap = profile["replace"][cap]
            if isinstance(cap, str):
                cap = [cap]
            caps_clean += cap
    
    return profile["header"] + caps_clean + profile["footer"]
