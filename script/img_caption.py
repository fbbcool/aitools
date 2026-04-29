import sys
from pathlib import Path
from typing import Optional

from aidb import SceneDef
from ait.caption import Joy, JoySceneDB
from ait.tools.files import is_img

if __name__ == '__main__':
    trigger = 'gts_prompter'
    url_img = Path(sys.argv[1])
    if not is_img(url_img):
        exit(1)
    print(f'-> {url_img.name}')

    caption: Optional[str] = None
    prompt: Optional[str] = None
    id = SceneDef.id_from_filename_orig(url_img)
    if id is not None:
        joy = JoySceneDB('prod', trigger=trigger)
        prompt, caption = joy._id_caption(id)

    if caption is None:
        joy = Joy(trigger)
        prompt, caption = joy.imgurl_caption(str(url_img))

    print(f'<caption>\n{caption}\n </caption>')
