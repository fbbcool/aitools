import os
import sys
from typing import Any
import pyperclip

from aidb import SceneConfig, SceneManager

from ait.tools.files import is_img_or_vid, is_dir


def imgs_or_vids_move_to_scene_id(params: Any, clipsapce: Any, config: SceneConfig) -> None:
    print(f'move: params[{params}] clipspace[{clipspace}]')


def scene_new(params: Any, clipsapce: Any, config: SceneConfig) -> None:
    urls_img_vid = [url for url in clipspace if is_img_or_vid(url)]
    urls_dir = [url for url in clipspace if is_dir(url)]

    if not urls_img_vid:
        print('no imgs found!')
    else:
        print(urls_img_vid)

    scenes_subdir_default = os.environ['AIDB_SCENE_DEFAULT']
    scenes_subdir = input(f'enter scenes subdir [{scenes_subdir_default}]: ')
    if not scenes_subdir:
        scenes_subdir = scenes_subdir_default
    yesno = input(
        f'sure using: config[{config}] subdir[{scenes_subdir}] (yes = enter | cancel = else)?'
    )
    if yesno:
        exit()

    if not scenes_subdir:
        scenes_subdir = None

    scm = SceneManager(config=config, subdir_scenes=scenes_subdir, verbose=0)  # type: ignore

    scm.new_scene_from_urls(urls_img_vid)
    scm.new_scene_from_urls(urls_dir)


if __name__ == '__main__':
    cmd = None
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
    params = None
    if len(sys.argv) > 2:
        params = sys.argv[2:]

    clipspace = pyperclip.paste().split('\n')

    if cmd is None:  # help
        print('help ... TODO')
        exit()

    scenes_subdir_default = os.environ['AIDB_SCENE_DEFAULT']
    config = os.environ['AIDB_SCENE_CONFIG']
    if not config:
        config = 'default'
    map_cmd = {
        'move': imgs_or_vids_move_to_scene_id,
        'new': scene_new,
    }

    print(f'config[{config}] cmd[{cmd}] params[{params}] clipspace[{clipspace}]')

    func = map_cmd.get(cmd, None)
    if func is None:
        print(f'cmd [{cmd}] unknown!')
        exit()
    func(params, clipspace, config)  # type: ignore
