from src.depr_imgset import ImgPool, Defines
from src.tags import TagsProfile

iset = ImgPool("lara", 0)

profile = TagsProfile("busty", trigger="xlara")
profile.append_header("cropped")
profile.append_footer(["indoors","watermark"])

iset.build([], Defines.TypeCapWd14, profile, 10, perc=0.33, folders=["origs", "faces"])
