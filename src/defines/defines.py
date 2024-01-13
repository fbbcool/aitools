import os
from typing import Final

class Defines():
    DirBuild : Final = "build"
    DirTmp : Final = f"{DirBuild}/tmp"
    DirPools : Final = f"{DirBuild}/pools"
    DirTrains : Final = f"{DirBuild}/trains"
    
    TypeImgTarget : Final = "png"
    TypeImgSource : Final = "jpg"
    TypeCap : Final = "caption"
    TypeCapWd14 : Final = f"{TypeCap}_wd14"
    TypeCapBlip : Final = f"{TypeCap}_blip"
    TypeCapCropped : Final = f"{TypeCap}_cropped"
    
    CapCropped : Final = "cropped"

    MaxIds : Final = 2000

    Epochs : Final = 10
    TrainSteps : Final = 20
    PicsNum : Final = 100

class Helpers():
    @classmethod
    def url_exit(cls, url: str) -> bool:
        return os.path.isfile(url) or os.path.isdir(url)
    @classmethod
    def url_change_type(cls, url: str, to_type: str) -> str:
        return f"{os.path.splitext(url)[0]}.{to_type}"
    @classmethod
    def caption_check_type(cls, use_type: str) -> None:    
        if Defines.TypeCap != use_type.split("_")[0]:
            raise ValueError(f"Unknown caption {use_type}.")
    @classmethod
    def tags_to_caps(cls, url) -> list[str]:
        try:
            with open(url) as f:
                tags = f.readline()
        except FileNotFoundError:
            print(f"Warning: no tags file {url} found.")
            return []
        
        caps = []
        caps_raw = tags.split(",")
        for cap in caps_raw:
            caps.append(cap.replace("_", " "))
        return caps

    @classmethod
    def caps_to_tags(cls, caps: list[str], url: str) -> None:
        tags = ""
        for cap in caps:
            cap = cap.replace("_", " ")
            tags += f",{cap}"
        tags = tags[1:]
        
        try:
            with open(url,'w') as f:
                    f.write(tags)
        except:
            print(f"Warning: write tags {url} failed.")

