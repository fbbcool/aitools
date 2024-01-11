from src.imgset import ImgSet, Defines
from src.tags import TagsProfile

iset = ImgSet("lara", 0)

profile = TagsProfile("busty", trigger="xlara")
profile.append_header("cropped")
profile.append_footer(["indoors","watermark"])

iset.build([], Defines.TYPE_CAP_WD14, profile, 10, perc=0.33, folders=["origs", "faces"])
