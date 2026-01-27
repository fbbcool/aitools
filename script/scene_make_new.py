import sys

# from pprint import pprint
from ait.tools.files import is_dir, is_img_or_vid
from aidb import SceneManager

if __name__ == '__main__':
    urls = sys.argv[1:]
    urls_img_vid = [url for url in urls if is_img_or_vid(url)]
    urls_dir = [url for url in urls if is_dir(url)]

    if not urls_img_vid:
        print('no imgs found!')
    else:
        print(urls_img_vid)

    # scm = SceneManager(subdir_scenes='grow')
    scm = SceneManager()

    scm.new_scene_from_urls(urls_img_vid)
    scm.new_scene_from_urls(urls_dir)
