"""One-time backfill of `scenes_linked.ids_scene_enh` (board FEATURE REQ task 66).

Scans every scene folder's images for 1xlasm-enhancer iteration payloads (via
`ait.tools.images.metadata()` — prompt-chunk authoritative, parent/workflow
inheritance per its trust rules) and writes the found enhancer scene ids into
the scene document's `scenes_linked.ids_scene_enh` ($addToSet — idempotent,
re-runnable). Without this, `scene_adopt_img` payload matching starts blind and
every adoption spawns a new scene.

Usage:
    python script/scenes_linked_backfill.py [config=test|prod] [dry]

    config  DB profile (default: test — pass config=prod for the real run)
    dry     scan and report only, no DB writes
"""

import sys

from aidb import SceneConfig, SceneManager


def main() -> None:
    config: SceneConfig = 'test'
    dry = False
    for arg in sys.argv[1:]:
        if arg.startswith('config='):
            value = arg.split('=', 1)[1]
            if value not in ('test', 'prod', 'default'):
                print(f'invalid config: {value}', file=sys.stderr)
                sys.exit(1)
            config = value  # type: ignore[assignment]
        elif arg == 'dry':
            dry = True
        else:
            print(f'unknown arg: {arg}', file=sys.stderr)
            sys.exit(1)

    scm = SceneManager(config=config, verbose=0)
    n_scenes = 0
    n_linked = 0
    for scene_id in scm.ids:
        n_scenes += 1
        if dry:
            found = scm.scene_scan_enh_ids(scene_id)
        else:
            found = scm.scene_seed_enh_links(scene_id)
        if found:
            n_linked += 1
            print(f'{scene_id}: {found}')

    mode = 'DRY RUN — no writes' if dry else 'written'
    print(f'{n_scenes} scenes scanned, {n_linked} carry enhancer renders ({mode})')


if __name__ == '__main__':
    main()
