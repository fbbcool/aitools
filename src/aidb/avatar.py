"""Avatars — aidb collection ``avatars`` (board FEATURE t218, schema ``aidb.avatar.v1``).

An avatar is one document per persona for img/vid generation workflows: metadata
(display name, description, triggers, LoRAs, prompt guides, tags, an open
``extra``) plus its media (images, videos, audio). The schema is owned by
avataros (t218); the LoRA fields stay compatible with the enhancer's INFO t90
``avatars[]`` entries.

    {
      schema: 'aidb.avatar.v1',
      name: '<slug>',                 # unique, also the media dir name
      display_name, description,
      triggers: [str],
      loras: [{trigger, class_word, family, dataset, revision, src,
               lora_weight: {solo, stacked, text}, negative}],
      prompt_guides: [{engine, text}],
      tags: [str],
      media: [{mid, kind, url, src, role, added}],
      extra: {},
      created, updated                # ISO 'YYYY-MM-DDTHH:MM:SS'
    }

Media are COPIED into ``<root>/<name>/{img,vid,aud}/`` (root default
``~/Data/AI/avatars``): the filename is kept, a ``_<n>`` suffix is added on
collision; ``url`` = the copy, ``src`` = the original. ``kind`` follows refdef's
``media_kind`` (file suffix). ``role`` is free text with refdef slot-role
semantics; where the format carries one (png / mp4 / mov / mkv) it is also
written into the copy as the embedded ``ait_role`` descr (t215). Removing a
media item deletes its copy; renaming an avatar moves its dir.

Everything public takes / returns plain dicts (``_id`` as str).
"""

from __future__ import annotations

import builtins
import datetime
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote

from aidb.scene.db_connect import DBConnection
from aidb.scene.scene_common import SceneConfig
from ait.tools import role as ait_role
from ait.tools.files import suffix_aud, suffix_img, suffix_vid

COLLECTION: Final = 'avatars'
SCHEMA: Final = 'aidb.avatar.v1'
AVATARS_ROOT: Final = Path.home() / 'Data' / 'AI' / 'avatars'
KIND_DIR: Final = {'image': 'img', 'video': 'vid', 'audio': 'aud'}
KINDS: Final = tuple(KIND_DIR)

EDITABLE: Final = (
    'display_name',
    'description',
    'triggers',
    'loras',
    'prompt_guides',
    'tags',
    'extra',
)
LORA_FIELDS: Final = (
    'trigger',
    'class_word',
    'family',
    'dataset',
    'revision',
    'src',
    'lora_weight',
    'negative',
)
LORA_WEIGHT_FIELDS: Final = ('solo', 'stacked', 'text')
SLUG_RE: Final = re.compile(r'^[a-z0-9][a-z0-9_-]*$')
TS_FMT: Final = '%Y-%m-%dT%H:%M:%S'


class AvatarError(ValueError):
    """Unknown avatar / media id, duplicate name, invalid field or unusable media."""


# ---------------------------------------------------------------------- #
# helpers (pure)
# ---------------------------------------------------------------------- #
def now() -> str:
    return datetime.datetime.now().strftime(TS_FMT)


def media_kind(url: str | Path | None) -> str | None:
    """'image' / 'video' / 'audio' by file suffix (None when empty / unknown) — same
    rule as the refdef tab's ``media_kind``."""
    if not url:
        return None
    suf = Path(str(url).split('?')[0]).suffix.lower()
    if suf in suffix_img():
        return 'image'
    if suf in suffix_vid():
        return 'video'
    if suf in suffix_aud():
        return 'audio'
    return None


def slugify(name: str) -> str:
    """Display name → avatar slug (lowercase ``[a-z0-9_-]``, '' when nothing is left)."""
    s = re.sub(r'[^a-z0-9_-]+', '-', (name or '').strip().lower())
    return re.sub(r'-{2,}', '-', s).strip('-_')


def check_slug(name: str) -> str:
    if not isinstance(name, str) or not SLUG_RE.match(name):
        raise AvatarError(f'invalid avatar name {name!r} (slug: [a-z0-9][a-z0-9_-]*)')
    return name


