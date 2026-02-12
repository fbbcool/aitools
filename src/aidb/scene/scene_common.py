from pathlib import Path
from typing import Any, Final, Literal, Optional

SceneConfig = Literal['test', 'prod', 'default']


class SceneDef:
    COLLECTION_IMAGES: Final = 'images'
    COLLECTION_SCENES: Final = 'scenes'
    COLLECTION_SETS: Final = 'sets'

    SEPERATOR_ID: Final = '___'

    PREFIX_ORIG: Final = 'orig'
    PREFIX_THUMBNAIL: Final = 'thumbnail'
    PREFIX_TRAIN: Final = 'train'
    PREFIXES: Final = [PREFIX_ORIG, PREFIX_THUMBNAIL, PREFIX_TRAIN]

    SUFFIX_IMG_STD = '.png'

    FIELD_OID: Final = '_id'
    FIELD_URL: Final = 'url'
    FIELD_URL_SRC: Final = 'url_src'
    FIELD_URL_PARENT: Final = 'url_parent'
    FIELD_NAME: Final = 'name'
    FIELD_DESCRIPTION: Final = 'description'
    FIELD_CAPTION: Final = 'caption'
    FIELD_PROMPT: Final = 'prompt'
    FIELD_QUERY: Final = 'query'
    FIELD_QUERY_IMG: Final = 'query_img'
    FIELD_TRIGGER: Final = 'trigger'

    DIR_THUMBNAILS: Final = f'{SEPERATOR_ID}thumbnails'

    FIELD_RATING: Final = 'rating'
    RATING_MIN: Final = -2
    RATING_MAX: Final = 5
    RATING_INIT: Final = -1

    FIELD_LABELS: Final = 'labels'

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
    def filename_train_from_id(cls, id: Any, suffix: str = SUFFIX_IMG_STD) -> str | None:
        return cls.filename_from_id(cls.PREFIX_TRAIN, id, suffix=suffix)

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

    @classmethod
    def id_from_filename_orig(cls, url: str | Path) -> Optional[str]:
        id_and_prefix = cls.id_and_prefix_from_filename(url)
        if id_and_prefix is None:
            return None
        if id_and_prefix[1] != cls.PREFIX_ORIG:
            return None
        return id_and_prefix[0]
