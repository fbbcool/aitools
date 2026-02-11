import os
import sys

from ait.tools.files import is_dir
from aidb import SceneManager, Scene, SceneConfig

if __name__ == '__main__':
    urls = sys.argv[1:]
    urls_dir = [url for url in urls if is_dir(url)]

    config_str = os.environ['AIDB_SCENE_CONFIG']
    if not config_str:
        config_str = 'default'
    config: SceneConfig = config_str
    scm = SceneManager(verbose=0, config=config)

    for url in urls_dir:
        try:
            scene = Scene(scm, url)
        except Exception:
            continue
        scene.update()
