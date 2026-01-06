from pathlib import Path
from PIL import Image as PILImage
import json


def get_prompt_comfy(
    img_path: Path | str = '', pil: PILImage.Image | None = None, verbose: bool = False
) -> str | None:
    if pil is None:
        img_path = Path(img_path)
        if not img_path.exists():
            return None
        if not img_path.is_file():
            return None
        img_pil = PILImage.open(img_path)
    else:
        img_pil = pil

    img_pil.load()
    data = json.loads(img_pil.info['prompt'])

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
                return None

            max_loop -= 1
            if max_loop < 0:
                prompt = None
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
                return None

            if inputs is None:
                return None

            prompt = inputs.get('text', None)
            keys = ['Text', 'string_b', 'positive_prompt']
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

    except Exception:
        return None

    # always return None, regardless of None or empty.
    if not prompt:
        return None
    return prompt