def _str_list(v: Any, field: str) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)) or not all(isinstance(x, str) for x in v):
        raise AvatarError(f'{field}: list of str expected')
    out: list[str] = []
    for x in v:  # stripped, blanks + duplicates dropped, order kept
        x = x.strip()
        if x and x not in out:
            out.append(x)
    return out


def norm_lora(d: Any) -> dict:
    """One ``loras[]`` entry with every t90 field present (missing = None, weights
    = {solo, stacked, text}); unknown keys are kept."""
    if not isinstance(d, dict):
        raise AvatarError('loras: list of dicts expected')
    out = {k: d.get(k) for k in LORA_FIELDS}
    w = d.get('lora_weight')
    if w is not None and not isinstance(w, dict):
        raise AvatarError('loras[].lora_weight: dict {solo, stacked, text} expected')
    wd = dict(w or {})
    out['lora_weight'] = {k: wd.pop(k, None) for k in LORA_WEIGHT_FIELDS} | wd
    out.update({k: v for k, v in d.items() if k not in LORA_FIELDS})
    return out


def norm_guide(d: Any) -> dict:
    if not isinstance(d, dict) or not isinstance(d.get('engine', ''), str):
        raise AvatarError('prompt_guides: list of {engine, text} expected')
    out = {**d, 'engine': (d.get('engine') or '').strip(), 'text': d.get('text') or ''}
    if not isinstance(out['text'], str):
        raise AvatarError('prompt_guides[].text: str expected')
    return out


def norm_fields(fields: dict) -> dict:
    """Validate / normalize the editable fields; raises AvatarError on unknown keys."""
    bad = [k for k in fields if k not in EDITABLE]
    if bad:
        raise AvatarError(f'not editable: {", ".join(bad)}')
    out: dict[str, Any] = {}
    for k, v in fields.items():
        if k in ('display_name', 'description'):
            if v is not None and not isinstance(v, str):
                raise AvatarError(f'{k}: str expected')
            out[k] = (v or '').strip() if k == 'display_name' else (v or '')
        elif k in ('triggers', 'tags'):
            out[k] = _str_list(v, k)
        elif k == 'loras':
            out[k] = [norm_lora(x) for x in (v or [])]
        elif k == 'prompt_guides':
            out[k] = [norm_guide(x) for x in (v or [])]
        elif k == 'extra':
            if v is not None and not isinstance(v, dict):
                raise AvatarError('extra: dict expected')
            out[k] = dict(v or {})
    return out


def _local_path(src: str | Path) -> Path:
    s = str(src).strip().strip('"\'')
    if s.startswith('file://'):
        s = unquote(s.removeprefix('file://'))
    if '://' in s:
        raise AvatarError(f'only local files can be added: {s}')
    return Path(s).expanduser()


def free_name(dirpath: Path, filename: str) -> Path:
    """``dirpath/filename``, or ``<stem>_<n><suffix>`` (n = 1, 2, …) when taken."""
    p = dirpath / filename
    n = 1
    while p.exists():
        p = dirpath / f'{Path(filename).stem}_{n}{Path(filename).suffix}'
        n += 1
    return p


def _ordered_media(avatar: dict, mids: list[str] | None) -> list[dict]:
    media = list(avatar.get('media') or [])
    if mids is None:
        return media
    by_mid = {m['mid']: m for m in media}
    missing = [m for m in mids if m not in by_mid]
    if missing:
        raise AvatarError(f'unknown media id(s) in {avatar.get("name")}: {", ".join(missing)}')
    return [by_mid[m] for m in mids]


def to_refdef(avatar: dict, mids: list[str] | None = None) -> list[dict]:
    """Refdef-compatible ref list ``[{slot, url, id, role}]`` (slot 1-based, id = mid)
    in the order of `mids` (None = every media item in avatar order)."""
    return [
        {'slot': i, 'url': m['url'], 'id': m['mid'], 'role': m.get('role') or ''}
        for i, m in enumerate(_ordered_media(avatar, mids), start=1)
    ]


def refdef_urls(avatar: dict, mids: list[str] | None = None) -> list[str]:
    """The ordered url list (what the tab's ⇪ deploy writes, one url per line)."""
    return [m['url'] for m in _ordered_media(avatar, mids)]


