from pathlib import Path
from PIL import Image as PILImage
import json


def get_prompt_comfy(img_path: Path | str) -> str | None:
    img_path = Path(img_path)
    if not img_path.exists():
        return None
    if not img_path.is_file():
        return None

    img_pil = PILImage.open(img_path)
    img_pil.load()
    data = json.loads(img_pil.info['prompt'])

    prompt = None
    try:
        ksampler = {}
        for id in data:
            class_type = data[id]['class_type']
            if class_type in ['KSampler', 'WanVideoSampler', 'WanMoeKSampler']:
                ksampler = data[id]
                break
        inputs = ksampler.get('inputs', None)
        if inputs is None:
            return None

        prompt = None
        value = None
        for key in ['positive', 'text_embeds']:
            value = inputs.get(key, None)
            if value is not None:
                id_pos = value[0]
                prompt = data[id_pos]
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
            elif isinstance(prompt, dict):
                inputs = prompt.get('inputs', None)
            else:
                return None

            if inputs is None:
                return None

            prompt = inputs.get('text', None)
            for key in ['Text', 'string_b', 'positive_prompt']:
                value = inputs.get(key, None)
                if value is not None:
                    prompt = value
                    break  # for

    except Exception:
        return None

    # always return None, regardless of None or empty.
    if not prompt:
        return None
    return prompt
