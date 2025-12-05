import sys
from pathlib import Path

# from pprint import pprint
from ait.image import get_prompt_comfy

if __name__ == '__main__':
    url_img = sys.argv[1]

    print(f'-> {Path(url_img).name}')

    prompt = get_prompt_comfy(url_img)
    print(prompt)
