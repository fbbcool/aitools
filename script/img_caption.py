import sys
from pathlib import Path
from ait.caption import Joy

if __name__ == '__main__':
    url_img = sys.argv[1]

    print(f'-> {Path(url_img).name}')

    joy = Joy('1gts')
    caption = joy.imgurl_caption(url_img)

    print(f'<prompt>\n{caption}\n </prompt>')
