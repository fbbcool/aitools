import sys

from ait.tools.files import is_dir
from aidb import SceneManager, Scene

if __name__ == '__main__':
    urls = sys.argv[1:]
    urls_dir = [url for url in urls if is_dir(url)]
    scm = SceneManager(verbose=0)

    for url in urls_dir:
        try:
            scene = Scene(scm, url)
        except Exception:
            continue
        scene.update()
