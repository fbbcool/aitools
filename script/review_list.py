"""Agent-side CLI for throwaway image review lists (board task 102).

Writers never touch the ``review_imgs`` collection directly — use this:

    python script/review_list.py create <list.json|-> [--replace] [--config test|prod]
    python script/review_list.py get <list_id>        # full doc (with responses) as JSON
    python script/review_list.py ls                   # newest first, answered/total
    python script/review_list.py delete <list_id>
    python script/review_list.py validate <list.json|->   # schema check only, no DB

--config defaults to $AIDB_SCENE_CONFIG (else 'default' = prod).
The operator answers lists in the aidb app's "Review" tab.
Schema: conf/review/_schema.json, doc: conf/review/README.md.
"""

import argparse
import json
import os
import sys

from aidb.review_imgs import ReviewImgs, validate


def _read_json(src: str) -> dict:
    if src == '-':
        return json.load(sys.stdin)
    with open(src, encoding='utf-8') as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description='throwaway image review lists (review_imgs)')
    parser.add_argument(
        '--config',
        default=os.environ.get('AIDB_SCENE_CONFIG') or 'default',
        choices=['test', 'prod', 'default'],
    )
    sub = parser.add_subparsers(dest='cmd', required=True)
    p_create = sub.add_parser('create', help='validate + insert a list')
    p_create.add_argument('file', help="list JSON file, '-' = stdin")
    p_create.add_argument('--replace', action='store_true', help='overwrite an existing list_id')
    p_get = sub.add_parser('get', help='print a list (incl. responses) as JSON')
    p_get.add_argument('list_id')
    sub.add_parser('ls', help='list summaries, newest first')
    p_delete = sub.add_parser('delete', help='delete a list')
    p_delete.add_argument('list_id')
    p_validate = sub.add_parser('validate', help='schema-check a list file (no DB)')
    p_validate.add_argument('file', help="list JSON file, '-' = stdin")
    args = parser.parse_args()

    if args.cmd == 'validate':
        errors = validate(_read_json(args.file))
        for e in errors:
            print(e, file=sys.stderr)
        print('invalid' if errors else 'valid')
        return 1 if errors else 0

    rv = ReviewImgs(config=args.config, verbose=0)

    if args.cmd == 'create':
        try:
            doc = rv.create(_read_json(args.file), replace=args.replace)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        print(f'created {doc["list_id"]} ({len(doc["items"])} items) in config={args.config}')
    elif args.cmd == 'get':
        doc = rv.get(args.list_id)
        if doc is None:
            print(f'no list {args.list_id!r}', file=sys.stderr)
            return 1
        print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
    elif args.cmd == 'ls':
        for d in rv.ls():
            print(
                f'{d["list_id"]}\t{d["answered"]}/{d["total"]}\t{d["created"]}\t'
                f'{d["created_by"] or "-"}\t{d["title"]}'
            )
    elif args.cmd == 'delete':
        if not rv.delete(args.list_id):
            print(f'no list {args.list_id!r}', file=sys.stderr)
            return 1
        print(f'deleted {args.list_id}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
