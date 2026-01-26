import sys

from ait.tools.files import is_img_or_vid
from aidb import SceneManager

if __name__ == '__main__':
    urls = sys.argv[1:]
    urls_img = [url for url in urls if is_img_or_vid(url)]

    if not urls_img:
        print('no imgs found!')
    else:
        print(urls_img)

    iscm = SceneManager().scene_image_manager()
    for url in urls_img:
        iscm.register_from_url(url)
