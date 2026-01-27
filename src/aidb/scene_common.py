from pathlib import Path
from re import S
from typing import Any, Final

from ait.tools.files import SUFFIX_IMG


class SceneDef:
    CONFIG_DEFAULT: Final = 'test_scenes'

    IMAGE_COLLECTION: Final = 'images'

    SEPERATOR_ID: Final = '___'

    PREFIX_ORIG: Final = 'orig'
    PREFIX_THUMBNAIL: Final = 'thumbnail'
    PREFIXES: Final = [PREFIX_ORIG, PREFIX_THUMBNAIL]

    SUFFIX_IMG_STD = '.png'

    FIELD_OID: Final = '_id'
    FIELD_URL: Final = 'url'
    FIELD_URL_SRC: Final = 'url_src'
    FIELD_URL_PARENT: Final = 'url_parent'

    DIR_THUMBNAILS: Final = '.thumbnails'

    @classmethod
    def filename_from_id(cls, prefix: str, id: Any, suffix: str | None = None) -> str | None:
        try:
            id_str = str(id)
        except Exception:
            return None

        ret = f'{prefix}{cls.SEPERATOR_ID}{id_str}'
        if suffix is not None:
            ret += suffix

        return ret

    @classmethod
    def filename_orig_from_id(cls, id: Any, suffix: str | None = None) -> str | None:
        return cls.filename_from_id(cls.PREFIX_ORIG, id, suffix=suffix)

    @classmethod
    def filename_thumbnail_from_id(cls, id: Any, suffix: str = SUFFIX_IMG_STD) -> str | None:
        return cls.filename_from_id(cls.PREFIX_THUMBNAIL, id, suffix=suffix)

    @classmethod
    def id_and_prefix_from_filename(cls, url: str | Path) -> tuple[str, str] | None:
        split = Path(url).stem.split(cls.SEPERATOR_ID)
        if len(split) != 2:
            return None
        prefix = split[0]
        id = split[1]

        if prefix in cls.PREFIXES:
            return id, prefix
        return None
