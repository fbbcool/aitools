import sys
from pathlib import Path

# from pprint import pprint
from ait.image import get_prompt_comfy
from ait.tools.files import is_dir, is_img_or_vid
from aidb.scene_manager import SceneManager

if __name__ == '__main__':
    urls = sys.argv[1:]
    urls_img = [url for url in urls if is_img_or_vid(url)]
    urls_dir = [url for url in urls if is_dir(url)]

    # url_img = Path(sys.argv[1])
    # if not url_img.exists():
    #    exit(1)
    # if url_img.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.webp']:
    #    exit(1)

    # prompt = get_prompt_comfy(str(url_img), verbose=False)
    # print(prompt)
    #
    print(urls_img)

    if not urls_img:
        print('no imgs found!')

    scm = SceneManager()

    scm.scene_new(urls_img)
    scm.scene_new(urls_dir)
