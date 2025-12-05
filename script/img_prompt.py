import sys
from pathlib import Path

# from pprint import pprint
from ait.image import get_prompt_comfy

if __name__ == '__main__':
    url_img = sys.argv[1]

    url_img = Path(sys.argv[1])
    if not url_img.exists():
        exit(1)
    if url_img.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.webp']:
        exit(1)

    prompt = get_prompt_comfy(str(url_img))
    print(prompt)
