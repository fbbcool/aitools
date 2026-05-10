"""Skin: caption-recipe configuration loaded from `conf/skins/<name>.json`.

Source fields are authored by humans; the `_built` block is composed by
`skin_build.compose_built(source)` and persisted by
`python -m ait.caption.skin_build <name>`. At load time the registry reads
the persisted `_built`; if it is missing or its `source_hash` does not match
a freshly computed hash of the source fields, an in-memory build is run
silently (so a forgotten skin_build doesn't block captioning) and a one-line
warning is logged so the author rebuilds.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final, Optional

from jsonschema import Draft202012Validator


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _conf_root() -> Path:
    return Path(os.environ.get('CONF_AIT', './conf')).resolve()


SCHEMA_PATH: Final[Path] = _conf_root() / 'skins' / '_schema.json'
SKINS_DIR: Final[Path] = _conf_root() / 'skins'


# ---------------------------------------------------------------------------
# Placeholder interpolation
# ---------------------------------------------------------------------------

class _SafeFormatDict(dict):
    """str.format_map mapping that returns `{key}` literally for missing keys.

    Used so `{hint}` survives directive/label interpolation (it is resolved at
    caption time inside JoyNG with a separate format call), while
    `{entities.primary.phrase}` and similar are filled in at build time.
    """

    def __missing__(self, key: str) -> str:  # noqa: D401
        return '{' + key + '}'


def _format_ctx(primary: 'SkinEntity', secondary: Optional['SkinEntity']) -> _SafeFormatDict:
    entities = SimpleNamespace(
        primary=SimpleNamespace(
            token=primary.token,
            phrase=primary.phrase,
        ),
        secondary=SimpleNamespace(
            token=secondary.token if secondary is not None else '',
            phrase=secondary.phrase if secondary is not None else '',
        ),
    )
    return _SafeFormatDict(entities=entities)


def interpolate(s: str, ctx: _SafeFormatDict) -> str:
    """Apply trigger-placeholder interpolation, leaving `{hint}` untouched."""
    if '{' not in s:
        return s
    return s.format_map(ctx)


# ---------------------------------------------------------------------------
# Dataclasses for source fields
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SkinLabel:
    name: str
    description: str
    expansion: str  # raw (un-interpolated) prompt template
    # Accumulating log of migration notes (each entry is a string prefixed
    # with an ISO-8601 UTC timestamp). Authoring metadata only; not surfaced
    # to the runtime. Cleared only via a manual flush (TBD).
    migration: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkinLabelGroup:
    description: str
    labels: tuple[SkinLabel, ...]  # in declaration order; names unique within group


@dataclass(frozen=True)
class SkinEntity:
    description: str
    token: str
    phrase: str
    rules: tuple[str, ...]
    forbidden: tuple[str, ...]
    label_groups: dict[str, SkinLabelGroup]


@dataclass(frozen=True)
class SkinInteraction:
    description: str
    rules: tuple[str, ...]
    forbidden: tuple[str, ...]
    label_groups: dict[str, SkinLabelGroup]


@dataclass(frozen=True)
class SkinConcept:
    name: str
    description: str = ''
    labels: tuple[str, ...] = ()
    label_prefix: tuple[str, ...] = ()
    residual: bool = False
    ignore_labels: tuple[str, ...] = ()
    ignore_label_prefix: tuple[str, ...] = ()
    target: Optional[int] = None
    sub_concepts: dict[str, 'SkinConcept'] = field(default_factory=dict)

    def matches(self, applied_labels: list[str], any_themed_matched: bool = False) -> bool:
        """Return True iff this concept's match rule fires on `applied_labels`.

        Concept rules use leaf names (`labels: ['holding']`, `label_prefix:
        ['i_']`). When a caller passes structured paths (`primary.action.holding`)
        we match against the leaf segment after the last dot; legacy bare
        names (`holding`) are matched as-is.

        For residual concepts: returns True only when no themed concept matched
        AND there is at least one applied label whose leaf is not under
        `ignore_labels` / `ignore_label_prefix`.
        """
        leaves = [l.rsplit('.', 1)[-1] for l in applied_labels]
        if self.residual:
            if any_themed_matched:
                return False
            non_ignored = [
                leaf for leaf in leaves
                if leaf not in self.ignore_labels
                and not any(leaf.startswith(p) for p in self.ignore_label_prefix)
            ]
            return bool(non_ignored)
        if self.labels and any(leaf in self.labels for leaf in leaves):
            return True
        if self.label_prefix and any(
            any(leaf.startswith(p) for p in self.label_prefix) for leaf in leaves
        ):
            return True
        return False


# ---------------------------------------------------------------------------
# Skin (full loaded recipe)
# ---------------------------------------------------------------------------

@dataclass
class Skin:
    # meta
    name: str
    version: int
    description: str
    # source (authored)
    entities_primary: SkinEntity
    entities_secondary: Optional[SkinEntity]
    interaction: Optional[SkinInteraction]
    default_prompt: str
    user_hint_preamble: str
    post_prompt: str
    body_type_words: dict[str, tuple[str, ...]]
    require_trigger_presence: bool
    concepts: dict[str, SkinConcept]
    model_key: tuple[str, str, str]
    lora_key: Optional[tuple[str, str, str]]
    default_set: Optional[str]
    # derived (from _built or in-memory composition)
    directive: str
    labels: dict[str, str]               # flat lookup, fully interpolated
    label_to_group: dict[str, str]       # 'b_muscular' -> 'primary.attribute'
    label_to_entity: dict[str, str]      # 'b_muscular' -> 'primary' / 'ass' -> 'interaction'
    forbidden: tuple[str, ...]           # union of all forbidden lists, deduplicated
    # raw source dict (for skin_build / inspection)
    source: dict[str, Any] = field(default_factory=dict)

    # ---- regex caches ----

    @cached_property
    def _forbidden_re(self) -> re.Pattern:
        if not self.forbidden:
            return re.compile(r'(?!.*)')
        pat = '|'.join(re.escape(p) for p in self.forbidden)
        return re.compile(rf'\b(?:{pat})\b', re.IGNORECASE)

    @cached_property
    def _body_type_res(self) -> dict[str, re.Pattern]:
        out: dict[str, re.Pattern] = {}
        for label, words in self.body_type_words.items():
            if not words:
                continue
            pat = '|'.join(re.escape(w) for w in words)
            out[label] = re.compile(rf'\b(?:{pat})\b', re.IGNORECASE)
        return out

    # ---- caption-time helpers ----

    def render_label_prompts(self, applied: list[str]) -> list[str]:
        """For each applied label that this skin recognizes, return its
        rendered label-prompt sentence. Output is ordered by build order
        (primary attribute → pose → action, then secondary, then interaction
        groups in declaration order). Unrecognized entries are dropped.

        `applied` may contain structured paths (`'primary.pose.front'`) and/or
        legacy leaf names (`'front'`). Path entries are looked up directly
        against `self.labels`. Legacy leaf entries are matched against the
        first path whose final segment equals the leaf — ambiguous when the
        same leaf exists in multiple groups, in which case the first match
        in build order wins.
        """
        applied_paths = {a for a in applied if a in self.labels}
        applied_leaves = {a for a in applied if a not in self.labels}
        leaves_consumed: set[str] = set()
        out: list[str] = []
        for path in self.labels:                  # iteration is build-order
            if path in applied_paths:
                out.append(self.labels[path])
                continue
            if not applied_leaves:
                continue
            leaf = path.rsplit('.', 1)[-1]
            if leaf in applied_leaves and leaf not in leaves_consumed:
                out.append(self.labels[path])
                leaves_consumed.add(leaf)   # first match wins (build order)
        return out

    def caption_violations(self, caption: str) -> list[str]:
        """Return forbidden phrases found in `caption` (empty list = clean)."""
        return [m.group(0).lower() for m in self._forbidden_re.finditer(caption)]

    def body_type_warnings(self, caption: str, applied_labels: list[str]) -> list[str]:
        """One warning per body-type word found in `caption` whose authorizing
        label is NOT in `applied_labels`.

        `applied_labels` may be bare leaf names (e.g. `'busty'`) or full
        paths (e.g. `'primary.attribute.busty'`); we match against the leaf
        segment so both forms work.
        """
        applied_leaves = {l.rsplit('.', 1)[-1] for l in applied_labels}
        warnings: list[str] = []
        for label, regex in self._body_type_res.items():
            if label in applied_leaves:
                continue
            for m in regex.finditer(caption):
                warnings.append(
                    f'caption contains "{m.group(0).lower()}" but {label} label was not set'
                )
        return warnings

    def missing_triggers(self, caption: str) -> list[str]:
        """Trigger phrases the caption is missing. Empty unless
        `require_trigger_presence` is True.
        """
        if not self.require_trigger_presence:
            return []
        lowered = caption.lower()
        missing: list[str] = []
        primary = self.entities_primary.phrase
        if primary.lower() not in lowered:
            missing.append(primary)
        if self.entities_secondary is not None:
            secondary = self.entities_secondary.phrase
            if secondary.lower() not in lowered:
                missing.append(secondary)
        return missing

    # ---- concept matching ----

    def matched_concepts(self, applied_labels: list[str]) -> dict[str, bool]:
        """{concept_name: matched_bool} for every top-level concept.

        Residual concepts are evaluated last, with `any_themed_matched` set
        based on whether any non-residual concept matched.
        """
        themed: dict[str, bool] = {}
        residual_names: list[str] = []
        for name, c in self.concepts.items():
            if c.residual:
                residual_names.append(name)
            else:
                themed[name] = c.matches(applied_labels)
        any_themed = any(themed.values())
        result: dict[str, bool] = dict(themed)
        for name in residual_names:
            result[name] = self.concepts[name].matches(applied_labels, any_themed_matched=any_themed)
        return result

    # ---- I/O ----

    @classmethod
    def from_file(cls, path: Path, *, schema: Optional[dict] = None,
                  log: Optional[callable] = None) -> 'Skin':
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data, source_path=path, schema=schema, log=log)

    @classmethod
    def from_dict(cls, data: dict, *, source_path: Optional[Path] = None,
                  schema: Optional[dict] = None,
                  log: Optional[callable] = None) -> 'Skin':
        if schema is None:
            schema = _load_schema()
        Draft202012Validator(schema).validate(data)
        if source_path is not None and data['name'] != source_path.stem:
            raise ValueError(
                f'skin name {data["name"]!r} does not match filename stem '
                f'{source_path.stem!r}'
            )

        entities_primary = _entity_from_dict(data['entities']['primary'])
        secondary_raw = data['entities'].get('secondary')
        entities_secondary = _entity_from_dict(secondary_raw) if secondary_raw else None

        interaction_raw = data.get('interaction')
        if entities_secondary is None and interaction_raw:
            raise ValueError('interaction is set but secondary entity is null')
        interaction = _interaction_from_dict(interaction_raw) if interaction_raw else None

        body_type_words = {
            k: tuple(v) for k, v in (data.get('body_type_words') or {}).items()
            if not k.startswith('_')
        }
        require_trigger_presence = bool(data.get('require_trigger_presence', False))
        concepts = {
            name: _concept_from_dict(name, c)
            for name, c in (data.get('concepts') or {}).items()
        }

        model = data['model']
        model_key = (model['group'], model['variant'], model['target'])
        lora_raw = data.get('lora')
        lora_key = (lora_raw['group'], lora_raw['variant'], lora_raw['target']) if lora_raw else None

        # _built handling
        source_hash = _compute_source_hash(data)
        built = data.get('_built')
        compose_in_memory = built is None or built.get('source_hash') != source_hash
        if compose_in_memory:
            from . import skin_build  # avoid circular at import time
            built = skin_build.compose_built(data, source_hash=source_hash, in_memory=True)
            if log is not None and source_path is not None:
                log(
                    f'_built block missing or stale for skin {data["name"]!r} '
                    f'at {source_path} — using in-memory build. Run '
                    f'`python -m ait.caption.skin_build {data["name"]}` to refresh.'
                )

        return cls(
            name=data['name'],
            version=int(data['version']),
            description=str(data.get('description', '')),
            entities_primary=entities_primary,
            entities_secondary=entities_secondary,
            interaction=interaction,
            default_prompt=str(data['default_prompt']),
            user_hint_preamble=str(data['user_hint_preamble']),
            post_prompt=str(data['post_prompt']),
            body_type_words=body_type_words,
            require_trigger_presence=require_trigger_presence,
            concepts=concepts,
            model_key=model_key,
            lora_key=lora_key,
            default_set=data.get('default_set') or None,
            directive=str(built['directive']),
            labels=dict(built['labels']),
            label_to_group=dict(built['label_to_group']),
            label_to_entity=dict(built['label_to_entity']),
            forbidden=tuple(built['forbidden']),
            source=data,
        )


# ---------------------------------------------------------------------------
# Source-dict → dataclass parsing helpers
# ---------------------------------------------------------------------------

def _entity_from_dict(d: dict) -> SkinEntity:
    return SkinEntity(
        description=str(d.get('description', '')),
        token=str(d['token']),
        phrase=str(d['phrase']),
        rules=tuple(d.get('rules') or ()),
        forbidden=tuple(d.get('forbidden') or ()),
        label_groups=_label_groups_from_dict(d.get('label_groups') or {}),
    )


def _interaction_from_dict(d: dict) -> SkinInteraction:
    return SkinInteraction(
        description=str(d.get('description', '')),
        rules=tuple(d.get('rules') or ()),
        forbidden=tuple(d.get('forbidden') or ()),
        label_groups=_label_groups_from_dict(d.get('label_groups') or {}),
    )


def _label_groups_from_dict(d: dict) -> dict[str, SkinLabelGroup]:
    out: dict[str, SkinLabelGroup] = {}
    for group_name, g in d.items():
        labels = tuple(
            SkinLabel(
                name=str(item['name']),
                description=str(item.get('description', '')),
                expansion=str(item['expansion']),
                migration=tuple(str(m) for m in (item.get('migration') or ())),
            )
            for item in g['labels']
        )
        seen: set[str] = set()
        for lab in labels:
            if lab.name in seen:
                raise ValueError(
                    f'duplicate label name {lab.name!r} within group {group_name!r}'
                )
            seen.add(lab.name)
        out[group_name] = SkinLabelGroup(
            description=str(g.get('description', '')),
            labels=labels,
        )
    return out


def _concept_from_dict(name: str, d: dict) -> SkinConcept:
    sub = {
        sub_name: _concept_from_dict(sub_name, sub_d)
        for sub_name, sub_d in (d.get('sub_concepts') or {}).items()
    }
    return SkinConcept(
        name=name,
        description=str(d.get('description', '')),
        labels=tuple(d.get('labels') or ()),
        label_prefix=tuple(d.get('label_prefix') or ()),
        residual=bool(d.get('residual', False)),
        ignore_labels=tuple(d.get('ignore_labels') or ()),
        ignore_label_prefix=tuple(d.get('ignore_label_prefix') or ()),
        target=int(d['target']) if 'target' in d else None,
        sub_concepts=sub,
    )


# ---------------------------------------------------------------------------
# Source hashing
# ---------------------------------------------------------------------------

def _source_only(data: dict) -> dict:
    """Return `data` with the `_built` block stripped (so its content does not
    affect the hash)."""
    return {k: v for k, v in data.items() if k != '_built'}


def _compute_source_hash(data: dict) -> str:
    src = _source_only(data)
    payload = json.dumps(src, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return 'sha256:' + hashlib.sha256(payload.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

_SCHEMA_CACHE: Optional[dict] = None


def _load_schema() -> dict:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        with open(SCHEMA_PATH) as f:
            _SCHEMA_CACHE = json.load(f)
    return _SCHEMA_CACHE


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class SkinRegistry:
    """Loads skins from `conf/skins/<name>.json`. Caches by name."""

    def __init__(self, srcdir: Optional[Path] = None, *, log: Optional[callable] = None):
        self.srcdir = (srcdir or SKINS_DIR).resolve()
        self._cache: dict[str, Skin] = {}
        self._log = log

    def get(self, name: str) -> Skin:
        if name not in self._cache:
            path = self.srcdir / f'{name}.json'
            self._cache[name] = Skin.from_file(path, log=self._log)
        return self._cache[name]

    def names(self) -> list[str]:
        return sorted(
            p.stem for p in self.srcdir.glob('*.json')
            if not p.stem.startswith('_')
        )

    def reload(self) -> None:
        self._cache.clear()


# ---------------------------------------------------------------------------
# Labels-NG migration helper
# ---------------------------------------------------------------------------

# Curated rename history from the legacy `labels` vocabulary to current
# `labels_ng` paths. Used by the migration to translate existing SceneImages
# whose `labels` field still carries the pre-rename names. The legacy `labels`
# field is never modified.
LEGACY_NAME_TO_PATH: Final[dict[str, str]] = {
    # body attributes (woman) — `b_` prefix dropped
    'b_muscular': 'primary.attribute.muscular',
    'b_busty':    'primary.attribute.busty',
    'b_slim':     'primary.attribute.slim',
    'b_curvy':    'primary.attribute.curvy',
    'b_hairy':    'primary.attribute.hairy',
    # poses (woman) — `woman_` prefix dropped
    'woman_front':   'primary.pose.front',
    'woman_back':    'primary.pose.back',
    'woman_side':    'primary.pose.side',
    'woman_sitting': 'primary.pose.sitting',
    'woman_on_back': 'primary.pose.on_back',
    # poses (man) — `man_` prefix dropped
    'man_front':   'secondary.pose.front',
    'man_back':    'secondary.pose.back',
    'man_side':    'secondary.pose.side',
    'man_sitting': 'secondary.pose.sitting',
    'man_on_back': 'secondary.pose.on_back',
    # the on-body-part variant of "sitting" was renamed to `perched` to free
    # the `sitting` leaf for the simple seated pose (was `man_sitting`).
    'sitting':     'secondary.pose.perched',
    # insertions — `i_` prefix dropped (the interaction.insertion group
    # already encodes the insertion semantic).
    'i_breasts_body': 'interaction.insertion.breasts_body',
    'i_breasts_head': 'interaction.insertion.breasts_head',
    'i_breasts_low':  'interaction.insertion.breasts_low',
    'i_breasts_up':   'interaction.insertion.breasts_up',
    'i_vagina_low':   'interaction.insertion.vagina_low',
    'i_vagina_up':    'interaction.insertion.vagina_up',
    'i_vagina_head':  'interaction.insertion.vagina_head',
    'i_ass_low':      'interaction.insertion.ass_low',
    'i_ass_up':       'interaction.insertion.ass_up',
    'i_ass_head':     'interaction.insertion.ass_head',
    'i_mouth_body':   'interaction.insertion.mouth_body',
    'i_mouth_head':   'interaction.insertion.mouth_head',
    'i_mouth_low':    'interaction.insertion.mouth_low',
    'i_mouth_up':     'interaction.insertion.mouth_up',
}


def compute_labels_ng(
    legacy_labels: list[str],
    skin: Skin,
) -> tuple[list[str], list[str]]:
    """Translate legacy label names into structured label-paths under `skin`.

    Returns `(paths, unknown)` where:
      - `paths` is a list of structured paths like `'primary.attribute.muscular'`
        — first via `LEGACY_NAME_TO_PATH`, then by direct path lookup, then
        by leaf-name lookup against the skin's groups.
      - `unknown` is the subset of legacy labels that did not resolve.
    """
    # Build a leaf -> path index for fallback lookups (single match only).
    leaf_to_paths: dict[str, list[str]] = {}
    for path in skin.labels:
        leaf = path.rsplit('.', 1)[-1]
        leaf_to_paths.setdefault(leaf, []).append(path)

    paths: list[str] = []
    unknown: list[str] = []
    for legacy in legacy_labels:
        # 1) explicit rename map
        if legacy in LEGACY_NAME_TO_PATH:
            target = LEGACY_NAME_TO_PATH[legacy]
            if target in skin.labels:
                paths.append(target)
                continue
        # 2) already a path under the current skin
        if legacy in skin.labels:
            paths.append(legacy)
            continue
        # 3) leaf-name lookup (only when unambiguous)
        candidates = leaf_to_paths.get(legacy, [])
        if len(candidates) == 1:
            paths.append(candidates[0])
            continue
        unknown.append(legacy)
    return paths, unknown
