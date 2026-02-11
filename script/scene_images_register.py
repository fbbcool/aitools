import sys
import os

from ait.tools.files import is_img_or_vid
from aidb import SceneManager, SceneConfig

if __name__ == '__main__':
    urls = sys.argv[1:]
    urls_img = [url for url in urls if is_img_or_vid(url)]

    if not urls_img:
        print('no imgs found!')
    else:
        print(urls_img)

    config_str = os.environ['AIDB_SCENE_CONFIG']
    if not config_str:
        config_str = 'default'
    config: SceneConfig = config_str
    iscm = SceneManager(config=config, verbose=0).scene_image_manager()
    for url in urls_img:
        iscm.register_from_url(url)
