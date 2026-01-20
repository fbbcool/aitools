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

    joy = Joy('gts_prompter')
    # joy = Joy('1xlasm')
    # joy = Joy('1hairy')
    # joy = Joy('1fbb')
    caption = joy.imgurl_caption(str(url_img))

    print(f'<prompt>\n{caption}\n </prompt>')
