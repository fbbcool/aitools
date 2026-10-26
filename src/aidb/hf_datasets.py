"""Active HF dataset list + local-cache reader for the scene app's HF datasets tab.

The operator maintains the list of "active" Hugging Face dataset repos in the
``hf_datasets`` collection of the active aidb DB (``scenes_<config>``), one
document per repo: ``{repo_id, added}``. The app tab adds (by url or repo id)
and deletes entries; nothing here touches ``scenes`` / ``images`` / ``sets``.

``HFDatasetLocal`` pulls a dataset repo into the local HF cache
(``snapshot_download``) and lists its media files with their captions, read
from ``metadata.jsonl`` (``caption``, fallback ``caption_joy``) or, for
files the jsonl does not cover, a sibling ``<stem>.txt``.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Final

from huggingface_hub import HfApi, snapshot_download

from aidb.scene.db_connect import DBConnection
from aidb.scene.scene_common import SceneConfig, SceneDef
from ait.tools.files import is_img_or_vid

COLLECTION: Final = 'hf_datasets'

FILE_META: Final = 'metadata.jsonl'

_RE_REPO_ID: Final = re.compile(r'^[\w.-]+/[\w.-]+$')


def repo_id_from_url(url: str) -> str | None:
    """Repo id from an HF dataset url / ``datasets/<org>/<name>`` / plain ``<org>/<name>``.

    >>> repo_id_from_url('https://huggingface.co/datasets/fbbcool/1fbb_02/tree/main')
    'fbbcool/1fbb_02'
    """
    s = url.strip().rstrip('/')
    s = re.sub(r'^https?://(www\.)?(huggingface\.co|hf\.co)/', '', s)
    s = re.sub(r'^datasets/', '', s)
    parts = s.split('/')
    if len(parts) < 2:
        return None
    repo_id = f'{parts[0]}/{parts[1]}'
    return repo_id if _RE_REPO_ID.match(repo_id) else None


def _captions_from_jsonl(meta: Path) -> dict[Path, str]:
    """file path (``file_name`` resolved against the jsonl's dir) -> caption."""
    out: dict[Path, str] = {}
    with open(meta, encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            file_name = item.get(SceneDef.FIELD_FILE_NAME)
            caption = item.get(SceneDef.FIELD_CAPTION) or item.get(SceneDef.FIELD_CAPTION_JOY)
            if file_name and caption is not None:
                out[meta.parent / file_name] = caption
    return out


class HFDatasetsActive:
    """Manager for the operator-maintained ``hf_datasets`` collection."""

    def __init__(
        self,
        config: SceneConfig = 'default',
        dbc: DBConnection | None = None,
        verbose: int = 1,
    ) -> None:
        self._verbose = verbose
        self._dbc = dbc if dbc is not None else DBConnection(config=config, verbose=verbose)
        col = self._dbc._get_collection(COLLECTION)
        if col is None:
            raise RuntimeError(f'no DB connection for collection {COLLECTION!r}')
        self._col = col
        self._col.create_index('repo_id', unique=True)

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[hf_datasets:{level}] {msg}')

    @property
    def repo_ids(self) -> list[str]:
        return sorted(d['repo_id'] for d in self._col.find({}, {'_id': 0, 'repo_id': 1}))

    def add(self, url: str, check_hub: bool = True) -> str:
        """Add a dataset by url or repo id. Returns the repo id; raises ValueError."""
        repo_id = repo_id_from_url(url)
        if repo_id is None:
            raise ValueError(f'not an HF dataset url / repo id: {url!r}')
        if self._col.find_one({'repo_id': repo_id}, {'_id': 1}) is not None:
            raise ValueError(f'{repo_id} is already in the active list')
        if check_hub:
            try:
                HfApi().dataset_info(repo_id)
            except Exception as e:  # noqa: BLE001
                raise ValueError(f'{repo_id} not reachable on the hub: {e}') from e
        self._col.insert_one(
            {'repo_id': repo_id, 'added': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M')}
        )
        self._log(f'added {repo_id}')
        return repo_id

    def delete(self, repo_id: str) -> bool:
        ok = self._col.delete_one({'repo_id': repo_id}).deleted_count > 0
        self._log(f'deleted {repo_id}: {ok}')
        return ok


class HFDatasetLocal:
    """A dataset repo materialized in the local HF cache: media files + captions."""

    def __init__(self, repo_id: str, force_download: bool = False) -> None:
        self.repo_id = repo_id
        self.root = Path(
            snapshot_download(repo_id=repo_id, repo_type='dataset', force_download=force_download)
        )
        self.items = self._scan()

    def _scan(self) -> list[dict]:
        """``[{url, caption}]`` sorted by url; url is the snapshot path in the HF cache."""
        captions: dict[Path, str] = {}
        for meta in self.root.rglob(FILE_META):
            captions |= _captions_from_jsonl(meta)

        items = []
        for p in sorted(self.root.rglob('*')):
            if not p.is_file() or not is_img_or_vid(p):
                continue
            caption = captions.get(p)
            if caption is None:
                txt = p.with_suffix('.txt')
                caption = txt.read_text(encoding='utf-8').strip() if txt.is_file() else None
            items.append({'url': str(p), 'caption': caption})
        return items

    def __len__(self) -> int:
        return len(self.items)
