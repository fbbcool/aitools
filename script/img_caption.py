import sys
from ait.caption import Joy

if __name__ == '__main__':
    url_img = sys.argv[1]
    joy = Joy('1gts')
    caption = joy.imgurl_caption(url_img)
    print(caption)
