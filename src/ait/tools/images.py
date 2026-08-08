import json
from pathlib import Path
from typing import Final, Optional
from PIL import Image as PILImage

from ait.tools.files import is_img

THUMBNAIL_SIZE: Final = 256
RESOLUTIONS: Final = [512, 768, 1024]
RATIOS: Final = [1.0, 3.0 / 4.0, 2.0 / 3.0]
THRESHOLD_RATIO_SQUARE: Final = 0.25

METADATA_SCHEMA: Final = 'ait.image.metadata.v1'

# PNG text chunk carrying the provenance envelope of the image an AI render was derived
# from (written by the fbbcool-suite preview/save nodes; any JSON object is accepted).
# The ComfyUI graph chunks cannot serve this: resolved parent identity (scene/image ids,
# clipboard payloads) exists only at execution time and never appears in the graph.
PARENT_METADATA_CHUNK: Final = 'parent_metadata'


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


def metadata(url: Path | str) -> dict | None:
    """Single schematized entry point for image-embedded metadata.

    Opens the image once and returns the `ait.image.metadata.v1` dict; the
    caller never branches on pipeline (krea2/qwen/wan), enhancer payload
    version (v3/v4) or partial embeds. Missing/unopenable file -> None
    (consistent with `image_info_from_url`); never raises on malformed or
    partial metadata — every key is always present, `None`/`[]` when a piece
    is not extractable.

    Schema (`schema` == `METADATA_SCHEMA`):
        {
          'schema': 'ait.image.metadata.v1',
          'url': str,                       # the path given
          'image': {'width': int, 'height': int, 'size': int,   # size = w*h
                    'timestamp_created': float},
          'comfy': {'prompt_graph': dict | None,   # raw parsed ComfyUI chunks
                    'workflow': dict | None},
          'enhancer': dict | None,          # raw 1xlasm-enhancer iteration
                                            # payload (v3 or v4), schema_id-gated;
                                            # authoritative copy across both
                                            # chunks — a prompt_index-bearing
                                            # copy wins over an index-less one
          'generation': {
              'prompt': str | None,         # identified positive prompt
              'prompt_index': int | None,   # v4 rendered entry (prompt_index,
                                            # else prompts.current); v3/plain None
              'prompt_offset': int | None,  # prompt_index - prompts.current,
                                            # when both are known
          },
          'loras': [{'name': str, 'strength': float, 'source': str}, ...],
          'seed': int | None,
          'parent': dict | None,            # provenance envelope of the source
                                            # image this render was derived from
                                            # (`parent_metadata` chunk)
          'inherited': [str, ...],          # top-level fields recovered from
                                            # `parent` because the image's own
                                            # chunks didn't yield them; [] when
                                            # everything is first-hand
        }

    Inheritance: when the image's own chunks don't yield a field but a
    `parent` envelope is present, the field is recovered from the parent —
    a round-tripped `ait.image.metadata.v1` dict contributes `enhancer`,
    `generation`, `seed` and `loras`; any other envelope shape (enhancer
    client envelope, scenes `input_data`, raw wrap) contributes an embedded
    iteration payload found by schema_id, from which `generation` is
    resolved. Own data always wins; inherited fields are listed in
    `inherited`; the `parent` envelope itself stays verbatim.
    """
    url = Path(url)
    pil = image_from_url(url)
    if pil is None:
        return None
    try:
        pil.load()
    except Exception:
        return None
    return _metadata_from_pil(url, pil)


