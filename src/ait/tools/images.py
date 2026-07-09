import json
from pathlib import Path
from typing import Final, Optional
from PIL import Image as PILImage

from ait.tools.files import is_img

THUMBNAIL_SIZE: Final = 256
RESOLUTIONS: Final = [512, 768, 1024]
RATIOS: Final = [1.0, 3.0 / 4.0, 2.0 / 3.0]
THRESHOLD_RATIO_SQUARE: Final = 0.25


def image_from_url(url: str | Path, verbose: bool = False) -> PILImage.Image | None:
    url = Path(url)
    if not is_img(url):
        if verbose:
            print(f"'{url}' is not an image.")
        return None

    try:
        pil_image = PILImage.open(url)
        if verbose:
            print(f"Successfully opened image '{url}' as PIL image.")
        return pil_image
    except FileNotFoundError:
        if verbose:
            print(f"Error: Image file not found at '{url}'.")
        return None
    except IOError:
        if verbose:
            print(f"Error opening image file '{url}'.")
        return None
    except Exception as e:
        if verbose:
            print(f"An unexpected error occurred while getting PIL image for '{url}': {e}")
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

    # loras + seed (Power Lora Loader rgthree slots only)
    loras_info = _image_extract_loras_from_info_ext(pil.info)
    if loras_info is not None:
        info |= {'seed': loras_info['seed'], 'loras': loras_info['loras']}

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

    # A `Display Any (rgthree)` node titled 'string pos' is an explicit,
    # authoritative marker of the final positive prompt: when present, its
    # cached value defines the prompt and wins over the graph walk.
    named = _prompt_from_named_display(info_ext.get('workflow'), 'string pos', verbose)
    if named:
        return named

    prompt, chain = _walk_positive_to_text(data, verbose)
    if isinstance(prompt, str) and prompt:
        return prompt

    # The positive chain terminated in a dynamic node (e.g. a custom DB-backed
    # loader like FbbcoolScenesImage) whose resolved text is not stored in the
    # API `prompt` graph. Recover it from the UI `workflow` chunk, where a
    # `Display Any (rgthree)` node mirroring a link in the chain caches the
    # value it displayed at run time.
    cached = _prompt_from_display_cache(data, info_ext.get('workflow'), chain, verbose)
    if cached:
        return cached

    if verbose:
        print('prompt is empty')
    return None


def _walk_positive_to_text(data: dict, verbose=False) -> tuple[str | None, list[str]]:
    """Walk the ComfyUI API graph from the sampler's positive input back to a
    static text widget. Returns (text_or_None, chain) where `chain` is the list
    of node ids visited (used by the Display-cache fallback when the walk ends
    on a dynamic node)."""
    chain: list[str] = []
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
            return None, chain

        prompt = None
        value = None
        for key in ['positive', 'text_embeds']:
            value = inputs.get(key, None)
            if value is not None:
                id_pos = value[0]
                chain.append(str(id_pos))
                prompt = data[id_pos]
                if verbose:
                    print(f'{key} with value[{value}] found!')
                break  # of for

        max_loop = 10
        while not isinstance(prompt, str):
            if prompt is None:
                if verbose:
                    print('prompt is None!')
                return None, chain

            max_loop -= 1
            if max_loop < 0:
                if verbose:
                    print('max_loop is <0!')
                return None, chain

            inputs = None
            if isinstance(prompt, list):
                id_pos = prompt[0]
                chain.append(str(id_pos))
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
                return None, chain

            if inputs is None:
                if verbose:
                    print('inputs is None!')
                return None, chain

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
        return None, chain

    if not prompt:
        return None, chain
    return prompt, chain


def _prompt_from_named_display(info_workflow, title: str, verbose=False) -> str | None:
    """Return the cached value of a `Display Any (rgthree)` node whose title is
    `title` (e.g. 'string pos'), read from the UI `workflow` chunk. Such a node
    is an explicit, hand-placed marker of the resolved positive prompt."""
    if not info_workflow:
        return None
    try:
        wf = json.loads(info_workflow) if isinstance(info_workflow, str) else info_workflow
    except (json.JSONDecodeError, TypeError):
        return None

    for node in wf.get('nodes', []):
        if node.get('type') != 'Display Any (rgthree)':
            continue
        if (node.get('title') or '').strip().lower() != title.strip().lower():
            continue
        wv = node.get('widgets_values') or []
        if wv and isinstance(wv[0], str) and wv[0].strip():
            if verbose:
                print(f"recovered prompt from Display node titled '{title}'")
            return wv[0].strip()
    return None


