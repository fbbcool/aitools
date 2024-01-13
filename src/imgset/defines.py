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