def _metadata_from_pil(url: Path, pil: PILImage.Image) -> dict:
    """Core of `metadata()`: build the v1 schema dict from an opened image.
    Shared with the `image_info_from_url` adapter so the file is opened once."""
    info_ext = pil.info or {}

    prompt_graph = _parse_json_chunk(info_ext.get('prompt'))
    workflow = _parse_json_chunk(info_ext.get('workflow'))

    # Authoritative payload copy across BOTH ComfyUI chunks (board ISSUE in
    # #23's reopen: real renders can carry the raw index-less clipspace copy in
    # the prompt graph while the prompt_index-bearing envelope sits only in the
    # workflow chunk).
    enhancer = _select_enhancer_payload(prompt_graph, workflow)

    prompt: str | None = None
    try:
        prompt = _image_extract_prompt_from_info_ext(info_ext, verbose=False)
    except Exception:
        pass

    seed: int | None = None
    loras: list[dict] = []
    try:
        loras_info = _image_extract_loras_from_info_ext(info_ext)
    except Exception:
        loras_info = None
    if loras_info is not None:
        seed = loras_info['seed']
        loras = loras_info['loras']

    parent = _parse_json_chunk(info_ext.get(PARENT_METADATA_CHUNK))
    # Round-tripped metadata() dict (SmartInput `metadata` output) — its fields
    # describe the parent's generation and are the best available account of
    # what this derived render came from.
    pmd = parent if parent and parent.get('schema') == METADATA_SCHEMA else None
    inherited: list[str] = []
    if parent is not None:
        try:
            if enhancer is None:
                cand = pmd.get('enhancer') if pmd else None
                if not isinstance(cand, dict):
                    cand = _iteration_payload_from_obj(parent)
                if isinstance(cand, dict):
                    enhancer = cand
                    inherited.append('enhancer')

            if pmd:
                if seed is None and isinstance(pmd.get('seed'), int):
                    seed = pmd['seed']
                    inherited.append('seed')
                if not loras and isinstance(pmd.get('loras'), list):
                    loras = [lora for lora in pmd['loras'] if isinstance(lora, dict)]
                    if loras:
                        inherited.append('loras')
        except Exception:
            pass

    # Unified generation attribution (board ISSUE #29): derive index/offset
    # from the FINAL payload — own or inherited — regardless of which path
    # produced the prompt text, so an inherited payload always yields
    # attribution even when the image's own chunks resolved the prompt.
    prompt_index: int | None = None
    prompt_offset: int | None = None
    try:
        if enhancer is not None:
            payload_prompt, prompt_index = _iteration_prompt_and_index(enhancer)
            prompts = enhancer.get('prompts')
            current = prompts.get('current') if isinstance(prompts, dict) else None
            if isinstance(prompt_index, int) and isinstance(current, int):
                prompt_offset = prompt_index - current
            prompt_from_payload = prompt is None and payload_prompt is not None
            if prompt_from_payload:
                prompt = payload_prompt
            if 'enhancer' in inherited and (prompt_index is not None or prompt_from_payload):
                inherited.append('generation')
        if prompt is None and pmd:
            pgen = pmd.get('generation')
            if isinstance(pgen, dict) and isinstance(pgen.get('prompt'), str) and pgen['prompt']:
                prompt = pgen['prompt']
                pi, po = pgen.get('prompt_index'), pgen.get('prompt_offset')
                prompt_index = pi if isinstance(pi, int) else None
                prompt_offset = po if isinstance(po, int) else None
                if 'generation' not in inherited:
                    inherited.append('generation')
    except Exception:
        pass

    return {
        'schema': METADATA_SCHEMA,
        'url': str(url),
        'image': {
            'width': pil.width,
            'height': pil.height,
            'size': pil.width * pil.height,
            'timestamp_created': url.stat().st_ctime,
        },
        'comfy': {'prompt_graph': prompt_graph, 'workflow': workflow},
        'enhancer': enhancer,
        'generation': {
            'prompt': prompt,
            'prompt_index': prompt_index,
            'prompt_offset': prompt_offset,
        },
        'loras': loras,
        'seed': seed,
        'parent': parent,
        'inherited': inherited,
    }


def _select_enhancer_payload(prompt_graph: dict | None, workflow: dict | None) -> dict | None:
    """Collect every copy of the 1xlasm-enhancer iteration payload embedded in
    the two ComfyUI chunks and select the authoritative one. Real renders can
    carry several copies with different attribution: the API prompt graph holds
    the raw clipspace payload (no `prompt_index`), while the metadata-enhancer
    Display node in the UI workflow chunk holds the enhancer-client envelope
    whose nested payload carries the render-stamped top-level `prompt_index`.
    A `prompt_index`-bearing copy always wins over an index-less one (#23)."""
    candidates: list[dict] = []
    if prompt_graph:
        found = _enhancer_payload_from_graph(prompt_graph)
        if found is not None:
            candidates.append(found)
    if workflow:
        candidates += _enhancer_payloads_from_workflow(workflow)
    for payload in candidates:
        if isinstance(payload.get('prompt_index'), int):
            return payload
    return candidates[0] if candidates else None


