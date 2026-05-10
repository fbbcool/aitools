"""Migrate SceneImage labels into the new structured `labels_ng` field.

For each SceneImage in the active database:
  1. Read the legacy `labels` array (FIELD_LABELS) — left untouched.
  2. Translate each legacy label into a structured path
     (`<entity_or_interaction>.<group>.<name>`) under the chosen skin.
     Body-attribute labels with the legacy `b_` prefix resolve to their
     renamed un-prefixed form (`b_muscular` -> `muscular`, etc.).
  3. Set `labels_ng` (FIELD_LABELS_NG) on the document.

Run:
  python script/migrate_labels_ng.py [--config prod|test] [--skin 1xlasm] [--dry-run]

The `labels` field is never modified. Re-running the migration is idempotent.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

# allow running from repo root with `python script/migrate_labels_ng.py`
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
os.environ.setdefault('CONF_AIT', str(REPO / 'conf'))

from ait.caption.skin import SkinRegistry, compute_labels_ng
from aidb.scene.db_connect import DBConnection
from aidb.scene.scene_common import SceneDef


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    parser.add_argument('--config', default='prod', choices=['prod', 'test', 'default'],
                        help='AIDB scene config (default: prod).')
    parser.add_argument('--skin', default='1xlasm',
                        help='Skin name to use for path resolution (default: 1xlasm).')
    parser.add_argument('--dry-run', action='store_true',
                        help='Compute changes but do not write to the DB.')
    args = parser.parse_args(argv)

    skin = SkinRegistry().get(args.skin)
    print(f'using skin {args.skin!r} ({len(skin.labels)} known labels)')

    dbc = DBConnection(config=args.config, verbose=0)
    coll = dbc._get_collection(SceneDef.COLLECTION_IMAGES)
    if coll is None:
        print('ERROR: cannot access images collection', file=sys.stderr)
        return 2

    total = 0
    updated = 0
    unchanged = 0
    no_labels = 0
    unknown_counter: Counter[str] = Counter()

    cursor = coll.find({}, {SceneDef.FIELD_OID: 1, SceneDef.FIELD_LABELS: 1, SceneDef.FIELD_LABELS_NG: 1})
    for doc in cursor:
        total += 1
        legacy = doc.get(SceneDef.FIELD_LABELS) or []
        if not legacy:
            no_labels += 1
            paths: list[str] = []
        else:
            paths, unknown = compute_labels_ng(legacy, skin)
            for u in unknown:
                unknown_counter[u] += 1

        existing = doc.get(SceneDef.FIELD_LABELS_NG)
        if existing == paths:
            unchanged += 1
            continue

        if not args.dry_run:
            coll.update_one(
                {SceneDef.FIELD_OID: doc[SceneDef.FIELD_OID]},
                {'$set': {SceneDef.FIELD_LABELS_NG: paths}},
            )
        updated += 1

    print(f'total scanned:     {total}')
    print(f'no labels:         {no_labels}')
    print(f'already up-to-date:{unchanged}')
    print(f'{"would update" if args.dry_run else "updated"}:           {updated}')
    if unknown_counter:
        print('unresolved legacy labels (count):')
        for name, cnt in unknown_counter.most_common(20):
            print(f'  {cnt:>5}  {name}')
        if len(unknown_counter) > 20:
            print(f'  … and {len(unknown_counter) - 20} more')
    if args.dry_run:
        print('(dry run; FIELD_LABELS_NG was not written)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