def _prompt_from_display_cache(
    data: dict, info_workflow, chain: list[str], verbose=False
) -> str | None:
    """Fallback prompt recovery for graphs whose positive text is produced by a
    dynamic node (no static widget). A `Display Any (rgthree)` wired to the same
    link the sampler consumes caches the value it showed at run time inside the
    UI `workflow` chunk. Find such a display mirroring a node in `chain` and
    return its cached text.

    Chain order matters: we prefer the display nearest the sampler (post any
    string transforms), i.e. the earliest chain node that a display mirrors."""
    if not info_workflow:
        return None
    try:
        wf = json.loads(info_workflow) if isinstance(info_workflow, str) else info_workflow
    except (json.JSONDecodeError, TypeError):
        return None

    # UI node id -> cached displayed string (rgthree stores it in widgets_values[0]).
    cached_text: dict[str, str] = {}
    for node in wf.get('nodes', []):
        if node.get('type') != 'Display Any (rgthree)':
            continue
        wv = node.get('widgets_values') or []
        if wv and isinstance(wv[0], str) and wv[0].strip():
            cached_text[str(node.get('id'))] = wv[0].strip()
    if not cached_text:
        return None

    # API Display node -> the node id it displays (its `source` input link).
    display_source: dict[str, str] = {}
    for api_id, node in data.items():
        if not isinstance(node, dict) or node.get('class_type') != 'Display Any (rgthree)':
            continue
        src = (node.get('inputs') or {}).get('source')
        if isinstance(src, list) and src:
            display_source[str(api_id)] = str(src[0])

    for nid in chain:
        for api_id, src_id in display_source.items():
            if src_id == nid and api_id in cached_text:
                if verbose:
                    print(f'recovered prompt from Display node {api_id} (mirrors {nid})')
                return cached_text[api_id]
    return None


def _image_extract_loras_from_info_ext(info_ext: dict, verbose: bool = False) -> dict | None:
    """Walk the ComfyUI workflow JSON in the PNG `prompt` chunk and return the
    Power Lora Loader (rgthree) slots that were toggled on, plus the sampler
    seed.

    Returns `{'seed': int | None, 'loras': [{'name', 'strength', 'source'},
    ...]}`, or `None` if the workflow JSON isn't present.

    Only `Power Lora Loader (rgthree)` slots with `on: True` and `strength !=
    0` are emitted. Single-LoRA loader nodes (`LoraLoader`,
    `LoraLoaderModelOnly`) are intentionally ignored — they typically hold
    fixed infrastructure LoRAs (step distillation, etc.) that aren't
    variables of interest in testset reviews.
    """
    info_prompt = info_ext.get('prompt', None)
    if info_prompt is None:
        return None
    try:
        data = json.loads(info_prompt)
    except (json.JSONDecodeError, TypeError):
        if verbose:
            print('prompt chunk is not valid JSON')
        return None

    seed: int | None = None
    loras: list[dict] = []

    for node_id, node in data.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get('class_type', '')
        inputs = node.get('inputs', {}) or {}

        if class_type in ('KSampler', 'KSamplerAdvanced'):
            s = inputs.get('seed', inputs.get('noise_seed'))
            if isinstance(s, int):
                seed = s

        if class_type == 'Power Lora Loader (rgthree)':
            for key, val in inputs.items():
                if not key.startswith('lora_'):
                    continue
                if not isinstance(val, dict):
                    continue
                if not val.get('on', False):
                    continue
                name = val.get('lora')
                strength = val.get('strength')
                if not name or not isinstance(strength, (int, float)) or strength == 0:
                    continue
                loras.append(
                    {
                        'name': name,
                        'strength': float(strength),
                        'source': f'node-{node_id}/{key}',
                    }
                )

    return {'seed': seed, 'loras': loras}


def train_from_image(
    pil: PILImage.Image, ratios: list[float] = RATIOS, resolutions: list[int] = RESOLUTIONS
) -> Optional[PILImage.Image]:
    width, height = pil.size  # Get dimensions
    minwh = min(width, height)
    maxwh = max(width, height)

    ratio = float(minwh) / float(maxwh)
    ratio_target = 1.0
    loss_ratio = 1.0
    for ratio_check in ratios:
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
    resolution_target = resolutions[0]
    width_crop, height_crop = pil_train.size
    maxwh_crop = max(width_crop, height_crop)
    for resolution_check in resolutions:
        if maxwh_crop > resolution_check:
            resolution_target = resolution_check

    train_max = resolution_target
    train_min = int(float(resolution_target) * ratio_target)
    if width_crop == maxwh_crop:
        width_train = train_max
        height_train = train_min
    else:
        width_train = train_min
        height_train = train_max

    print(
        f'train img resize: [{width},{height}] -> [{width_crop},{height_crop}] -> [{width_train},{height_train}]'
    )
    pil_train = pil_train.resize((width_train, height_train), PILImage.Resampling.LANCZOS)

    return pil_train
