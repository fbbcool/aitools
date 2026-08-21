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
                                            # own copy = API prompt-graph embed
                                            # (queue-time input, this run's
                                            # truth); a parent-envelope copy
                                            # bearing the execution-time
                                            # `prompt_index` supersedes an
                                            # index-less own copy (#30)
          'generation': {
              'prompt': str | None,         # identified positive prompt
              'prompt_index': int | None,   # v4 rendered entry: stamped
                                            # prompt_index, else current +
                                            # queue-time `prompt_offset` graph
                                            # input, else prompts.current;
                                            # v3/plain None
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

    Trust (board ISSUE #30): "own data" means the API prompt-graph chunk —
    queue-time inputs (FbbcoolClipspace `is_changed`, node string inputs)
    are this run's values. Workflow-chunk display-widget copies (rgthree
    Display nodes: the enhancer-json envelope, the 'string pos' marker) are
    serialized one run STALE by construction and are never used on
    payload-bearing renders — neither for attribution nor for the prompt
    text; display caches only serve renders without any payload.

    Inheritance: when the image's own trustworthy chunks don't yield a field
    but a `parent` envelope is present, the field is recovered from the
    parent — a round-tripped `ait.image.metadata.v1` dict contributes
    `enhancer`, `generation`, `seed` and `loras` (the parent image's account,
    gap-fill only); any other envelope shape (enhancer client envelope,
    scenes `input_data`, raw wrap) is written at execution time of THIS
    render, so its embedded iteration payload both fills a missing payload
    and supersedes an index-less own copy with the truly rendered
    `prompt_index`. Stored-mode renders (clipspace input = source-image PATH,
    no embedded payload at all) recover the payload by following that
    queue-time reference through the source chain to the first file that
    embeds it, with this render's `prompt_offset` applied. Own trustworthy
    data always wins; inherited fields are listed in `inherited`; the
    `parent` envelope itself stays verbatim.
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

    # Own trustworthy payload copy: the API prompt graph ONLY. Queue-time
    # inputs (FbbcoolClipspace `is_changed`, node string inputs) are this run's
    # values; workflow-chunk display-widget copies show the PREVIOUS run when
    # the graph is serialized and never count as own attribution (board #30).
    enhancer = _enhancer_payload_from_graph(prompt_graph) if prompt_graph else None

    # Rendered-index attribution from own data: a stamped `prompt_index` on the
    # payload wins; otherwise derive it from the enhancer client's queue-time
    # `prompt_offset` INPUT (also this run's truth) + the payload's `current`.
    own_index = _rendered_index_from_graph(enhancer, prompt_graph) if enhancer else None

    parent = _parse_json_chunk(info_ext.get(PARENT_METADATA_CHUNK))
    # Round-tripped metadata() dict (SmartInput `metadata` output) — its fields
    # describe the PARENT's generation: gap-fill only, never an override.
    pmd = parent if parent and parent.get('schema') == METADATA_SCHEMA else None
    # Any other envelope shape (enhancer-client envelope, scenes `input_data`,
    # raw wrap) was written at execution time of THIS render by the preview
    # node — an embedded payload there carries the truly rendered
    # `prompt_index`.
    parent_payload: dict | None = None
    if parent is not None and pmd is None:
        try:
            parent_payload = _iteration_payload_from_obj(parent)
        except Exception:
            parent_payload = None

    inherited: list[str] = []
    if enhancer is None:
        cand = parent_payload
        if cand is None and pmd:
            c = pmd.get('enhancer')
            cand = c if isinstance(c, dict) else _iteration_payload_from_obj(pmd)
        if cand is None and prompt_graph:
            # Stored-mode renders: the clipspace input is the SOURCE IMAGE
            # PATH (queue-time), the payload only lives at the root of that
            # source chain. This run's `prompt_offset` applies to it.
            cand = _enhancer_payload_from_source_chain(prompt_graph)
            if cand is not None:
                own_index = _rendered_index_from_graph(cand, prompt_graph)
        if cand is not None:
            enhancer = cand
            inherited.append('enhancer')
    elif (
        parent_payload is not None
        and own_index is None
        and isinstance(parent_payload.get('prompt_index'), int)
    ):
        # Own copy is a raw clipspace payload with no resolvable index; the
        # parent envelope is the execution-time stamped account of the same
        # run — it wins (#30).
        enhancer = parent_payload
        inherited.append('enhancer')

    # Generation attribution AND prompt from the final payload — own or
    # inherited (board #29/#30). On payload-governed renders the payload is the
    # only trustworthy prompt source: display caches ('string pos' included)
    # are one run stale, so they must not outrank it.
    prompt: str | None = None
    prompt_index: int | None = None
    prompt_offset: int | None = None
    try:
        if enhancer is not None:
            # own_index is only ever set for queue-time-anchored payloads
            # (own graph copy or source-chain root + this run's offset).
            prompt, prompt_index = _iteration_prompt_and_index(enhancer, own_index)
            prompts = enhancer.get('prompts')
            current = prompts.get('current') if isinstance(prompts, dict) else None
            if isinstance(prompt_index, int) and isinstance(current, int):
                prompt_offset = prompt_index - current
            if 'enhancer' in inherited and (prompt_index is not None or prompt is not None):
                inherited.append('generation')
    except Exception:
        pass

    if prompt is None:
        # Renders without a resolvable payload: legacy graph paths — named
        # display marker, positive walk, display-cache fallback.
        try:
            prompt = _image_extract_prompt_from_info_ext(info_ext, verbose=False)
        except Exception:
            pass

    if prompt is None and pmd:
        try:
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

    seed: int | None = None
    loras: list[dict] = []
    try:
        loras_info = _image_extract_loras_from_info_ext(info_ext)
    except Exception:
        loras_info = None
    if loras_info is not None:
        seed = loras_info['seed']
        loras = loras_info['loras']
    if pmd:
        try:
            if seed is None and isinstance(pmd.get('seed'), int):
                seed = pmd['seed']
                inherited.append('seed')
            if not loras and isinstance(pmd.get('loras'), list):
                loras = [lora for lora in pmd['loras'] if isinstance(lora, dict)]
                if loras:
                    inherited.append('loras')
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

    # Fbbcool enhancer renders (krea2/qwen graphs): the `FbbcoolClipspace`
    # source node persists the full iteration payload in its `is_changed`
    # field — a queue-time INPUT, i.e. this run's value. It outranks every
    # display-cache path below: display widgets (the 'string pos' marker
    # included) are serialized one run stale (board #30), so on
    # payload-bearing renders they show the previous run's prompt.
    iteration = _prompt_from_enhancer_iteration(info_ext, verbose)
    if iteration:
        return iteration

    # A `Display Any (rgthree)` node titled 'string pos' is an explicit,
    # hand-placed marker of the final positive prompt: on payload-less
    # renders its cached value defines the prompt and wins over the graph
    # walk.
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


def _iteration_prompt_and_index(
    payload: dict, index_hint: int | None = None
) -> tuple[str | None, int | None]:
    """Resolve (prompt, index) from an iteration payload. The index is the
    `prompt_data` entry the prompt came from (v4 only); v3 flat-field prompts
    and unresolvable payloads yield index None. `index_hint` is a rendered
    index derived outside the payload (queue-time `prompt_offset` graph input
    + `current`, board #30) — it ranks between the stamped `prompt_index` and
    the `current` fallback."""
    prompts = payload.get('prompts')
    if isinstance(prompts, dict):
        prompt_data = prompts.get('prompt_data')
        if isinstance(prompt_data, list) and prompt_data:
            # Ordered candidate indices per the #23 contract: the render-stamped
            # `prompt_index` first, then the derived hint, then the enhancer's
            # `current`; each is bounds-checked so a malformed pointer falls
            # through instead of raising or returning the wrong entry.
            candidates = [
                i
                for i in (payload.get('prompt_index'), index_hint, prompts.get('current'))
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


def _rendered_index_from_graph(payload: dict, prompt_graph: dict | None) -> int | None:
    """Rendered `prompt_data` index for a queue-time-anchored payload: the
    stamped `prompt_index` when present, else the payload's `current` + the
    enhancer client's queue-time `prompt_offset` graph input (board #30)."""
    pi = payload.get('prompt_index')
    if isinstance(pi, int):
        return pi
    offset = _prompt_offset_from_graph(prompt_graph) if prompt_graph else None
    prompts = payload.get('prompts')
    current = prompts.get('current') if isinstance(prompts, dict) else None
    if isinstance(offset, int) and isinstance(current, int):
        return current + offset
    return None


def _source_image_path_from_graph(data: dict) -> Path | None:
    """The queue-time source-image reference of a stored-mode render: the
    `FbbcoolClipspace` node's `is_changed`/input holds the PATH of the image
    the payload was resolved from at execution time (instead of the payload
    JSON itself). Returns the first existing image path, or None."""
    for node in data.values():
        if not isinstance(node, dict) or node.get('class_type') != 'FbbcoolClipspace':
            continue
        cands: list[str] = []
        is_changed = node.get('is_changed')
        if isinstance(is_changed, list):
            cands += [c for c in is_changed if isinstance(c, str)]
        elif isinstance(is_changed, str):
            cands.append(is_changed)
        cands += [v for v in (node.get('inputs') or {}).values() if isinstance(v, str)]
        for cand in cands:
            if _ENHANCER_ITERATION_SCHEMA_PREFIX in cand:
                continue
            path = Path(cand)
            if is_img(path) and path.is_file():
                return path
    return None


def _enhancer_payload_from_source_chain(data: dict, max_depth: int = 8) -> dict | None:
    """Recover the iteration payload of a stored-mode render (board #30
    follow-up): its own graph carries only the queue-time source-image PATH.
    Follow that reference — transitively, since the source may itself be a
    stored-mode render — to the first file whose own chunks embed the payload
    (prompt-graph copy, else `parent_metadata` envelope). Depth-capped and
    cycle-guarded; any unreadable link ends the walk (honest None)."""
    seen: set[str] = set()
    graph: dict | None = data
    for _ in range(max_depth):
        path = _source_image_path_from_graph(graph) if graph else None
        if path is None or str(path) in seen:
            return None
        seen.add(str(path))
        try:
            pil = PILImage.open(path)
            pil.load()
        except Exception:
            return None
        info = pil.info or {}
        graph = _parse_json_chunk(info.get('prompt'))
        if graph:
            payload = _enhancer_payload_from_graph(graph)
            if payload is not None:
                return payload
        parent = _parse_json_chunk(info.get(PARENT_METADATA_CHUNK))
        if parent:
            payload = _iteration_payload_from_obj(parent)
            if payload is not None:
                return payload
    return None


def _prompt_offset_from_graph(data: dict) -> int | None:
    """The enhancer client's `prompt_offset` INPUT from the API prompt graph —
    a queue-time value, i.e. this run's truth (unlike display widgets, board
    #30). Either a literal on the client node or a link to an int-primitive
    node (e.g. `PrimitiveInt`, whose queue-time `value` input is resolved)."""
    for node in data.values():
        if not isinstance(node, dict) or node.get('class_type') != 'FbbcoolEnhancerClient':
            continue
        offset = (node.get('inputs') or {}).get('prompt_offset')
        if isinstance(offset, int):
            return offset
        if isinstance(offset, list) and offset:
            src = data.get(str(offset[0]))
            src_inputs = src.get('inputs') if isinstance(src, dict) else None
            if isinstance(src_inputs, dict):
                value = src_inputs.get('value')
                if isinstance(value, int):
                    return value
                int_inputs = [v for v in src_inputs.values() if isinstance(v, int)]
                if len(int_inputs) == 1:
                    return int_inputs[0]
    return None


def _prompt_from_enhancer_iteration(info_ext: dict, verbose=False) -> str | None:
    """Recover the positive prompt from the trustworthy embedded 1xlasm-enhancer
    iteration payload: the API prompt-graph copy only (queue-time input, see
    `_enhancer_payload_from_graph`). Workflow-chunk display-widget copies are
    one run stale by construction and are never consulted (board ISSUE #30).
    Prompt resolution is v3 flat field or v4 structured `prompts.prompt_data[]`
    (see `_prompt_from_iteration_payload`)."""
    prompt_graph = _parse_json_chunk(info_ext.get('prompt'))
    payload = _enhancer_payload_from_graph(prompt_graph) if prompt_graph else None
    if payload is None and prompt_graph:
        payload = _enhancer_payload_from_source_chain(prompt_graph)
    if payload is None:
        return None
    # Same rendered-index derivation as metadata(): stamped index, else
    # queue-time `prompt_offset` graph input + the payload's `current`.
    hint = _rendered_index_from_graph(payload, prompt_graph)
    prompt = _iteration_prompt_and_index(payload, hint)[0]
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


EMBED_MODEL_DEFAULT: Final = 'dinov2:small'
# batches above this size auto-select the GPU (operator directive 2026-08-21);
# dinov2-small's footprint is small enough to coexist with a running ComfyUI
EMBED_GPU_MIN_BATCH: Final = 3

# stored-embedding payload: a PNG tEXt chunk named 'embedding-<group>-<variant>'
# (e.g. 'embedding-dinov2-small') carrying schema_id + the normalized vector,
# so re-embedding a stored file is a chunk read instead of an inference pass
EMBEDDING_SCHEMA: Final = 'ait.image.embedding.v1'
EMBED_CHUNK_PREFIX: Final = 'embedding-'

_PNG_SIG: Final = b'\x89PNG\r\n\x1a\n'


def _embed_chunk_key(model: str) -> str:
    return EMBED_CHUNK_PREFIX + model.replace(':', '-')


def _embedding_payload_parse(raw, model: str):
    """Stored embedding chunk -> normalized float32 numpy vector, or None on
    any mismatch (schema, model, malformed vector) — never raises."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get('schema_id') != EMBEDDING_SCHEMA:
        return None
    if data.get('model') != model:
        return None
    vec = data.get('vector')
    if not isinstance(vec, list) or not vec:
        return None
    import numpy as np

    try:
        v = np.asarray(vec, dtype=np.float32)
    except (TypeError, ValueError):
        return None
    norm = float(np.linalg.norm(v))
    if v.ndim != 1 or not np.isfinite(norm) or norm == 0.0:
        return None
    return v / norm


def _png_text_chunk_upsert(url: Path, key: str, text: str) -> bool:
    """Insert/replace one tEXt chunk in a PNG *without re-encoding*: IDAT and
    every other chunk (prompt graph, workflow, parent_metadata provenance)
    stay byte-identical; a stale chunk under the same key is replaced. Atomic
    via temp file + rename. Returns False (no write) on any non-PNG input."""
    import struct
    import zlib

    try:
        raw = url.read_bytes()
    except OSError:
        return False
    if not raw.startswith(_PNG_SIG):
        return False

    keyb = key.encode('latin-1')
    data = keyb + b'\x00' + text.encode('latin-1')
    new_chunk = (
        struct.pack('>I', len(data))
        + b'tEXt'
        + data
        + struct.pack('>I', zlib.crc32(b'tEXt' + data))
    )

    out = bytearray(_PNG_SIG)
    pos = len(_PNG_SIG)
    inserted = False
    while pos + 12 <= len(raw):
        (length,) = struct.unpack('>I', raw[pos : pos + 4])
        ctype = raw[pos + 4 : pos + 8]
        chunk = raw[pos : pos + 12 + length]
        pos += 12 + length
        if ctype == b'tEXt' and chunk[8:].startswith(keyb + b'\x00'):
            continue
        # before the first IDAT, so PIL surfaces the chunk on open() without a
        # full pixel load (post-IDAT text only appears after .load())
        if ctype in (b'IDAT', b'IEND') and not inserted:
            out += new_chunk
            inserted = True
        out += chunk
    if not inserted:
        return False

    tmp = url.with_name(url.name + '.tmp_embed')
    try:
        tmp.write_bytes(out)
        tmp.replace(url)
    except OSError:
        tmp.unlink(missing_ok=True)
        return False
    return True


def _embedding_store(url: Path, key: str, model: str, vector) -> bool:
    """Persist a computed vector into the image file as its model-keyed
    embedding payload. PNG only — other formats are silently skipped."""
    if url.suffix.lower() != '.png':
        return False
    payload = json.dumps(
        {
            'schema_id': EMBEDDING_SCHEMA,
            'model': model,
            'dim': int(vector.shape[0]),
            'vector': [float(x) for x in vector],
        }
    )
    return _png_text_chunk_upsert(url, key, payload)


# lazy per-model cache: {(model, device): (processor, model_instance)} — one load
# per process, so a batch call never reloads the model per image (board task 67)
_embed_models: dict = {}


def _embed_model(model: str, device: str):
    key = (model, device)
    cached = _embed_models.get(key)
    if cached is not None:
        return cached
    # imported lazily: metadata()/thumbnail consumers must not pay the torch
    # import (nor the model download) unless embeddings are actually used
    from transformers import AutoImageProcessor, AutoModel
    from transformers.utils import logging as hf_logging

    from ait.install import snapshot_from_db

    # agent-facing call: keep load-time progress bars/info off stderr
    hf_logging.set_verbosity_error()
    hf_logging.disable_progress_bar()

    # 'group:variant' spec against the conf/models DB (conf/models/models_dinov2.json)
    group, _, variant = model.partition(':')
    local_dir = snapshot_from_db(group, variant or 'common')

    processor = AutoImageProcessor.from_pretrained(local_dir)
    instance = AutoModel.from_pretrained(local_dir).to(device).eval()
    _embed_models[key] = (processor, instance)
    return processor, instance


def embed(
    urls: list[str | Path] | str | Path,
    model: str = EMBED_MODEL_DEFAULT,
    device: str | None = None,
    batch_size: int = 16,
    store: bool = False,
    refresh: bool = False,
) -> list:
    """Batched semantic image embeddings for similarity/dedup/grouping.

    Input: image path(s) (any format `is_img` accepts — png/jpg/webp/gif).
    Output: one L2-normalized float32 numpy vector per input, order matching
    the input; an unreadable/missing file yields ``None`` in its slot
    (consistent with `metadata()`), never an exception. Cosine similarity of
    two results is their plain dot product.

    ``model`` is a ``group:variant`` key into the layered `conf/models` DB
    (`conf/models/models_dinov2.json`); the default ``dinov2:small`` gives
    384-dim vectors, ``dinov2:base`` swaps in the bigger variant — new
    variants are added in the JSON, not in code. Files are materialized via
    the ait downloader (`ait.install.snapshot_from_db`), loaded once per
    process and cached; a call processes the whole list in ``batch_size``
    chunks — no per-image model loads.

    Stored payloads: a PNG may carry its embedding in a
    ``embedding-<group>-<variant>`` tEXt chunk (e.g. ``embedding-dinov2-small``,
    schema ``ait.image.embedding.v1``). Such a payload is used instead of
    inference whenever the model matches — a fully stored batch never loads
    the model. ``store=True`` writes freshly computed vectors back into their
    PNG files (chunk-level insert, image data and every other chunk stay
    byte-identical; non-PNG inputs are skipped). ``refresh=True`` ignores
    stored payloads and recomputes (rewriting them when ``store``). NOTE:
    storing changes the file's bytes — a stored copy no longer byte-matches
    an unstored one (relevant for `SceneManager.scene_adopt_img` idempotence).

    ``device=None`` auto-selects: when more than ``EMBED_GPU_MIN_BATCH``
    images actually need inference, the GPU is used when available, else CPU
    (model footprint is small enough to coexist with a running ComfyUI).
    An explicit ``device`` ('cpu'/'cuda') always wins.
    """
    if not isinstance(urls, list):
        urls = [urls]

    paths = [Path(url) for url in urls]
    vectors: list = [None] * len(paths)
    pils: dict[int, PILImage.Image] = {
        i: pil for i, path in enumerate(paths) if (pil := image_from_url(path)) is not None
    }
    if not pils:
        return vectors

    chunk_key = _embed_chunk_key(model)
    todo = list(pils)
    if not refresh:
        todo = []
        for i, pil in pils.items():
            stored = _embedding_payload_parse(pil.info.get(chunk_key), model)
            if stored is None:
                todo.append(i)
            else:
                vectors[i] = stored

    if todo:
        import torch

        if device is None:
            use_gpu = len(todo) > EMBED_GPU_MIN_BATCH and torch.cuda.is_available()
            device = 'cuda' if use_gpu else 'cpu'

        processor, instance = _embed_model(model, device)
        for start in range(0, len(todo), batch_size):
            chunk = todo[start : start + batch_size]
            imgs = [pils[i].convert('RGB') for i in chunk]
            inputs = processor(images=imgs, return_tensors='pt').to(device)
            with torch.no_grad():
                out = instance(**inputs)
            # CLS token — DINOv2's global image descriptor
            cls = torch.nn.functional.normalize(out.last_hidden_state[:, 0], dim=-1)
            for j, i in enumerate(chunk):
                vectors[i] = cls[j].cpu().numpy()

    if store:
        for i in todo:
            if vectors[i] is not None:
                _embedding_store(paths[i], chunk_key, model, vectors[i])
    return vectors


def embed_stored(
    urls: list[str | Path] | str | Path,
    model: str = EMBED_MODEL_DEFAULT,
) -> list:
    """Read stored embedding payloads only — never computes.

    Same list contract as `embed()`: one L2-normalized float32 numpy vector
    per input, order matching; ``None`` for a file that is unreadable or
    carries no stored payload for ``model`` (chunk
    ``embedding-<group>-<variant>``, schema ``ait.image.embedding.v1``).
    No torch, no model load, no GPU — a pure chunk read, safe on boxes
    without the ML stack. Use it to consume `embed(..., store=True)` results
    cheaply or to check cache coverage before a compute pass.
    """
    if not isinstance(urls, list):
        urls = [urls]
    chunk_key = _embed_chunk_key(model)
    vectors: list = []
    for url in urls:
        pil = image_from_url(url)
        raw = pil.info.get(chunk_key) if pil is not None else None
        vectors.append(_embedding_payload_parse(raw, model))
    return vectors
