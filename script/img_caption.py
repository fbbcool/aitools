import sys
from pathlib import Path
from ait.caption import Joy

if __name__ == '__main__':
    url_img = Path(sys.argv[1])
    if not url_img.exists():
        exit(1)
    if url_img.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.webp']:
        exit(1)

    print(f'-> {url_img.name}')

    joy = Joy('1gts')
    caption = joy.imgurl_caption(str(url_img))

    print(f'<prompt>\n{caption}\n </prompt>')
