import os
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

    scenes_subdir_default = os.environ['AIDB_SCENE_DEFAULT']
    config = os.environ['AIDB_SCENE_CONFIG']
    if not config:
        config = 'default'
    scenes_subdir = input(f'enter scenes subdir [{scenes_subdir_default}]: ')
    if not scenes_subdir:
        scenes_subdir = scenes_subdir_default
    yesno = input(f'sure using {scenes_subdir} as subdir (yes = enter | cancel = else)?')
    if yesno:
        exit()

    if not scenes_subdir:
        scenes_subdir = None

    scm = SceneManager(config=config, subdir_scenes=scenes_subdir, verbose=0)  # type: ignore

    scm.new_scene_from_urls(urls_img_vid)
    scm.new_scene_from_urls(urls_dir)
