import os
from pathlib import Path
import sys
from typing import Any
import pyperclip

from aidb import SceneConfig, SceneManager, SceneImageManager, SceneImage, Scene

from aidb.app.scene.app import AIDBSceneApp

from aidb.scene.scene_common import SceneDef
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


def scenes_update(params: Any, clipsapce: Any, config: SceneConfig) -> None:
    scm = SceneManager(verbose=0, config=config)
    scm.scenes_update()


def scene_url(params: Any, clipsapce: Any, config: SceneConfig) -> None:
    scm = SceneManager(verbose=0, config=config)
    url_reg_file = clipsapce[0]
    url = scm.url_from_registered_file(url_reg_file)
    print(str(url))
    pyperclip.copy(str(url))


def images_info(params: Any, clipsapce: Any, config: SceneConfig) -> None:
    urls_img = [url for url in clipsapce if is_img_or_vid(url)]

    if not urls_img:
        print('no imgs found!')
    else:
        print(urls_img)

    im: SceneImageManager = SceneManager(config=config, verbose=0).scene_image_manager()
    for url in urls_img:
        img: SceneImage = im.image_from_id_or_url(url)
        if img is not None:
            print(img)


def images_register(params: Any, clipsapce: Any, config: SceneConfig) -> None:
    urls_img = [url for url in clipsapce if is_img_or_vid(url)]

    if not urls_img:
        print('no imgs found!')
    else:
        print(urls_img)

    sm = SceneManager(config=config, verbose=0)
    im: SceneImageManager = sm.scene_image_manager()

    urls_scene_to_update = []
    for url in urls_img:
        ret = im.register_from_url(url)
        if ret is not None:
            # remember potential scene url
            urls_scene_to_update.append(Path(url).parent)

    urls_scene_to_update = list(set(urls_scene_to_update))
    for url_scene in urls_scene_to_update:
        sid = sm.id_from_dotfile(url_scene)
        if sid is None:
            continue
        scene: Scene = sm.scene_from_id_or_url(sid)
        scene.update(force=True)


def images_rate(params: Any, clipsapce: Any, config: SceneConfig) -> None:
    urls_img = [url for url in clipsapce if is_img_or_vid(url)]

    if not urls_img:
        print('no imgs found!')
    else:
        print(urls_img)

    im: SceneImageManager = SceneManager(config=config, verbose=0).scene_image_manager()
    rating = params[0]
    for url in urls_img:
        img: SceneImage = im.image_from_id_or_url(url)
        if img is not None:
            img.rate(rating)


def start_app(params: Any, clipsapce: Any, config: SceneConfig) -> None:
    scm = SceneManager(config=config)  # type: ignore
    scm.scenes_update()
    app = AIDBSceneApp(scm)
    app.launch(server_port=7861)


def _keyval(params: list[str]) -> tuple[dict, list[str]]:
    keyvals = {}
    params_reduced = []
    for param in params:
        split = param.split('=')
        if len(split) >= 2:
            keyvals |= {split[0]: split[1]}
        else:
            params_reduced.append(param)
    return keyvals, params_reduced


if __name__ == '__main__':
    cmd = None
    if len(sys.argv) > 1:
        cmd = sys.argv[1]

    params = None
    if len(sys.argv) > 2:
        params = sys.argv[2:]

    keyval = {}
    if params is not None:
        keyval, params = _keyval(params)

    clipspace = pyperclip.paste().split('\n')

    map_cmd = {
        'app': start_app,
        'move': imgs_or_vids_move_to_scene_id,
        'url': scene_url,
        'new': scene_new,
        'update': scenes_update,
        'imgs_info': images_info,
        'imgs_register': images_register,
        'imgs_rate': images_rate,
    }

    if cmd is None:  # help
        print('help ... TODO')
        exit()

    scenes_subdir_default = os.environ['AIDB_SCENE_DEFAULT']
    config = os.environ['AIDB_SCENE_CONFIG']
    if not config:
        config = 'default'
    param_config = keyval.get('config', None)
    if param_config is not None:
        config = param_config

    print(f'config[{config}] cmd[{cmd}] params[{params}] clipspace[{clipspace}]')

    func = map_cmd.get(cmd, None)
    if func is None:
        print(f'cmd [{cmd}] unknown!')
        exit()
    func(params, clipspace, config)  # type: ignore
