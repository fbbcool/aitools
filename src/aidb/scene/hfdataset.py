from pathlib import Path
from typing import Generator, Optional
import jsonlines
from huggingface_hub import hf_hub_download, snapshot_download
from pandas.core.computation.ops import Op

from aidb.scene.scene_common import SceneDef


class HFDataset:
    def __init__(
        self, repo_id: str, file_meta: str = 'metadata.jsonl', force_meta_dl: bool = False
    ):
        self._repo_id = repo_id
        self._file_meta = file_meta
        self._url_cache: Optional[Path] = None
        self._meta = self._load_meta(force_download=force_meta_dl)
        self._data_ids = self._make_data_ids()

    def _load_meta(self, force_download: bool = False) -> list[dict]:
        file_path = hf_hub_download(
            repo_id=self._repo_id,
            filename='train/' + self._file_meta,
            repo_type='dataset',
            force_download=force_download,
        )
        if self._file_meta.endswith('.jsonl'):
            meta = []
            with jsonlines.open(file_path) as reader:
                for obj in reader:
                    meta.append(obj)
            return meta
        else:
            raise FileNotFoundError('Unsupported file format. Only .json and .jsonl are supported.')

    def _make_data_ids(self) -> dict[str, dict]:
        data_ids = {}
        for item in self:
            url = item.get(SceneDef.FIELD_FILE_NAME, None)
            if url is None:
                continue
            id_and_prefix = SceneDef.id_and_prefix_from_filename(url)
            if id_and_prefix is None:
                continue
            id = id_and_prefix[0]

            data_id = {}

            file_name = item.get(SceneDef.FIELD_FILE_NAME, None)
            if file_name is not None:
                data_id |= {SceneDef.FIELD_FILE_NAME: file_name}

            file_type = item.get(SceneDef.FIELD_FILE_TYPE, None)
            if file_type is not None:
                data_id |= {SceneDef.FIELD_FILE_TYPE: file_type}

            caption = item.get(SceneDef.FIELD_CAPTION, None)
            # TODO: hfds should only use FIELD_CAPTION!
            if caption is None:
                caption = item.get(SceneDef.FIELD_CAPTION_JOY, None)

            if caption is not None:
                data_id |= {SceneDef.FIELD_CAPTION: caption}

            if data_id:
                data_ids |= {id: data_id}
        return data_ids

    def cache(self) -> Path:
        if self._url_cache is None:
            url_cache = snapshot_download(repo_id=self._repo_id, repo_type='dataset')
            self._url_cache = Path(url_cache)
        return self._url_cache

    @property
    def urls(self) -> Generator[Optional[str], None, None]:
        for item in self:
            yield item.get(SceneDef.FIELD_FILE_NAME, None)

    @property
    def ids(self) -> Generator[Optional[str], None, None]:
        for url in self.urls:
            if url is None:
                yield None
                continue
            id_and_prefix = SceneDef.id_and_prefix_from_filename(url)
            if id_and_prefix is None:
                yield None
                continue
            else:
                yield id_and_prefix[0]

    @property
    def urls_file(self) -> Generator[Optional[Path], None, None]:
        url_cache = self.cache()
        if url_cache is None:
            yield None
        else:
            for url in self.urls:
                if url is None:
                    yield None
                    continue
                yield url_cache / url

    @property
    def meta(self) -> list[dict]:
        return self._meta

    def data_from_id(self, id: str) -> Optional[dict]:
        return self._data_ids.get(id, None)

    def file_name_from_id(self, id: str) -> Optional[str]:
        data_id = self.data_from_id(id)
        if data_id is None:
            return None
        return data_id.get(SceneDef.FIELD_FILE_NAME, None)

    def file_tyep_from_id(self, id: str) -> Optional[str]:
        data_id = self.data_from_id(id)
        if data_id is None:
            return None
        return data_id.get(SceneDef.FIELD_FILE_TYPE, None)

    def caption_from_id(self, id: str) -> Optional[str]:
        data_id = self.data_from_id(id)
        if data_id is None:
            return None
        return data_id.get(SceneDef.FIELD_CAPTION, None)

    def url_file_from_id(self, id: str) -> Optional[Path]:
        file_name = self.file_name_from_id(id)
        if file_name is None:
            return None
        return self.cache() / file_name

    def __len__(self):
        return len(self._meta)

    def __getitem__(self, idx):
        return self._meta[idx]

    def __iter__(self):
        for item in self._meta:
            yield item