def _enhancer_payloads_from_workflow(workflow: dict) -> list[dict]:
    """Iteration payload copies embedded in the UI `workflow` chunk: the
    fbbcool metadata-enhancer `Display Any (rgthree)` node caches the
    enhancer-client envelope (payload nested inside) in its `widgets_values`.
    Scan every node's widget strings, schema_id-gated."""
    out: list[dict] = []
    for node in workflow.get('nodes', []):
        if not isinstance(node, dict):
            continue
        widgets = node.get('widgets_values') or []
        if isinstance(widgets, dict):
            widgets = list(widgets.values())
        if not isinstance(widgets, list):
            continue
        for widget in widgets:
            if isinstance(widget, str) and _ENHANCER_ITERATION_SCHEMA_PREFIX in widget:
                found = _iteration_payload_from_obj(widget)
                if found is not None:
                    out.append(found)
    return out


def _iteration_payload_from_obj(obj, depth: int = 6) -> dict | None:
    """Find a 1xlasm-enhancer iteration payload nested anywhere inside a parent
    provenance envelope (enhancer client envelope, scenes `input_data`, raw
    wrap, ...): the payload dict itself, a dict value, a list item, or a
    JSON-encoded string field. Gated on the iteration `schema_id`,
    depth-limited against pathological nesting."""
    if depth < 0:
        return None
    if isinstance(obj, dict):
        schema_id = obj.get('schema_id', '')
        if isinstance(schema_id, str) and schema_id.startswith(_ENHANCER_ITERATION_SCHEMA_PREFIX):
            return obj
        for value in obj.values():
            found = _iteration_payload_from_obj(value, depth - 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _iteration_payload_from_obj(item, depth - 1)
            if found is not None:
                return found
    elif isinstance(obj, str) and _ENHANCER_ITERATION_SCHEMA_PREFIX in obj:
        try:
            return _iteration_payload_from_obj(json.loads(obj), depth - 1)
        except (ValueError, TypeError):
            return None
    return None


def _parse_json_chunk(chunk) -> dict | None:
    """Parse a PNG text chunk into a dict; None for absent/invalid/non-dict."""
    if isinstance(chunk, dict):
        return chunk
    if not isinstance(chunk, str):
        return None
    try:
        parsed = json.loads(chunk)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def image_info_from_url(url: Path | str, include_info_ext: bool = False) -> dict | None:
    """
    Creates an info struct if image exists, otherwise returns None.

    Thin adapter over `metadata()` (same extraction, legacy flat key layout).
    The given url is stored in ['url_src'].
    """
    url = Path(url)
    pil = image_from_url(url)
    if pil is None:
        return None
    pil.load()
    md = _metadata_from_pil(url, pil)

    info = {
        'url_src': md['url'],
        'timestamp_created': md['image']['timestamp_created'],
        'width': md['image']['width'],
        'height': md['image']['height'],
        'size': md['image']['size'],
    }

    # prompt
    if md['generation']['prompt'] is not None:
        info |= {'prompt': md['generation']['prompt']}

    # loras + seed (Power Lora Loader rgthree slots only); keys present exactly
    # when the ComfyUI prompt chunk was present and parseable, as before
    if md['comfy']['prompt_graph'] is not None:
        info |= {'seed': md['seed'], 'loras': md['loras']}

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

    # Fbbcool enhancer renders (krea2/qwen graphs): the positive text is a
    # runtime output of `FbbcoolEnhancerClient`, fed from a `FbbcoolClipspace`
    # node that persists the full iteration payload in its `is_changed` field.
    # The graph walk dead-ends on that dynamic node, but the resolved prompt is
    # embedded in that payload (v3 flat `prompt`, or v4 structured
    # `prompts.prompt_data[]`). Recover it from the authoritative copy across
    # both chunks (prompt_index-bearing envelope preferred, see
    # `_select_enhancer_payload`), gated on the iteration schema_id so we never
    # pick up an unrelated embedded JSON.
    iteration = _prompt_from_enhancer_iteration(info_ext, verbose)
    if iteration:
        return iteration

    if verbose:
        print('prompt is empty')
    return None


# Marker for the 1xlasm-enhancer iteration payload embedded by FbbcoolClipspace.
# Gate the enhancer-prompt fallback on this so an unrelated embedded JSON that
# happens to carry a `prompt` key is never mistaken for the generation prompt.
_ENHANCER_ITERATION_SCHEMA_PREFIX = '1xlasm_enhancer.iteration'


def _prompt_from_iteration_payload(payload: dict) -> str | None:
    """Resolve the generation prompt from a 1xlasm-enhancer iteration payload,
    v3 or v4.

    v4 (`schema_id` == `1xlasm_enhancer.iteration.v4`): all flat prompt fields
    are retired; the prompt lives in the structured `prompts.prompt_data[]`
    list. The rendered entry is `prompt_index` (a top-level field the render
    pipeline stamps with the index actually generated) when present, else
    `prompts.current` (the enhancer's now-scene pointer, for offset-unaware
    embeds). `prompt_index`-with-`current`-fallback is the attribution contract
    agreed on board FEATURE REQ #23; each index is bounds-checked.

    v3 (legacy): the flat `prompt` field.

    Returns the prompt string, or None when neither shape yields text."""
    return _iteration_prompt_and_index(payload)[0]


def _iteration_prompt_and_index(payload: dict) -> tuple[str | None, int | None]:
    """Resolve (prompt, index) from an iteration payload. The index is the
    `prompt_data` entry the prompt came from (v4 only); v3 flat-field prompts
    and unresolvable payloads yield index None."""
    prompts = payload.get('prompts')
    if isinstance(prompts, dict):
        prompt_data = prompts.get('prompt_data')
        if isinstance(prompt_data, list) and prompt_data:
            # Ordered candidate indices per the #23 contract: the render-stamped
            # `prompt_index` first, then the enhancer's `current`; each is
            # bounds-checked so a malformed pointer falls through instead of
            # raising or returning the wrong entry.
            candidates = [
                i
                for i in (payload.get('prompt_index'), prompts.get('current'))
                if isinstance(i, int)
            ]
            for i in candidates:
                if 0 <= i < len(prompt_data):
                    entry = prompt_data[i]
                    if isinstance(entry, dict):
                        prompt = entry.get('prompt')
                        if isinstance(prompt, str) and prompt:
                            return prompt, i
    # v3 legacy flat field.
    prompt = payload.get('prompt')
    if isinstance(prompt, str) and prompt:
        return prompt, None
    return None, None


def _enhancer_payload_from_graph(data: dict) -> dict | None:
    """Find the raw 1xlasm-enhancer iteration payload (v3 or v4) embedded in a
    ComfyUI API graph. The `FbbcoolClipspace` source node keeps the whole
    iteration JSON in its `is_changed` field; older/string-input embeds carry
    it in a node string input. Scan every node for such a blob, gated on the
    iteration `schema_id` so an unrelated embedded JSON is never picked up.
    Returns the parsed payload dict, or None."""
    for node in data.values():
        if not isinstance(node, dict):
            continue
        blobs: list[str] = []
        is_changed = node.get('is_changed')
        if isinstance(is_changed, list):
            blobs += [b for b in is_changed if isinstance(b, str)]
        elif isinstance(is_changed, str):
            blobs.append(is_changed)
        blobs += [v for v in node.get('inputs', {}).values() if isinstance(v, str)]
        for blob in blobs:
            if _ENHANCER_ITERATION_SCHEMA_PREFIX not in blob:
                continue
            try:
                payload = json.loads(blob)
            except (ValueError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            schema_id = payload.get('schema_id', '')
            if isinstance(schema_id, str) and schema_id.startswith(
                _ENHANCER_ITERATION_SCHEMA_PREFIX
            ):
                return payload
    return None


def _prompt_from_enhancer_iteration(info_ext: dict, verbose=False) -> str | None:
    """Recover the positive prompt from an embedded 1xlasm-enhancer iteration
    payload: select the authoritative copy across the prompt-graph and
    workflow chunks (see `_select_enhancer_payload`) and resolve its prompt
    (v3 flat field or v4 structured `prompts.prompt_data[]`; see
    `_prompt_from_iteration_payload`)."""
    payload = _select_enhancer_payload(
        _parse_json_chunk(info_ext.get('prompt')), _parse_json_chunk(info_ext.get('workflow'))
    )
    if payload is None:
        return None
    prompt = _prompt_from_iteration_payload(payload)
    if prompt and verbose:
        print(f'enhancer-iteration prompt recovered (schema {payload.get("schema_id")})')
    return prompt


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
