"""One-time backfill of `scenes_linked` (board FEATURE REQ task 66).

Scans every scene folder's images for 1xlasm-enhancer iteration payloads (via
`ait.tools.images.metadata()` — prompt-chunk authoritative, parent/workflow
inheritance per its trust rules) and writes the found enhancer scene ids into
the scene document's `scenes_linked.ids_scene_enh` AND each payload's
url-resolved origin DB scene into `scenes_linked.ids_scene_db.sourced`
(one-way child → origin, self-links excluded; $addToSet — idempotent,
re-runnable). Without this, `scene_adopt_img` payload matching starts blind and
every adoption spawns a new scene.

Usage:
    python script/scenes_linked_backfill.py [config=test|prod] [dry]

    config  DB profile (default: test — pass config=prod for the real run)
    dry     scan and report only, no DB writes
"""

import sys

from aidb import SceneConfig, SceneDef, SceneManager


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
    n_sourced = 0
    for scene_id in scm.ids:
        n_scenes += 1
        if dry:
            found = scm.scene_scan_links(scene_id)
        else:
            found = scm.scene_seed_enh_links(scene_id)
        enh = found[SceneDef.FIELD_IDS_SCENE_ENH]
        sourced = found[SceneDef.FIELD_LINKED_SOURCED]
        if enh or sourced:
            n_linked += 1
            n_sourced += 1 if sourced else 0
            print(f'{scene_id}: enh={enh} sourced={sourced}')

    mode = 'DRY RUN — no writes' if dry else 'written'
    print(
        f'{n_scenes} scenes scanned, {n_linked} carry enhancer renders, '
        f'{n_sourced} resolve an origin scene ({mode})'
    )


if __name__ == '__main__':
    main()
