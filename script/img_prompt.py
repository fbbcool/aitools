import sys
from ait.tools.images import image_info_from_url

if __name__ == '__main__':
    info = image_info_from_url(sys.argv[1])
    if info is not None:
        print(info.get('prompt', ''))
