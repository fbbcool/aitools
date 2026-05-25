"""Batch-apply face_meta extraction labels across a scene.

Reads each registered SceneImage's PNG `face_meta` text chunk (written by
aip's avatar-extraction pipeline), buckets the structural measurements
against the named skin's label vocabulary, and persists the result to
`FIELD_LABELS_NG_EXTRACTION`.

Idempotent: re-running overwrites the field with a fresh bucket.

Usage:
    python script/imgs_extract_face_meta.py <scene-id-or-url> [skin=<name>] [config=<test|prod>]

Examples:
    python script/imgs_extract_face_meta.py 6a12c76272e06624c7e3359a
    python script/imgs_extract_face_meta.py jezebeth-test skin=1xlface config=test
"""
import sys
from collections import Counter

from aidb import SceneManager
from ait.caption.face_meta import apply_to_scene_image
from ait.caption.skin import SkinRegistry


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0

    scene_id_or_url = argv[0]
    skin_name = '1xlface'
    config = 'prod'
    for term in argv[1:]:
        if '=' not in term:
            continue
        k, v = term.split('=', 1)
        if k == 'skin':
            skin_name = v
        elif k == 'config':
            config = v

    skin = SkinRegistry().get(skin_name)
    scm = SceneManager(config=config, verbose=0)  # type: ignore[arg-type]
    try:
        scene = scm.scene_from_id_or_url(scene_id_or_url)
    except Exception as e:
        print(f'ERROR: scene {scene_id_or_url!r} not found in config={config!r}: {e}')
        return 2

    n_with = 0
    n_empty = 0
    n_errors = 0
    all_labels: Counter[str] = Counter()
    for img in scene.imgs:
        try:
            paths = apply_to_scene_image(img, skin, persist=True)
        except Exception as e:
            n_errors += 1
            print(f'  ERROR id={img.id}: {e}')
            continue
        if paths:
            n_with += 1
            all_labels.update(paths)
        else:
            n_empty += 1

    print(f'skin={skin_name} config={config} scene={scene_id_or_url}')
    print(f'  {n_with} images with extraction labels')
    print(f'  {n_empty} images with no face_meta / no buckets')
    if n_errors:
        print(f'  {n_errors} errors')
    print()
    print('aggregate distribution:')
    for path, cnt in sorted(all_labels.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f'  {path:45s} {cnt}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
