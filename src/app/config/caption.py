from pathlib import Path
from typing import Final, TypedDict


class CaptionItem(TypedDict):
    train: list[str]
    trigger: list[str]
    wd14: list[str]
    joy: list[str]
    blip: list[str]
    
    @staticmethod
    def defaults() -> 'CaptionItem':
        return CaptionItem(
            train=[],
            trigger=[],
            wd14=[],
            joy=[],
            blip=[],
        )

class Caption():
    CAPTION_SUFFIX_PART: Final = "caption"
    CAPTION_SUFFIX_TRAIN: Final = ".txt"
    CAPTION_DICT: Final = CaptionItem.defaults() # empty CaptionDict instance for keys
    CAPTION_TYPES: Final = list(CAPTION_DICT.keys())
    CAPTION_TYPE_TRAIN: Final = CAPTION_TYPES[0]

    def __init__(self):
        pass

    @classmethod
    def suffix_from_type(cls, type_: str) -> str | None:
        """maps a caption file suffix to a caption type."""
        types = cls.CAPTION_TYPES
        if not types:
            return None
        if type_ == types[0]:
            return cls.CAPTION_SUFFIX_TRAIN
        for _type in types:
            if type_ == _type:
                return f".{cls.CAPTION_SUFFIX_PART}_{_type}" 

    @classmethod
    def type_from_suffix(cls, url_cap: Path | str | None) -> str | None:
        """takes a caption file and returns the type"""
        if not url_cap:
            return None
        url_cap = Path(url_cap)

        if not url_cap.is_file():
            return None
        suffix = url_cap.suffix
        split = suffix.split("_")
        
        if suffix == cls.CAPTION_SUFFIX_TRAIN:
            return cls.CAPTION_TYPE_TRAIN

        elif split[0] == "." + cls.CAPTION_SUFFIX_PART:
            if len(split) != 2:
                return None
            if split[1] in cls.CAPTION_TYPES:
                return split[1]
        
        return None

    @classmethod
    def suffixes(cls) -> list[str]:
        """list all known caption files suffixes."""
        types = cls.CAPTION_TYPES
        return [cls.suffix_from_type(_type) for _type in types]
    
    @classmethod
    def is_file(cls, url: Path | str | None) -> bool:
        """
        true if url is caption file.
        """
        if not url:
            return False
        path = Path(url)
        
        if path.is_dir():
            return False
        if path.suffix in cls.suffixes():
            return True
        return False
    
    @classmethod
    def urls_from_img(cls, url_img: Path | str | None) -> list[Path]:
        """
        returns all existing caption files wrt. a given file, file suffix is ignored!
        """
        if not url_img:
            return []

        path = Path(url_img)

        if not path.exists():
            return []
        if path.is_dir():
            return []
        
        ret: list[Path] = []
        for suffix in cls.suffixes():
            cand = Path(path.parent, path.stem).with_suffix(suffix)
            if cand.is_file():
                ret.append(cand)
        
        return ret

    @classmethod
    def dict_from_img(cls, url_img: Path | str | None) -> CaptionItem:
        """
        returns a CaptionDict of all found caption files.
        """
        if not url_img:
            return CaptionItem.defaults()

        path = Path(url_img)
        cap = CaptionItem.defaults()

        cap_files = cls.urls_from_img(path)
        for cap_file in cap_files:
            cap_type = cls.type_from_suffix(cap_file)
            with cap_file.open() as f:
                data = f.read()
            cap |= {cap_type: [data]}
        return cap
    
    @classmethod
    def write_dict_from_img(cls, url_img: Path | str | None, cap: CaptionItem) -> None:
        """
        write the caption files wrt. the img file.
        
        HANDLE WITH CARE, IT OVERWRITES!!!
        """
        if not url_img:
            return
        
        path = Path(url_img)
        if not path.is_file():
            return
        
        root = path.parent
        name = path.stem
        for type_ in cls.CAPTION_TYPES:
            suffix = cls.suffix_from_type(type_)
            if suffix:
                cap_file = Path(root, name).with_suffix(suffix)
                data = cap[type_]
                if not isinstance(data, list):
                    return
                if not data:
                    return
                data = cls.join_data(data)
    
    @classmethod
    def move_item_by_name(cls, item: CaptionItem, name: str) -> None:
        """
        moves all inner url data in the item as well as physically the files.
        
        HANDLE WITH CARE!
        """
        ctype = "blip"
        src = item[ctype]
        if src:
            target = Path(src.parent, f"{name}").with_suffix(src.suffix)
            src.rename(target)
            item["orig_hd"] = target

    @staticmethod
    def join_data(data: list[str]) -> list[str]:
        """joins a list of tags to one comma seperated string as one only elements of the list."""
        if not data:
            return []
        ret = data[0]
        for part in data[1:]:
            ret += f",{part}"
        return [ret]

    @staticmethod
    def split_data(data: list[str]) -> list[str]:
        """if a data list only contains one element, it splits this element by comma."""
        if not data:
            return []
        if len(data) > 1:
            return data
        return data[0].split(",")

