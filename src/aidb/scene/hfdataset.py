from pathlib import Path
from typing import Final, Generator, Optional
import jsonlines
from huggingface_hub import hf_hub_download, snapshot_download

from aidb.scene.scene_common import SceneDef


class HFDataset:
    FILE_META: Final = 'metadata.jsonl'

    def __init__(self, repo_id: str, file_jsonl: str = FILE_META, force_meta_dl: bool = False):
        self._repo_id = repo_id
        self._file_jsonl = file_jsonl
        self._url_cache: Optional[Path] = None
        _jsonl = self._load_jsonl(force_download=force_meta_dl)
        self._data = self._data_from_jsonl(_jsonl)

    def _load_jsonl(self, force_download: bool = False) -> list[dict]:
        file_path = hf_hub_download(
            repo_id=self._repo_id,
            filename='train/' + self._file_jsonl,
            repo_type='dataset',
            force_download=force_download,
        )
        if self._file_jsonl.endswith('.jsonl'):
            meta = []
            with jsonlines.open(file_path) as reader:
                for obj in reader:
                    meta.append(obj)
            return meta
        else:
            raise FileNotFoundError('Unsupported file format. Only .json and .jsonl are supported.')

    def _data_from_jsonl(self, jsonl: list[dict]) -> dict[str, dict]:
        data_ids = {}
        for item in jsonl:
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

    def _jsonl_from_data(self) -> list[dict]:
        return [line_data for line_data in self._data.values()]

    def cache(self) -> Path:
        if self._url_cache is None:
            url_cache = snapshot_download(repo_id=self._repo_id, repo_type='dataset')
            self._url_cache = Path(url_cache)
        return self._url_cache

    @property
    def urls(self) -> Generator[str, None, None]:
        for item in self._data.values():
            url = item.get(SceneDef.FIELD_FILE_NAME, None)
            if url is None:
                continue
            yield url

    @property
    def ids(self) -> Generator[str, None, None]:
        for url in self.urls:
            id_and_prefix = SceneDef.id_and_prefix_from_filename(url)
            if id_and_prefix is None:
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
                yield url_cache / SceneDef.DIR_TRAIN / url

    def data_from_id(self, id: str) -> Optional[dict]:
        return self._data.get(id, None)

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
        return self.cache() / SceneDef.DIR_TRAIN / file_name

    def set_caption(self, id: str, caption: str) -> bool:
        if not id or not caption:
            return False
        data_id = self.data_from_id(id)
        if data_id is None:
            return False
        data_id |= {SceneDef.FIELD_CAPTION: caption}
        self._data |= {id: data_id}
        return True

    def save(self, to_url: Optional[Path] = None, force: bool = True):
        to_file_meta = Path()
        if to_url is not None:
            to_file_meta = to_url
        to_file_meta = to_file_meta / self.FILE_META

        try:
            with jsonlines.open(to_file_meta, mode='w') as writer:
                writer.write_all(self._jsonl_from_data())
                print(f'metadata successfully saved to {to_file_meta}')
        except Exception as e:
            print(f'Error saving data to JSONL: {e}')

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        for id in self._data:
            yield id
