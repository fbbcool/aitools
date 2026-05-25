"""Skin build phase.

Reads source fields from a `conf/skins/<name>.json`, composes the derived
`_built` block (directive, flat labels, reverse indices, union forbidden,
source_hash, built_at), and writes the result back to the same file.

CLI:
    python -m ait.caption.skin_build <name>

Library entry:
    compose_built(source_dict) -> built_dict
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator


# All skin timestamps are emitted in CET/CEST (Europe/Berlin) with seconds
# precision, e.g. `2026-05-10T20:30:42+02:00`. Authoring metadata, not
# anything reproducibility-critical.
_TS_ZONE = ZoneInfo('Europe/Berlin')


def _now_cet_iso() -> str:
    return datetime.datetime.now(_TS_ZONE).isoformat(timespec='seconds')

from .skin import (
    SKINS_DIR,
    _SafeFormatDict,
    _compute_source_hash,
    _load_schema,
)


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def compose_built(
    data: dict,
    *,
    source_hash: Optional[str] = None,
    in_memory: bool = False,
) -> dict[str, Any]:
    """Compose the `_built` block from source fields.

    Returns a dict with: version, built_at, source_hash, directive, labels,
    label_to_group, label_to_entity, forbidden.

    Pure: same source produces the same output (modulo `built_at`).
    """
    # Interpolation context
    primary_d = data['entities']['primary']
    secondary_d = data['entities'].get('secondary')
    ctx_entities = SimpleNamespace(
        primary=SimpleNamespace(
            token=primary_d['token'],
            phrase=primary_d['phrase'],
        ),
        secondary=SimpleNamespace(
            token=secondary_d['token'] if secondary_d else '',
            phrase=secondary_d['phrase'] if secondary_d else '',
        ),
    )
    ctx = _SafeFormatDict(entities=ctx_entities)

    interp = lambda s: s.format_map(ctx) if '{' in s else s

    # ---- Directive (composed prose) ----
    parts: list[str] = []
    if secondary_d:
        parts.append(
            f'This image features two figures together: a '
            f'{primary_d["phrase"]} and a {secondary_d["phrase"]}.'
        )
    else:
        parts.append(f'This image features one figure: a {primary_d["phrase"]}.')

    def _entity_paragraph(ed: dict) -> str:
        bits: list[str] = []
        desc = (ed.get('description') or '').strip()
        if desc:
            bits.append(interp(desc))
        for rule in ed.get('rules') or ():
            bits.append(interp(rule).strip())
        return ' '.join(bits)

    primary_para = _entity_paragraph(primary_d)
    if primary_para:
        parts.append(primary_para)

    if secondary_d:
        secondary_para = _entity_paragraph(secondary_d)
        if secondary_para:
            parts.append(secondary_para)

    interaction_d = data.get('interaction')
    if interaction_d and secondary_d:
        bits: list[str] = []
        idesc = (interaction_d.get('description') or '').strip()
        if idesc:
            bits.append(interp(idesc))
        for rule in interaction_d.get('rules') or ():
            bits.append(interp(rule).strip())
        if bits:
            parts.append(' '.join(bits))

    directive = '\n\n'.join(parts)

    # ---- Flat labels lookup + reverse indices ----
    labels: dict[str, str] = {}
    label_to_group: dict[str, str] = {}
    label_to_entity: dict[str, str] = {}

    # Cross-group uniqueness is enforced on the FULL PATH (e.g.
    # `primary.pose.front`), not on the leaf name. Two groups may carry the
    # same leaf name (e.g. primary.pose.front + secondary.pose.front); the
    # path disambiguates and labels_ng on a SceneImage stores the path.
    def _consume(group_owner: str, entity_tag: str, groups_d: dict) -> None:
        for group_name, group in (groups_d or {}).items():
            for item in group.get('labels') or ():
                leaf = item['name']
                expansion = item['expansion']
                path = f'{group_owner}.{group_name}.{leaf}'
                if path in labels:
                    raise ValueError(f'duplicate label path {path!r}')
                labels[path] = interp(expansion)
                label_to_group[path] = f'{group_owner}.{group_name}'
                label_to_entity[path] = entity_tag

    _consume('primary', 'primary', primary_d.get('label_groups') or {})
    if secondary_d:
        _consume('secondary', 'secondary', secondary_d.get('label_groups') or {})
    if interaction_d and secondary_d:
        _consume('interaction', 'interaction', interaction_d.get('label_groups') or {})

    # ---- Union forbidden (preserve first-seen order, deduplicate) ----
    seen: set[str] = set()
    forbidden: list[str] = []
    for src in [
        primary_d.get('forbidden') or (),
        (secondary_d or {}).get('forbidden') or (),
        ((interaction_d or {}).get('forbidden') or ()) if (interaction_d and secondary_d) else (),
    ]:
        for term in src:
            if term not in seen:
                seen.add(term)
                forbidden.append(term)

    # ---- Standalone (1xlasm-style skins only) ----
    # Optional: skins that ship a generation-mode directive (script/img_caption.py)
    # carry a top-level `standalone` block; resolve {entities.*} placeholders
    # at build time, leave {hint} untouched (caller-side runtime slot).
    standalone_src = data.get('standalone')
    standalone_built: Optional[dict] = None
    if standalone_src is not None:
        standalone_built = {
            'directive_head':    interp(standalone_src['directive_head']),
            'emphasis_preamble': interp(standalone_src['emphasis_preamble']),
            'hint_preamble':     interp(standalone_src['hint_preamble']),
            'directive_tail':    interp(standalone_src['directive_tail']),
        }
        desc = standalone_src.get('description')
        if desc is not None:
            standalone_built['description'] = desc

    # ---- Hash + timestamp ----
    if source_hash is None:
        source_hash = _compute_source_hash(data)
    built_at = _now_cet_iso()

    built: dict[str, Any] = {
        'version':         1,
        'built_at':        built_at,
        'source_hash':     source_hash,
        'directive':       directive,
        'labels':          labels,
        'label_to_group':  label_to_group,
        'label_to_entity': label_to_entity,
        'forbidden':       forbidden,
    }
    if standalone_built is not None:
        built['standalone'] = standalone_built
    return built


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_file(path: Path) -> None:
    with open(path) as f:
        data = json.load(f)

    schema = _load_schema()
    Draft202012Validator(schema).validate(data)

    if data['name'] != path.stem:
        raise ValueError(
            f'skin name {data["name"]!r} does not match filename stem '
            f'{path.stem!r}'
        )

    built = compose_built(data)
    data['_built'] = built

    # Write back, preserving key order, with trailing newline.
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f'wrote _built for {data["name"]!r} ({len(built["labels"])} labels, '
          f'{len(built["forbidden"])} forbidden, '
          f'{len(built["directive"])} chars directive) -> {path}')


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print('usage: python -m ait.caption.skin_build <skin_name>...', file=sys.stderr)
        return 1
    for name in args:
        path = SKINS_DIR / f'{name}.json'
        if not path.exists():
            print(f'no such skin: {path}', file=sys.stderr)
            return 2
        _build_file(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
