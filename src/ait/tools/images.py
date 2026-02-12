import json
from pathlib import Path
from typing import Final, Literal, Optional
from PIL import Image as PILImage
import time

from ait.tools.files import is_img

THUMBNAIL_SIZE: Final = 256
RESOLUTIONS: Final = [256, 512, 768, 1024]
RATIOS: Final = [1.0, 3.0 / 4.0, 2.0 / 3.0]
THRESHOLD_RATIO_SQUARE: Final = 0.25


def image_from_url(url: str | Path) -> PILImage.Image | None:
    url = Path(url)
    if not is_img(url):
        return None

    try:
        pil_image = PILImage.open(url)
        # print(f"Successfully opened image '{full_path}' as PIL image.") # Too verbose
        return pil_image
    except FileNotFoundError:
        # print(f"Error: Image file not found at '{url}'.")
        return None
    except IOError:
        # print(f"Error opening image file '{url}': {e}")
        return None
    except Exception:
        # print(f"An unexpected error occurred while getting PIL image for '{url}': {e}")
        return None


def image_info_from_url(url: Path | str, include_info_ext: bool = False) -> dict | None:
    """
    Creates an info struct if image exists, otherwise returns None.

    The given url is stored in ['url_src'].
    """
    url = Path(url)
    pil = image_from_url(url)
    if pil is None:
        return None
    pil.load()

    info = {'url_src': str(url)}

    # timestamps
    # get creation time
    info |= {'timestamp_created': url.stat().st_ctime}
    # set data ts to current time
    # DISABLED: oid stores db creation time!
    # info |= {'timestamp_data': time.time()}

    # size
    info |= {'width': pil.width}
    info |= {'height': pil.height}
    info |= {'size': pil.width * pil.height}

    # prompt
    prompt = _image_extract_prompt_from_info_ext(pil.info, verbose=False)
    if prompt is not None:
        info |= {'prompt': prompt}

    # info_ext
    if include_info_ext:
        info |= {'info_ext': pil.info}

    return info


def thumbnail_to_url(url_from: Path | str, url_to: Path | str, size: int = THUMBNAIL_SIZE) -> None:
    """Will create url_to parent and overrides url_to. url_from stoic"""
    if not is_img(url_from):
        return None

    url_to = Path(url_to)
    url_to.parent.mkdir(exist_ok=True, parents=True)
    pil = PILImage.open(url_from)
    pil.thumbnail((size, size))
    pil.save(url_to)


def _image_extract_prompt_from_info_ext(info_ext: dict, verbose=False) -> str | None:
    info_prompt = info_ext.get('prompt', None)
    if info_prompt is None:
        return None
    data = json.loads(info_prompt)

    prompt = None
    try:
        ksampler = {}
        for id in data:
            class_type = data[id]['class_type']
            if verbose:
                print(class_type)
            if class_type in ['KSampler', 'WanVideoSampler', 'WanMoeKSampler', 'XT404_Skynet_1']:
                ksampler = data[id]
                if verbose:
                    print(f'{class_type} found!')
                break
        inputs = ksampler.get('inputs', None)
        if inputs is None:
            if verbose:
                print('no inputs found!')
            return None

        prompt = None
        value = None
        for key in ['positive', 'text_embeds']:
            value = inputs.get(key, None)
            if value is not None:
                id_pos = value[0]
                prompt = data[id_pos]
                if verbose:
                    print(f'{key} with value[{value}] found!')
                break  # of for

        max_loop = 10
        while not isinstance(prompt, str):
            if prompt is None:
                if verbose:
                    print('prompt is None!')
                return None

            max_loop -= 1
            if max_loop < 0:
                prompt = None
                if verbose:
                    print('max_loop is <0!')
                return None

            inputs = None
            if isinstance(prompt, list):
                id_pos = prompt[0]
                node_pos = data[id_pos]
                if isinstance(node_pos, dict):
                    inputs = node_pos.get('inputs', None)
                    if verbose:
                        print(f'value[{value}] found!')
            elif isinstance(prompt, dict):
                inputs = prompt.get('inputs', None)
                if verbose:
                    print(f'inputs[{inputs}] found!')
            else:
                if verbose:
                    print(f'prompt [{prompt}] is neither dict nor list')
                return None

            if inputs is None:
                if verbose:
                    print('inputs is None!')
                return None

            prompt = inputs.get('text', None)
            keys = ['Text', 'string_b', 'positive_prompt', 'conditioning']
            for key in keys:
                value = inputs.get(key, None)
                if value is not None:
                    prompt = value
                    break  # for
            if prompt is None:
                # search anys
                for i in range(10):
                    key = f'any_0{i}'
                    value = inputs.get(key, None)
                    if value is not None:
                        prompt = value

    except Exception as e:
        if verbose:
            print(f'got an exception: {e}')
        return None

    # always return None, regardless of None or empty.
    if not prompt:
        if verbose:
            print('prompt is empty')
        return None
    return prompt


def train_from_image(pil: PILImage.Image) -> Optional[PILImage.Image]:
    width, height = pil.size  # Get dimensions
    minwh = min(width, height)
    maxwh = max(width, height)

    ratio = float(minwh) / float(maxwh)
    ratio_target = 1.0
    loss_ratio = 1.0
    for ratio_check in RATIOS:
        if ratio < ratio_check:
            loss = ratio_check / ratio - ratio_check
        else:
            loss = ratio - ratio_check
        if loss < loss_ratio:
            loss_ratio = loss
            ratio_target = ratio_check

    if ratio < ratio_target:
        new_min = minwh
        new_max = int(float(minwh) / ratio_target)
    else:
        new_min = int(float(maxwh) * ratio_target)
        new_max = maxwh

    if width == maxwh:
        new_width = new_max
        new_height = new_min
    else:
        new_width = new_min
        new_height = new_max

    left = (width - new_width) / 2
    top = (height - new_height) / 2
    right = (width + new_width) / 2
    bottom = (height + new_height) / 2

    # make square by crop around center
    pil_train = pil.crop((left, top, right, bottom))

    # resize
    resolution_target = RESOLUTIONS[0]
    width, height = pil_train.size
    maxwh = max(width, height)
    minwh = min(width, height)
    for resolution_check in RESOLUTIONS:
        if maxwh == resolution_check:
            resolution_target = resolution_check
            break
        elif maxwh < resolution_check:
            resolution_target = resolution_check
    pil_train = pil_train.resize((scale_width, scale_height), Image.Resampling.LANCZOS)
