from pathlib import Path
from typing import Optional

from aidb import SceneDef

from .files import is_dir, is_img_or_vid
from .json import read_json


def scene_id_from_url(url: str | Path) -> Optional[str]:
    if is_dir(url):
        dir = Path(url)
    elif is_img_or_vid(url):
        dir = Path(url).parent
    else:
        return None

    try:
        data = read_json(dir / SceneDef.DOTFILE_SCENE)
    except ValueError:
        return None

    return data.get(SceneDef.FIELD_OID, None)
