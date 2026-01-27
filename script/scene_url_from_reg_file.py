import sys

# from pprint import pprint
from ait.tools.files import is_dir, is_img_or_vid
from aidb import SceneManager

if __name__ == '__main__':
    url_reg_file = sys.argv[1]
    scm = SceneManager(verbose=0)
    url = scm.url_from_registered_file(url_reg_file)
    print(str(url))