def _out(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    doc = dict(doc)
    if '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc


# ---------------------------------------------------------------------- #
# manager
# ---------------------------------------------------------------------- #
class AvatarManager:
    """CRUD + media store for the ``avatars`` collection of the active aidb DB."""

    def __init__(
        self,
        config: SceneConfig = 'default',
        dbc: DBConnection | None = None,
        root: Path | str | None = None,
        verbose: int = 0,
    ) -> None:
        self._verbose = verbose
        self._dbc = dbc if dbc is not None else DBConnection(config=config, verbose=verbose)
        col = self._dbc._get_collection(COLLECTION)
        if col is None:
            raise RuntimeError(f'no DB connection for collection {COLLECTION!r}')
        self._col = col
        self._col.create_index('name', unique=True)
        self.root = Path(root).expanduser() if root is not None else AVATARS_ROOT

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[avatar:{level}] {msg}')

    # -- paths ---------------------------------------------------------- #
    def dir_of(self, name: str) -> Path:
        return self.root / check_slug(name)

    def _in_root(self, p: Path) -> bool:
        try:
            p.resolve().relative_to(self.root.resolve())
            return True
        except ValueError:
            return False

    # -- read ----------------------------------------------------------- #
    def _doc(self, name: str) -> dict:
        doc = self._col.find_one({'name': name})
        if doc is None:
            raise AvatarError(f'no avatar {name!r}')
        return doc

    def get(self, name: str) -> dict | None:
        return _out(self._col.find_one({'name': name}))

    def names(self) -> list[str]:
        return sorted(d['name'] for d in self._col.find({}, {'_id': 0, 'name': 1}))

    def list(self) -> list[dict]:
        return [_out(d) for d in self._col.find({}).sort('name', 1)]  # type: ignore[misc]

    def media(self, name: str, mid: str) -> dict | None:
        doc = self._col.find_one({'name': name}, {'media': 1})
        return next((m for m in (doc or {}).get('media') or [] if m.get('mid') == mid), None)

    # -- write ---------------------------------------------------------- #
    def _set(self, name: str, fields: dict) -> dict:
        fields = {**fields, 'updated': now()}
        res = self._col.find_one_and_update({'name': name}, {'$set': fields}, return_document=True)
        if res is None:
            raise AvatarError(f'no avatar {name!r}')
        return _out(res)  # type: ignore[return-value]

    def create(self, name: str, display_name: str | None = None, **fields) -> dict:
        """New avatar `name` (slug, unique); further editable fields as kwargs."""
        check_slug(name)
        if self._col.find_one({'name': name}, {'_id': 1}) is not None:
            raise AvatarError(f'avatar {name!r} exists')
        f = norm_fields({'display_name': display_name or name, **fields})
        ts = now()
        doc = {
            'schema': SCHEMA,
            'name': name,
            'display_name': f.get('display_name') or name,
            'description': f.get('description', ''),
            'triggers': f.get('triggers', []),
            'loras': f.get('loras', []),
            'prompt_guides': f.get('prompt_guides', []),
            'tags': f.get('tags', []),
            'media': [],
            'extra': f.get('extra', {}),
            'created': ts,
            'updated': ts,
        }
        self._col.insert_one(doc)
        self._log(f'created {name}')
        return _out(doc)  # type: ignore[return-value]

    def update(self, name: str, **fields) -> dict:
        """Set editable fields (display_name, description, triggers, loras,
        prompt_guides, tags, extra); each given field is replaced whole."""
        return self._set(name, norm_fields(fields))

    def rename(self, name: str, new_name: str) -> dict:
        """Rename the avatar: moves its media dir and rewrites the media urls."""
        check_slug(new_name)
        doc = self._doc(name)
        if new_name == name:
            return _out(doc)  # type: ignore[return-value]
        if self._col.find_one({'name': new_name}, {'_id': 1}) is not None:
            raise AvatarError(f'avatar {new_name!r} exists')
        old_dir, new_dir = self.dir_of(name), self.dir_of(new_name)
        if new_dir.exists():
            raise AvatarError(f'dir exists: {new_dir}')
        if old_dir.exists():
            new_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_dir), str(new_dir))
        media = []
        for m in doc.get('media') or []:
            url = Path(m['url'])
            try:
                url = new_dir / url.relative_to(old_dir)
            except ValueError:
                pass  # not under the avatar dir: left as is
            media.append({**m, 'url': str(url)})
        try:
            res = self._col.find_one_and_update(
                {'name': name},
                {'$set': {'name': new_name, 'media': media, 'updated': now()}},
                return_document=True,
            )
        except Exception:
            if new_dir.exists() and not old_dir.exists():
                shutil.move(str(new_dir), str(old_dir))  # keep dir and DB in sync
            raise
        self._log(f'renamed {name} → {new_name}')
        return _out(res)  # type: ignore[return-value]

    def delete(self, name: str, remove_files: bool = True) -> bool:
        """Delete the avatar document (and, by default, its media dir)."""
        ok = self._col.delete_one({'name': name}).deleted_count > 0
        d = self.dir_of(name)
        if ok and remove_files and d.is_dir() and self._in_root(d):
            shutil.rmtree(d)
        self._log(f'deleted {name}: {ok}')
        return ok

    # -- media ---------------------------------------------------------- #
    def _write_role(self, url: str, role: str) -> None:
        if not ait_role.supported(url):
            return
        try:
            ait_role.role_set(url, {'descr': role} if role.strip() else None)
        except Exception as e:  # noqa: BLE001 - a role carrier failure keeps the DB role
            self._log(f'ait_role write failed for {url}: {e}', 'warning')

    def add_media(self, name: str, src: str | Path, role: str = '') -> dict:
        """Copy the local file `src` into the avatar dir; returns the new media item."""
        doc = self._doc(name)
        p = _local_path(src)
        if not p.is_file():
            raise AvatarError(f'no such file: {p}')
        kind = media_kind(p)
        if kind is None:
            raise AvatarError(f'not an image / video / audio file: {p.name}')
        role = (role or '').strip()
        dst_dir = self.dir_of(name) / KIND_DIR[kind]
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = free_name(dst_dir, p.name)
        shutil.copy2(p, dst)
        if role:
            self._write_role(str(dst), role)
        item = {
            'mid': uuid.uuid4().hex[:12],
            'kind': kind,
            'url': str(dst),
            'src': str(p),
            'role': role,
            'added': now(),
        }
        res = self._col.update_one(
            {'_id': doc['_id']}, {'$push': {'media': item}, '$set': {'updated': now()}}
        )
        if not res.matched_count:  # avatar vanished meanwhile: no orphan copy
            dst.unlink(missing_ok=True)
            raise AvatarError(f'no avatar {name!r}')
        self._log(f'{name}: added {kind} {dst.name}')
        return item

    def remove_media(self, name: str, mid: str) -> bool:
        """Drop a media item and delete its copy (only files inside the avatar root)."""
        item = self.media(name, mid)
        if item is None:
            return False
        self._col.update_one(
            {'name': name}, {'$pull': {'media': {'mid': mid}}, '$set': {'updated': now()}}
        )
        p = Path(item['url'])
        if p.is_file() and self._in_root(p):
            p.unlink()
        self._log(f'{name}: removed {mid}')
        return True

    def set_role(self, name: str, mid: str, role: str) -> dict:
        """Set a media item's role (DB, plus the embedded ait_role where supported)."""
        role = (role or '').strip()
        res = self._col.find_one_and_update(
            {'name': name, 'media.mid': mid},
            {'$set': {'media.$.role': role, 'updated': now()}},
            return_document=True,
        )
        if res is None:
            raise AvatarError(f'no media {mid!r} in avatar {name!r}')
        item = next(m for m in res['media'] if m['mid'] == mid)
        if Path(item['url']).is_file():
            self._write_role(item['url'], role)
        return item

    def reorder(self, name: str, mids: builtins.list[str]) -> dict:
        """New media order: `mids` first (in that order), the others keep theirs."""
        doc = self._doc(name)
        media = doc.get('media') or []
        by_mid = {m['mid']: m for m in media}
        unknown = [m for m in mids if m not in by_mid]
        if unknown:
            raise AvatarError(f'unknown media id(s) in {name}: {", ".join(unknown)}')
        first = list(dict.fromkeys(mids))
        rest = [m for m in media if m['mid'] not in first]
        return self._set(name, {'media': [by_mid[m] for m in first] + rest})
