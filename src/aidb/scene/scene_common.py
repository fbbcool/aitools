from copy import deepcopy
import datetime
from pathlib import Path
from typing import Any, Final, Literal, Optional, Protocol

SceneConfig = Literal['test', 'prod', 'default']


class SceneDef:
    COLLECTION_IMAGES: Final = 'images'
    COLLECTION_SCENES: Final = 'scenes'
    COLLECTION_SETS: Final = 'sets'

    SEPERATOR_ID: Final = '___'

    PREFIX_ORIG: Final = '0rig'
    PREFIX_ORIGS: Final = [PREFIX_ORIG]
    PREFIX_THUMBNAIL: Final = 'thumbnail'
    PREFIX_TRAIN: Final = 'train'
    PREFIXES: Final = PREFIX_ORIGS + [PREFIX_THUMBNAIL, PREFIX_TRAIN]

    SUFFIX_IMG_STD = '.png'

    FIELD_OID: Final = '_id'
    FIELD_URL: Final = 'url'
    FIELD_URL_SRC: Final = 'url_src'
    FIELD_URL_PARENT: Final = 'url_parent'
    FIELD_NAME: Final = 'name'
    FIELD_FILE_NAME: Final = 'file_name'
    FIELD_FILE_TYPE: Final = 'file_type'
    FIELD_DESCRIPTION: Final = 'description'
    FIELD_CAPTION: Final = 'caption'
    FIELD_CAPTION_JOY: Final = 'caption_joy'
    FIELD_PROMPT: Final = 'prompt'
    FIELD_QUERY: Final = 'query'
    FIELD_QUERY_IMG: Final = 'query_img'
    FIELD_TRIGGER: Final = 'trigger'
    FIELD_RATIOS: Final = 'ratios'
    FIELD_RESOLUTIONS: Final = 'resolutions'
    FIELD_TIMESTAMP_CREATED: Final = 'timestamp_created'
    FIELD_TIMESTAMP_UPDATED: Final = 'timestamp_updated'

    DEFAULT_RATIOS: Final = [1.0, 2.0 / 3.0, 3.0 / 4.0]
    DEFAULT_RESOLUTIONS: Final = [512, 768, 1024]

    DIR_TRAIN: Final = 'train'
    DIR_THUMBNAILS: Final = f'{SEPERATOR_ID}thumbnails'

    FIELD_RATING: Final = 'rating'
    RATING_MIN: Final = -2
    RATING_MAX: Final = 5
    RATING_INIT: Final = -1
    RATING_IMG_REG: Final = 1

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
        if id_and_prefix[1] not in cls.PREFIX_ORIGS:
            return None
        return id_and_prefix[0]

    @classmethod
    def sort_by_rating(cls, items: list[Any]) -> list[Any]:
        items.sort(key=lambda x: x.data.get(cls.FIELD_RATING, cls.RATING_MIN), reverse=True)
        return items

    @classmethod
    def sort_by_timestamp_updated(cls, items: list[Any]) -> list[Any]:
        items.sort(key=lambda x: cls.get_timestamp_update_from_data(x), reverse=True)
        return items

    @classmethod
    def reduce_by_rating_highest(cls, items: list[Any]) -> list[Any]:
        cls.sort_by_rating(items)
        if not items:
            return []
        rating_max = items[0].data.get(cls.FIELD_RATING, cls.RATING_MIN)
        return [
            item for item in items if item.data.get(cls.FIELD_RATING, cls.RATING_MIN) == rating_max
        ]

    @classmethod
    def prepare_data_for_update(cls, data: dict) -> dict:
        # copy
        update_data = deepcopy(data)

        # remove id
        update_data.pop(cls.FIELD_OID, None)

        # set update ts
        ts = datetime.datetime.now().timestamp()
        update_data |= {cls.FIELD_TIMESTAMP_UPDATED: ts}

        return update_data

    @classmethod
    def get_timestamp_update_from_data(cls, item: Any) -> float:
        if not hasattr(item, 'data'):
            return 0.0

        ts = item.data.get(cls.FIELD_TIMESTAMP_UPDATED, None)
        if ts is not None:
            return ts

        return item.data.get(cls.FIELD_TIMESTAMP_CREATED, 0.0)


class Sceneical(Protocol):
    @property
    def rating(self) -> int: ...
    def set_rating(self, val: int | str) -> None: ...
    @property
    def labels(self) -> list[str]: ...
    def set_labels(self, val: list[str]) -> None: ...
    def push_label(self, val: str) -> None: ...
    def pop_label(self, val: str) -> None: ...
    def switch_label(self, val: str) -> None: ...
    def db_store(self) -> bool: ...
