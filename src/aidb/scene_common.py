from pathlib import Path
from typing import Any, Final


class SceneDef:
    CONFIG_DEFAULT: Final = 'test_scenes'

    SEPERATOR_ID: Final = '___'

    IMAGE_COLLECTION: Final = 'images'

    PREFIX_ORIG: Final = 'orig'
    PREFIXES: Final = [PREFIX_ORIG]

    FIELD_OID: Final = '_id'
    FIELD_URL: Final = 'url'
    FIELD_URL_SRC: Final = 'url_src'
    FIELD_URL_PARENT: Final = 'url_parent'

    @classmethod
    def filename_from_id(cls, prefix: str, id: Any) -> str | None:
        try:
            id_str = str(id)
        except Exception:
            return None

        return f'{prefix}{cls.SEPERATOR_ID}{id_str}'

    @classmethod
    def filename_orig_from_id(cls, id: Any) -> str | None:
        return cls.filename_from_id(cls.PREFIX_ORIG, id)

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
