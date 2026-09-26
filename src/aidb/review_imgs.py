"""Throwaway image review lists (board task 102).

One document per review list in the ``review_imgs`` collection of the active
aidb DB (``scenes_<config>``). The creator writes a list once (via
``script/review_list.py create``); afterwards the aidb app Review tab is the
only writer, filling ``items[i].response`` and the list-level ``comment``.

Lazy by design: image refs are whatever path was current at creation time,
no status/versioning/archival — a list lives until its feedback has been
processed, then it is deleted (``review_list.py delete``). Nothing here reads
or writes the canonical ``scenes`` / ``images`` / ``sets`` collections.

Schema: ``conf/review/_schema.json`` (``aitools.review_imgs.v1``), doc:
``conf/review/README.md``.
"""

from __future__ import annotations

import copy
import datetime
import json
import os
from pathlib import Path
from typing import Any, Final

from aidb.scene.db_connect import DBConnection
from aidb.scene.scene_common import SceneConfig

COLLECTION: Final = 'review_imgs'
SCHEMA_ID: Final = 'aitools.review_imgs.v1'
FIELD_TYPES: Final = ('bool', 'choice', 'multi', 'text')


def schema_path() -> Path:
    return Path(os.environ.get('CONF_AIT', './conf')).resolve() / 'review' / '_schema.json'


def load_schema() -> dict:
    with open(schema_path(), encoding='utf-8') as f:
        return json.load(f)


def now_str() -> str:
    """Local wall-clock time (CEST on the operator box), minute precision."""
    return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M')


def is_answered(response: Any) -> bool:
    """A response counts as answered once any form key holds a non-empty value."""
    if not isinstance(response, dict):
        return False
    for v in response.values():
        if v is None or v == '' or v == []:
            continue
        return True
    return False


def answered_count(doc: dict) -> tuple[int, int]:
    items = doc.get('items') or []
    return sum(1 for it in items if is_answered(it.get('response'))), len(items)


def validate_response(form: list[dict], response: Any) -> list[str]:
    """Type-check a response dict against the list's form. Empty list = valid."""
    if response is None:
        return []
    if not isinstance(response, dict):
        return ['response must be an object or null']
    errors = []
    fields = {f['key']: f for f in form}
    for key, val in response.items():
        field = fields.get(key)
        if field is None:
            errors.append(f'unknown form key {key!r}')
            continue
        if val is None:
            continue
        ftype = field['type']
        options = field.get('options') or []
        if ftype == 'bool' and not isinstance(val, bool):
            errors.append(f'{key}: bool expected')
        elif ftype == 'text' and not isinstance(val, str):
            errors.append(f'{key}: string expected')
        elif ftype == 'choice' and val != '' and val not in options:
            errors.append(f'{key}: {val!r} not in options')
        elif ftype == 'multi':
            if not isinstance(val, list) or any(v not in options for v in val):
                errors.append(f'{key}: list of options expected')
    return errors


def validate(doc: dict) -> list[str]:
    """Validate a list document (schema + cross-field rules). Empty list = valid."""
    import jsonschema  # type: ignore[import-untyped]

    validator = jsonschema.Draft202012Validator(load_schema())
    errors = [
        f'{"/".join(str(p) for p in e.absolute_path) or "<root>"}: {e.message}'
        for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    ]
    if errors:
        return errors

    keys = [f['key'] for f in doc['form']]
    if len(keys) != len(set(keys)):
        errors.append('form: duplicate keys')
    ids = [it['id'] for it in doc['items']]
    if len(ids) != len(set(ids)):
        errors.append('items: duplicate ids')
    for i, it in enumerate(doc['items']):
        errors += [
            f'items/{i}/response: {e}' for e in validate_response(doc['form'], it.get('response'))
        ]
    return errors


def normalize(doc: dict) -> dict:
    """Fill optional fields with their defaults (does not mutate the input)."""
    doc = copy.deepcopy(doc)
    doc.setdefault('created', now_str())
    doc.setdefault('created_by', None)
    doc.setdefault('show_context', False)
    doc.setdefault('comment', None)
    for field in doc['form']:
        field.setdefault('label', field['key'])
    for it in doc['items']:
        it.setdefault('context', None)
        it.setdefault('response', None)
    return doc


class ReviewImgs:
    """Manager for the ``review_imgs`` collection."""

    def __init__(
        self,
        config: SceneConfig = 'default',
        dbc: DBConnection | None = None,
        verbose: int = 1,
    ) -> None:
        self._verbose = verbose
        self._dbc = dbc if dbc is not None else DBConnection(config=config, verbose=verbose)
        col = self._dbc._get_collection(COLLECTION)
        if col is None:
            raise RuntimeError(f'no DB connection for collection {COLLECTION!r}')
        self._col = col
        self._col.create_index('list_id', unique=True)

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[review_imgs:{level}] {msg}')

    # ------------------------------------------------------------------ #
    # creator side (CLI)
    # ------------------------------------------------------------------ #
    def create(self, doc: dict, replace: bool = False) -> dict:
        """Validate + insert a list. Raises ValueError on invalid doc / existing list_id."""
        errors = validate(doc)
        if errors:
            raise ValueError('invalid review list:\n  ' + '\n  '.join(errors))
        doc = normalize(doc)
        lid = doc['list_id']
        if self._col.find_one({'list_id': lid}, {'_id': 1}) is not None:
            if not replace:
                raise ValueError(f'list_id {lid!r} already exists (use --replace)')
            self._col.delete_one({'list_id': lid})
        self._col.insert_one(dict(doc))
        self._log(f'created {lid!r} ({len(doc["items"])} items)')
        return doc

    def get(self, list_id: str) -> dict | None:
        return self._col.find_one({'list_id': list_id}, {'_id': 0})

    def delete(self, list_id: str) -> bool:
        return self._col.delete_one({'list_id': list_id}).deleted_count > 0

    def ls(self) -> list[dict]:
        """Summaries, newest first: list_id, title, created, created_by, answered, total."""
        out = []
        proj = {
            '_id': 1,
            'list_id': 1,
            'title': 1,
            'created': 1,
            'created_by': 1,
            'items.response': 1,
        }
        for doc in self._col.find({}, proj):
            answered, total = answered_count(doc)
            out.append(
                {
                    'list_id': doc.get('list_id'),
                    'title': doc.get('title'),
                    'created': doc.get('created'),
                    'created_by': doc.get('created_by'),
                    'answered': answered,
                    'total': total,
                    '_sort': (doc.get('created') or '', doc['_id'].generation_time),
                }
            )
        out.sort(key=lambda d: d['_sort'], reverse=True)
        for d in out:
            del d['_sort']
        return out

    # ------------------------------------------------------------------ #
    # app side (the only writer after creation)
    # ------------------------------------------------------------------ #
    def set_response(self, list_id: str, idx: int, item_id: str, response: dict | None) -> bool:
        """Write items[idx].response, guarded by the item's id. Invalid → False."""
        doc = self._col.find_one({'list_id': list_id}, {'form': 1})
        if doc is None:
            return False
        errors = validate_response(doc['form'], response)
        if errors:
            self._log(f'{list_id}[{idx}] rejected: {errors}', 'warning')
            return False
        res = self._col.update_one(
            {'list_id': list_id, f'items.{idx}.id': item_id},
            {'$set': {f'items.{idx}.response': response}},
        )
        return res.matched_count > 0

    def set_comment(self, list_id: str, comment: str | None) -> bool:
        res = self._col.update_one({'list_id': list_id}, {'$set': {'comment': comment or None}})
        return res.matched_count > 0
