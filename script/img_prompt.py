import sys

# from pprint import pprint
from ait.image import get_prompt_comfy

if __name__ == '__main__':
    url_img = sys.argv[1]
    prompt = get_prompt_comfy(url_img)
    print(prompt)
