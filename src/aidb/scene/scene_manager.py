from pathlib import Path
from typing import Any, Generator
import filecmp
import shutil
import sys
import json

from aidb.scene.db_connect import DBConnection
from aidb.scene.scene_image_manager import SceneImageManager
from ait.tools.files import (
    imgs_and_vids_from_url,
    is_img_or_vid,
    subdir_inc,
    is_dir,
)
from ait.tools.images import metadata as image_metadata

from .scene_common import AdoptOutcome, SceneDef, SceneConfig


class SceneManager:
    def __init__(
        self,
        dbc: DBConnection | None = None,
        config: SceneConfig = 'default',
        subdir_scenes: str | None = None,
        verbose: int = 1,
    ) -> None:
        if dbc is None:
            self._verbose = verbose
            self._dbc = DBConnection(config=config, verbose=self._verbose)
        else:
            self._dbc = dbc
            self._verbose = self._dbc._verbose
        self._subdir_scenes = subdir_scenes
        self._collection = SceneDef.COLLECTION_SCENES

    @property
    def config(self):
        return self._dbc.config

    @property
    def root(self) -> Path:
        return self._dbc.config.root

    @property
    def url_scenes(self) -> Path:
        url = self.root
        if self._subdir_scenes is not None:
            url = url / self._subdir_scenes
        return url

    @property
    def url_thumbs(self) -> Path:
        return self._dbc.config.thumbs_url

    @staticmethod
    def _url_dotfile_path(url: str | Path) -> Path:
        url = Path(url)
        return url / SceneDef.DOTFILE_SCENE

    @classmethod
    def _url_dotfile_load(cls, url: str | Path) -> None | dict:
        dotfile = cls._url_dotfile_path(url)
        data = cls._json_read(dotfile)
        if not data:
            return None
        return data

    @classmethod
    def id_from_dotfile(cls, url: str | Path) -> None | str:
        data = cls._url_dotfile_load(url)
        if data is None:
            return None
        id = data.get(SceneDef.FIELD_OID, None)
        return id

    def id_from_url(self, url: str | Path) -> None | str:
        data = self.data_from_url_db(url)
        if data is None:
            return None
        return str(data.get(SceneDef.FIELD_OID, ''))

    @property
    def ids(self) -> Generator:
        """Returns a generator of scene oid's for all scenes in the db"""

        docs = self._dbc.find_documents(self._collection, query={})
        for doc in docs:
            yield str(doc['_id'])

    def ids_from_query(self, query: dict) -> Generator:
        docs = self._dbc.find_documents(self._collection, query)
        for doc in docs:
            yield str(doc['_id'])

    def ids_from_rating(self, min: int, max: int, labels: list[str] | None = None) -> Generator:
        query: dict[str, Any] = {SceneDef.FIELD_RATING: {'$gte': min, '$lte': max}}
        if labels is not None:
            if not labels:
                query |= {SceneDef.FIELD_LABELS: {'$size': 0}}
            else:
                query |= {SceneDef.FIELD_LABELS: {'$in': labels}}

        print(f'query: [{query}]', file=sys.stderr)
        return self.ids_from_query(query)

    def data_from_id(self, id: Any) -> dict | None:
        oid = self._dbc.to_oid(id)
        if oid is None:
            return None
        docs = self._dbc.documents_from_oid(self._collection, oid)
        if len(docs) == 0:
            return None
        elif len(docs) == 1:
            return docs[0]

        self._log(f'DATABASE INCONSISTENCY: id {id} is multiple', level='error')
        return None

    def data_from_url_db(self, url: str | Path) -> dict | None:
        docs = self._dbc.find_documents(self._collection, query={SceneDef.FIELD_URL: str(url)})
        if len(docs) == 0:
            return None
        elif len(docs) == 1:
            return docs[0]

        self._log(f'DATABASE INCONSISTENCY: id {id} is multiple', level='error')
        return None

    def data_from_url_dotfile(self, url: str | Path) -> dict | None:
        id = self.id_from_dotfile(url)
        data = self.data_from_id(id)
        return data

    def url_from_id(self, id: Any) -> Path | None:
        data = self.data_from_id(id)
        if data is None:
            return None
        return data.get(SceneDef.FIELD_URL, None)

    def is_id(self, id: str) -> bool:
        if self.data_from_id(id) is not None:
            return True
        return False

    def update_from_url(self, url: str | Path) -> str | None:
        url = Path(url)
        if not url.exists():
            self._log(f'url does not exist: {url}')
            return
        elif not url.is_dir():
            self._log(f'url is not a dir: {url}')
            return

        oid = self.id_from_dotfile(url)
        self._log(f'{url} got dotfile oid {oid}', level='debug')

        oid = self.id_from_url(url)
        self._log(f'{url} got oid {oid}', level='debug')

        if oid is None:
            if oid is None:
                # add new scene
                meta = self._meta_init_data(url=url)
                meta = self._scene_update(meta)
                if meta is not None:
                    oid = meta.get(SceneDef.FIELD_OID, None)
            data_dotfile = self._dotfile_init_data(oid=oid)
            self._dotfile_update(url, data_dotfile)
        else:
            if oid is None:
                # update url in db with check of db url?
                self._log(f'DATABASE INCONSISTENCY: {url} has no oid, TODO fix!', level='error')
            elif oid != oid:
                # update url in db with check of db url?
                self._log(
                    f'DATABASE INCONSISTENCY: {url} dotfile oid does match to oid, TODO fix!',
                    level='error',
                )
            else:
                # all good: scene db and dotfile consistent
                pass

        return oid

    def _dotfile_init_data(self, oid: str | None = None) -> dict:
        data = {}

        if not oid:
            oid = None
        if oid is not None:
            data |= {SceneDef.FIELD_OID: str(oid)}

        return data

    def _dotfile_update(self, url: Path | str, up_data: dict) -> dict | None:
        url = Path(url)

        if not url.exists():
            self._log(f'url {url} not exists for dotfile: {up_data}', level='warning')
            return None

        dotfile = url / SceneDef.DOTFILE_SCENE
        data = self._json_read(dotfile)
        data |= up_data
        self._json_write(dotfile, data)

    def _meta_init_data(self, url: Path | str | None = None) -> dict:
        data = {}

        if not url:
            url = None
        if url is not None:
            data |= {SceneDef.FIELD_URL: str(url)}
        return data

    def _scene_update(self, meta: dict) -> dict | None:
        url = meta.get(SceneDef.FIELD_URL, '')
        if not url:
            self._log('no url found in meta!')
            return None

        # does scene url already exist?
        oid = self.id_from_url(url)
        if oid is None:
            # scene docs are born with both timestamps so the scan staleness
            # rule (board tasks 69/70) is sound from creation on
            insert_data = dict(meta)
            insert_data |= {SceneDef.FIELD_TIMESTAMP_CREATED: SceneDef.now_ts()}
            insert_data |= SceneDef.update_ts()
            oid = self._dbc.insert_document(self._collection, insert_data)
            self._log('scene added: {url}.', level='message')
        else:
            self._log(f'scene not added, already exists: {url} oid={oid}.', level='debug')

        if oid:
            meta |= {SceneDef.FIELD_OID: oid}

        return meta

    def new_scene_from_urls(
        self,
        _urls: list[str] | list[Path] | str | Path,
        subdir_scenes: str | None = None,
        register: bool = False,
    ) -> list[str] | None:
        """Create new scene(s) from image/dir urls and return the new scene ids.

        subdir_scenes: per-call override of the target scene subdir (under the DB
            root), applied only for this call — no need to rebuild the manager.
            Omitted / None keeps the constructor's ``subdir_scenes`` value.
        register: when True, bulk-register the imported images (insert image
            docs + rename to the ``0rig___<id>`` convention) so the scenes'
            ``imgs_active`` reflects them. Default False preserves the curator's
            manual register/prototype choice (import creates the scene doc only).
        """
        if not isinstance(_urls, list):
            urls = [_urls]
        else:
            urls = _urls
        urls_img = [Path(url) for url in urls if is_img_or_vid(url)]

        prev_subdir = self._subdir_scenes
        if subdir_scenes is not None:
            self._subdir_scenes = subdir_scenes
        try:
            ret = []
            if urls_img:
                oid = self._scene_new_imgs(urls_img)
                if oid is not None:
                    ret.append(oid)

            dirs = [Path(url) for url in urls if is_dir(url)]
            for dir in dirs:
                oid = self._scene_new_dir(dir)
                if oid is not None:
                    ret.append(oid)
        finally:
            self._subdir_scenes = prev_subdir

        # maintenance write point (board task 66): seed scenes_linked
        # (ids_scene_enh + ids_scene_db.sourced) from the imported images'
        # enhancer payloads at creation time.
        for oid in ret:
            self.scene_seed_enh_links(oid)

        if register:
            self._register_scene_imgs(ret)

        return ret

    def _register_scene_imgs(self, scene_ids: list[str]) -> None:
        """Register the raw images of freshly imported scenes.

        Mirrors the curator flow (``script/aidb_scene.py`` imgs_register):
        ``register_from_url`` inserts each image doc and renames the file to the
        ``0rig___<id>`` convention; ``scene.update`` then refreshes the scene so
        ``imgs_active`` counts the registered images.
        """
        im = self.scene_image_manager()
        for oid in scene_ids:
            scene = self.scene_from_id_or_url(oid)
            for url_img in list(scene.urls_img):
                im.register_from_url(url_img)
            scene.update(force=True)

    def _scene_new_imgs(self, url_imgs: list[str] | list[Path]) -> None | str:
        """
        private: makes a new scene from a list of img urls.

        url_imgs should be completely valid (e.g. generated by is_img_or_vid(), they're not gonna be checked again.

        returns the new oid:str
        """

        if not url_imgs:
            return None

        # scene dir + doc first, then each file through the membership
        # primitive — one code path places files (board task 70)
        self.url_scenes.mkdir(parents=True, exist_ok=True)
        dir_scene = subdir_inc(self.url_scenes)
        dir_scene.mkdir(parents=True, exist_ok=True)
        oid = self.update_from_url(dir_scene)
        if not oid:
            self._log(f'scene creation failed for {dir_scene}', level='error')
            return None
        for url_img in url_imgs:
            if not Path(url_img).is_file():
                continue
            self._img_to_scene_dir(Path(url_img), oid, move=True)
        return oid

    def _scene_new_dir(self, dir: str | Path) -> None | str:
        return self._scene_new_imgs(imgs_and_vids_from_url(dir))

    @property
    def _dbc_scenes(self):
        return self._dbc._get_collection(self._collection)

    def _dbc_to_id(self, id: str):
        self._dbc.to_oid(id)

    def scene_touch(self, scene_id: str) -> bool:
        """Bump a scene's ``timestamp_updated`` — single-field ``$set``, no
        full-document store. The membership primitives (`img_add` /
        `img_delete` / `img_move`) call this iff a change actually happened,
        which keeps the scan staleness rule of board task 69 sound."""
        dbc = self._dbc_scenes
        oid = self._dbc.to_oid(scene_id)
        if dbc is None or oid is None:
            return False
        result = dbc.update_one({SceneDef.FIELD_OID: oid}, {'$set': SceneDef.update_ts()})
        return result is not None and result.matched_count > 0

    def scene_scan_write(self, scene_id: str, prop: str, value: dict) -> bool:
        """Persist one scan property sub-doc (``$set scan.<prop>``, board
        task 69). Machine bookkeeping: deliberately does NOT bump
        ``timestamp_updated`` — a scan write must never mark the scene stale
        for its own skip rule."""
        dbc = self._dbc_scenes
        oid = self._dbc.to_oid(scene_id)
        if dbc is None or oid is None:
            return False
        field = f'{SceneDef.FIELD_SCAN}.{prop}'
        result = dbc.update_one({SceneDef.FIELD_OID: oid}, {'$set': {field: value}})
        return result is not None and result.matched_count > 0

    def scan_all(
        self,
        props: list[str] | None = None,
        force: bool = False,
        query: dict | None = None,
    ) -> dict[str, dict[str, str]]:
        """Batch sweep of `Scene.scan` over all scenes (optionally
        query-restricted). Near-free when everything is fresh: a fresh
        property is skipped on its ``ts`` alone — no model load, no file
        reads. Returns ``{scene_id: {prop: outcome}}`` (see `Scene.scan`);
        scenes that fail to instantiate are logged and skipped."""
        from .scene import Scene

        results: dict[str, dict[str, str]] = {}
        ids = self.ids if query is None else self.ids_from_query(query)
        for sid in ids:
            try:
                scene = Scene(self, sid)
            except (FileNotFoundError, ValueError) as e:
                self._log(f'scan_all: skip scene[{sid}]: {e}', level='warning')
                continue
            results[sid] = scene.scan(props=props, force=force)
        return results

    def _db_update_scene(self, data: dict) -> bool:
        dbc = self._dbc_scenes
        if dbc is None:
            return False

        oid = data.get(SceneDef.FIELD_OID, None)
        if oid is None:
            return False
        update_data = SceneDef.prepare_data_for_update(data)

        filter = {SceneDef.FIELD_OID: oid}
        update = {'$set': update_data}
        result = dbc.update_one(filter, update)

        if result is None:
            return False
        return True

    def url_from_registered_file(self, reg_file: str | Path) -> Path | None:
        res = SceneDef.id_and_prefix_from_filename(reg_file)
        if res is None:
            return None
        return self.url_from_id(res[0])

    def scene_from_id_or_url(self, id_or_url: str | Path) -> Any:
        from .scene import Scene

        return Scene(self, id_or_url)

    def display_image(self, scene_id: str) -> str | None:
        """Return the image url the scene app displays for ``scene_id``.

        Read-only and deterministic: the highest-rated registered image (newest
        ``updated`` among ties), else the newest render file in the scene
        folder. This mirrors the source of the grid thumbnail exactly (see
        `Scene.url_display` / `Scene._update_thumbnail`), so a consumer resolving
        a scene id gets the same image the app shows — not a mtime-newest guess.

        Returns the url as a str, or None for an unknown/empty scene (no
        registered images and no renders on disk). No mutation of scenes/images.
        """
        try:
            scene = self.scene_from_id_or_url(scene_id)
        except (FileNotFoundError, ValueError) as e:
            self._log(f'display_image: cannot resolve scene[{scene_id}]: {e}', level='warning')
            return None
        url = scene.url_display
        return str(url) if url else None

    def scene_adopt_img(
        self, url: str | Path, move: bool = True, subdir_new: str | None = None
    ) -> str | None | bool:
        """Attach a loose render file to the DB scene it belongs to.

        Renders carrying a 1xlasm-enhancer iteration payload (own or inherited,
        per `ait.tools.images.metadata()` trust rules) belong to the creative
        unit of their ENHANCER scene, not to the DB scene of their source image
        (board FEATURE REQ task 66): the payload's ``scene_id`` is matched
        against ``scenes_linked.ids_scene_enh`` across scenes — a scene already
        holding the file byte-identical wins, else a single match adopts there,
        multiple matches tie-break by the newest file mtime in the scene
        folder. No match: with ``subdir_new`` a new scene is created under that
        subdir (seeded with the enhancer id), without it the call returns
        ``None`` — the distinct "unmatched, subdir needed" outcome — with zero
        side effects, so the caller can ask the operator and retry.

        Successful payload adoptions keep ``ids_scene_enh`` current AND record
        the derivation: the payload's ``url`` is resolved to its origin DB
        scene (registered image → its ``scene_id``, else the url's directory
        as a scene url) and appended to the adopting scene's
        ``scenes_linked.ids_scene_db.sourced`` — one-way child → origin, the
        origin scene gets no backlink. Payload-path successes return an
        `AdoptOutcome` (a str carrying ``id_origin`` / ``origin_unresolved``):
        an unresolvable origin never blocks the adoption, but the miss is
        visible in the result instead of silent.

        Payload-less renders resolve as before (board task 65): the file's own
        registration (``0rig___<id>`` filename or a registered image url) wins;
        otherwise the ``parent_metadata`` provenance chain is followed. When
        nothing resolves, the call returns ``False`` and touches neither disk
        nor DB.

        On success the file is moved (default) or, with ``move=False``, copied
        into the scene folder as an *unregistered* render — no image document
        is inserted, no canonical field is written; registration stays a
        separate curator step. Returns the resolved scene id (truthy str).

        A same-named file already in the scene folder is only accepted when it
        is byte-identical (idempotent re-adopt: ``move=True`` then removes the
        source); differing content aborts with ``False`` — never overwrite.
        """
        url = Path(url)
        if not url.is_file() or not is_img_or_vid(url):
            self._log(f'scene_adopt_img: not an image file: {url}', level='warning')
            return False

        md = image_metadata(url)
        id_enh = self._enh_id_from_metadata(md)
        if id_enh is not None:
            return self._adopt_by_enh_id(url, id_enh, move, subdir_new, md)

        scene_id = self._scene_id_for_adoption(url, md)
        if not scene_id:
            self._log(f'scene_adopt_img: no scene resolves for {url}', level='warning')
            return False
        return self._img_to_scene_dir(url, scene_id, move)

    def _img_to_scene_dir(self, url: Path, scene_id: str, move: bool) -> str | bool:
        """Place a file into a scene folder under the never-overwrite rule:
        a same-named file must be byte-identical (idempotent re-adopt), else
        the placement aborts with ``False``.

        The single code path that puts an image file into a scene folder
        (board task 70): iff the file actually lands (no no-op re-adopt, no
        collision abort), the scene's ``timestamp_updated`` is bumped."""
        url_scene = self.url_from_id(scene_id)
        if url_scene is None or not Path(url_scene).is_dir():
            self._log(
                f'scene_adopt_img: scene[{scene_id}] folder missing: {url_scene}', level='error'
            )
            return False

        dest = Path(url_scene) / url.name
        if dest.exists():
            if url.resolve() == dest.resolve():
                return scene_id
            if not filecmp.cmp(url, dest, shallow=False):
                self._log(
                    f'scene_adopt_img: name collision with different content: {dest}',
                    level='error',
                )
                return False
            # idempotent re-adopt: dest already holds the file, membership
            # unchanged — remove the source only, no timestamp bump
            if move:
                url.unlink()
            return scene_id
        elif move:
            shutil.move(str(url), str(dest))
        else:
            shutil.copy2(url, dest)

        self.scene_touch(scene_id)
        self._log(f'scene_adopt_img: {url.name} -> scene[{scene_id}] ({url_scene})')
        return scene_id

    def img_add(self, url: str | Path, scene_id: str, move: bool = True) -> str | bool:
        """Bring an image file from outside the scene DB into a scene's folder
        as an *unregistered* render (board task 70 — membership primitive).

        Never-overwrite rule as in `scene_adopt_img`: a same-named file in the
        scene folder must be byte-identical (idempotent re-add; ``move=True``
        then removes the source), differing content aborts with ``False``.
        No image document is inserted — registration stays a separate curator
        step.

        Timestamp contract: the scene's ``timestamp_updated`` is bumped iff
        the file actually lands — no bump on no-op re-add or abort. Returns
        the scene id (truthy str) on success/no-op, ``False`` otherwise.
        """
        url = Path(url)
        if not url.is_file() or not is_img_or_vid(url):
            self._log(f'img_add: not an image file: {url}', level='warning')
            return False
        return self._img_to_scene_dir(url, scene_id, move)

    def img_delete(self, img_or_url: str | Path) -> bool:
        """Remove an image from its scene (board task 70 — membership
        primitive). Accepts a file url, a registered filename or an image id.

        Registered images are HARD-deleted: the image document is removed
        from `images` together with the file — there is no trash/archive
        tier, the doc's ratings/labels are gone with it. Unregistered files
        must live inside a scene folder; deleting arbitrary files outside the
        scene DB is refused.

        Timestamp contract: the owning scene's ``timestamp_updated`` is
        bumped iff something was actually removed (file and/or doc); resolve
        failures return ``False`` with no bump.
        """
        img, url, scene_id = self._resolve_member(img_or_url)
        if scene_id is None:
            self._log(f'img_delete: not a scene member: {img_or_url}', level='warning')
            return False

        changed = False
        if url is not None and url.is_file():
            url.unlink()
            changed = True
        if img is not None:
            n = self._dbc.delete_document(
                SceneDef.COLLECTION_IMAGES, {SceneDef.FIELD_OID: self._dbc.to_oid(img.id)}
            )
            changed = bool(n) or changed
        if changed:
            self.scene_touch(scene_id)
            self._log(f'img_delete: {img_or_url} removed from scene[{scene_id}]')
        return changed

    def img_move(self, img_or_url: str | Path, scene_id_target: str) -> str | bool:
        """Relocate an image scene→scene (board task 70 — membership
        primitive). Accepts a file url, a registered filename or an image id;
        a source outside any scene degrades to `img_add` semantics (no source
        bump). For a registered image the image doc is updated
        (``url_parent`` / ``url``) so doc ↔ file stay consistently
        resolvable.

        Placement follows the never-overwrite rule (byte-identical dest =
        idempotent, source removed; differing content aborts with ``False``).

        Timestamp contract: ``timestamp_updated`` of source AND target is
        bumped iff that scene actually changed — a no-op (already in the
        target scene) or an abort bumps nothing. Returns the target scene id
        (truthy str) on success/no-op, ``False`` otherwise.
        """
        img, url, scene_src = self._resolve_member(img_or_url)
        if url is None or not url.is_file():
            self._log(f'img_move: no file resolves for: {img_or_url}', level='warning')
            return False

        placed = self._img_to_scene_dir(url, scene_id_target, move=True)
        if not isinstance(placed, str):
            return placed
        if scene_src is not None and scene_src != scene_id_target and not url.exists():
            self.scene_touch(scene_src)
        if img is not None and scene_src != scene_id_target:
            url_target = self.url_from_id(scene_id_target)
            img._data |= {
                SceneDef.FIELD_URL_PARENT: str(url_target),
                SceneDef.FIELD_URL: str(Path(str(url_target)) / url.name),
            }
            img.db_store()
        return placed

    def _resolve_member(self, img_or_url: str | Path) -> tuple[Any | None, Path | None, str | None]:
        """Resolve a membership reference — file url, registered filename or
        image id — to ``(registered image | None, file path | None, owning
        scene id | None)``. The file path may be None for a registered image
        whose file is missing on disk; the scene id comes from the registered
        doc (``url_parent``) or, for unregistered files, the file's directory
        resolved as a scene url."""
        sim = self.scene_image_manager()
        img = None
        url: Path | None = None

        as_path = Path(str(img_or_url))
        if as_path.is_file():
            url = as_path
            id_prefix = SceneDef.id_and_prefix_from_filename(as_path)
            oid = id_prefix[0] if id_prefix is not None else sim.id_from_url(as_path)
            if oid and sim.is_id(oid):
                img = sim.img_from_id(oid)
        elif sim.is_id(str(img_or_url)):
            img = sim.img_from_id(str(img_or_url))
            url = self._registered_file(img)

        if img is not None:
            scene_id = img.scene_id
        elif url is not None:
            scene_id = self.id_from_url(url.parent)
        else:
            scene_id = None
        return img, url, scene_id

    def _registered_file(self, img: Any) -> Path | None:
        """The on-disk file of a registered image: ``url_from_data`` when
        present, else a suffix-agnostic ``0rig___<id>.*`` lookup (registered
        videos keep their own suffix)."""
        url = img.url_from_data
        if url is not None and url.is_file():
            return url
        parent = img._data.get(SceneDef.FIELD_URL_PARENT, None)
        if not parent or not Path(parent).is_dir():
            return None
        pattern = f'{SceneDef.PREFIX_ORIG}{SceneDef.SEPERATOR_ID}{img.id}.*'
        matches = [p for p in Path(parent).glob(pattern) if p.is_file()]
        return matches[0] if matches else None

    def _adopt_by_enh_id(
        self, url: Path, id_enh: str, move: bool, subdir_new: str | None, md: dict | None
    ) -> str | None | bool:
        """Payload routing of `scene_adopt_img`: match the enhancer scene id
        against ``scenes_linked.ids_scene_enh``; see the caller's docstring for
        the win/tie-break/no-match contract and the ``sourced`` maintenance."""
        id_origin = self._origin_scene_from_enh(md)
        if id_origin is None:
            self._log(
                f'scene_adopt_img: origin scene of enhancer payload unresolvable: {url}',
                level='warning',
            )
        matches = self.scene_ids_from_enh_id(id_enh)

        # a matching scene already holding the file byte-identical wins
        target: str | None = None
        for scene_id in matches:
            url_scene = self.url_from_id(scene_id)
            if url_scene is None:
                continue
            dest = Path(url_scene) / url.name
            if dest.is_file() and filecmp.cmp(url, dest, shallow=False):
                target = scene_id
                break

        if target is None and matches:
            target = max(matches, key=self._scene_newest_mtime) if len(matches) > 1 else matches[0]
        if target is not None:
            placed = self._img_to_scene_dir(url, target, move)
            if not isinstance(placed, str):
                return placed
            self.link_scene_enh(placed, id_enh)
            if id_origin is not None:
                self.link_scene_db_sourced(placed, id_origin)
            return AdoptOutcome(placed, id_origin)

        if subdir_new is None:
            self._log(
                f'scene_adopt_img: enhancer scene {id_enh} unmatched, subdir_new needed: {url}',
                level='warning',
            )
            return None
        return self._scene_new_from_enh(url, id_enh, move, subdir_new, id_origin)

    def _scene_new_from_enh(
        self, url: Path, id_enh: str, move: bool, subdir_new: str, id_origin: str | None
    ) -> str | bool:
        """Create a new scene under ``subdir_new`` for an unmatched enhancer
        render: place the file, register the scene doc, seed ``ids_scene_enh``
        and (when the origin resolved) ``ids_scene_db.sourced``."""
        prev_subdir = self._subdir_scenes
        self._subdir_scenes = subdir_new
        try:
            self.url_scenes.mkdir(parents=True, exist_ok=True)
            dir_scene = subdir_inc(self.url_scenes)
            dir_scene.mkdir(parents=True, exist_ok=True)
            scene_id = self.update_from_url(dir_scene)
        finally:
            self._subdir_scenes = prev_subdir

        if not scene_id:
            self._log(f'scene_adopt_img: scene creation failed for {dir_scene}', level='error')
            return False
        placed = self._img_to_scene_dir(url, scene_id, move)
        if not isinstance(placed, str):
            return False
        self.link_scene_enh(scene_id, id_enh)
        if id_origin is not None:
            self.link_scene_db_sourced(scene_id, id_origin)
        self._log(f'scene_adopt_img: {url.name} -> NEW scene[{scene_id}] ({dir_scene})')
        return AdoptOutcome(scene_id, id_origin)

    def _scene_newest_mtime(self, scene_id: str) -> float:
        """Tie-break key for multi-match adoption: newest file mtime in the
        scene folder (folder mtime when it holds no files)."""
        url_scene = self.url_from_id(scene_id)
        if url_scene is None or not Path(url_scene).is_dir():
            return 0.0
        mtimes = [f.stat().st_mtime for f in Path(url_scene).iterdir() if f.is_file()]
        return max(mtimes) if mtimes else Path(url_scene).stat().st_mtime

    @staticmethod
    def _enh_id_from_metadata(md: dict | None) -> str | None:
        """Enhancer scene id of an image's iteration payload (own or inherited
        per `metadata()` trust rules). This id references the enhancer's own
        scene collection — never resolve it against `scenes`."""
        enh = md.get('enhancer') if md else None
        id_enh = enh.get('scene_id') if isinstance(enh, dict) else None
        return id_enh if isinstance(id_enh, str) and id_enh else None

    def scene_ids_from_enh_id(self, id_enh: str) -> list[str]:
        """DB scene ids whose ``scenes_linked.ids_scene_enh`` contains the
        enhancer scene id."""
        query = {f'{SceneDef.FIELD_SCENES_LINKED}.{SceneDef.FIELD_IDS_SCENE_ENH}': id_enh}
        return list(self.ids_from_query(query))

    def link_scene_enh(self, scene_id: str, id_enh: str) -> bool:
        """Ensure an enhancer scene id is present in a scene's
        ``scenes_linked.ids_scene_enh`` ($addToSet — idempotent). Machine
        bookkeeping only: deliberately does not bump ``timestamp_updated``."""
        field = f'{SceneDef.FIELD_SCENES_LINKED}.{SceneDef.FIELD_IDS_SCENE_ENH}'
        return self._link_add_to_set(scene_id, field, id_enh)

    def link_scene_db_sourced(self, scene_id: str, id_origin: str) -> bool:
        """Ensure an origin DB scene id is present in a scene's
        ``scenes_linked.ids_scene_db.sourced`` ($addToSet — idempotent).
        ONE-WAY child → origin: the origin scene gets no backlink, and a
        self-link is refused. Machine bookkeeping only: deliberately does not
        bump ``timestamp_updated``."""
        if id_origin == scene_id:
            return False
        field = (
            f'{SceneDef.FIELD_SCENES_LINKED}.{SceneDef.FIELD_IDS_SCENE_DB}'
            f'.{SceneDef.FIELD_LINKED_SOURCED}'
        )
        return self._link_add_to_set(scene_id, field, id_origin)

    def _link_add_to_set(self, scene_id: str, field: str, value: str) -> bool:
        dbc = self._dbc_scenes
        oid = self._dbc.to_oid(scene_id)
        if dbc is None or oid is None:
            return False
        result = dbc.update_one({SceneDef.FIELD_OID: oid}, {'$addToSet': {field: value}})
        return result is not None

    def scene_scan_enh_ids(self, scene_id: str) -> list[str]:
        """Read-only: the enhancer scene ids found in the payloads of a scene
        folder's images."""
        return self.scene_scan_links(scene_id)[SceneDef.FIELD_IDS_SCENE_ENH]

    def scene_scan_links(self, scene_id: str) -> dict[str, list[str]]:
        """Read-only: the enhancer scene ids found in the payloads of a scene
        folder's images plus the origin DB scenes those payloads' ``url``
        resolve to — ``{ids_scene_enh: [...], sourced: [...]}``, both dedup'd,
        self-links excluded from ``sourced``."""
        found: dict[str, list[str]] = {
            SceneDef.FIELD_IDS_SCENE_ENH: [],
            SceneDef.FIELD_LINKED_SOURCED: [],
        }
        url_scene = self.url_from_id(scene_id)
        if url_scene is None or not Path(url_scene).is_dir():
            return found
        for url_img in imgs_and_vids_from_url(url_scene):
            md = image_metadata(url_img)
            id_enh = self._enh_id_from_metadata(md)
            if id_enh is None:
                continue
            if id_enh not in found[SceneDef.FIELD_IDS_SCENE_ENH]:
                found[SceneDef.FIELD_IDS_SCENE_ENH].append(id_enh)
            id_origin = self._origin_scene_from_enh(md)
            if (
                id_origin is not None
                and id_origin != scene_id
                and id_origin not in found[SceneDef.FIELD_LINKED_SOURCED]
            ):
                found[SceneDef.FIELD_LINKED_SOURCED].append(id_origin)
        return found

    def scene_seed_enh_links(self, scene_id: str) -> dict[str, list[str]]:
        """Scan a scene folder's images for enhancer payloads and write the
        found enhancer scene ids into ``scenes_linked.ids_scene_enh`` and the
        payloads' resolved origin scenes into ``scenes_linked.ids_scene_db.
        sourced``. Returns the `scene_scan_links` result. Shared by the
        creation-time seeding and the one-time backfill
        (`script/scenes_linked_backfill.py`)."""
        found = self.scene_scan_links(scene_id)
        for id_enh in found[SceneDef.FIELD_IDS_SCENE_ENH]:
            self.link_scene_enh(scene_id, id_enh)
        for id_origin in found[SceneDef.FIELD_LINKED_SOURCED]:
            self.link_scene_db_sourced(scene_id, id_origin)
        return found

    def _origin_scene_from_enh(self, md: dict | None) -> str | None:
        """Origin DB scene of an enhancer payload: its ``url`` (the enhancer
        scene's canonical image path) resolved as a registered image
        (→ ``SceneImage.scene_id``), else the url's directory as a scene url.
        None when unresolvable (url null / outside the scenes tree / dir not
        a scene). Only the payload's ``url`` bridges to DB scenes — the
        payload's ``scene_id`` is an ENHANCER scene id and never resolves
        against `scenes`."""
        enh = md.get('enhancer') if md else None
        url = enh.get('url') if isinstance(enh, dict) else None
        if not isinstance(url, str) or not url:
            return None
        scene_id = self._scene_of_registered_img(url)
        if scene_id:
            return scene_id
        return self.id_from_url(Path(url).parent)

    def _scene_id_for_adoption(self, url: Path, md: dict | None = None) -> str | None:
        """Resolve the owning scene of an image file, DB + provenance only.

        Order: the file's own registered identity (filename id, then image-url
        lookup), then the embedded ``parent_metadata`` chain (nested ``parent``
        envelopes, depth-capped) — each parent tried as registered image
        (filename id / url), then its directory as a scene url.
        """
        scene_id = self._scene_of_registered_img(url)
        if scene_id:
            return scene_id

        if md is None:
            md = image_metadata(url)
        parent = md.get('parent') if md else None
        for _ in range(8):
            if not isinstance(parent, dict):
                break
            # 'url' as defined by the ait.image.metadata.v1 parent envelope
            parent_url = parent.get('url')
            if isinstance(parent_url, str) and parent_url:
                scene_id = self._scene_of_registered_img(parent_url)
                if scene_id:
                    return scene_id
                scene_id = self.id_from_url(Path(parent_url).parent)
                if scene_id:
                    return scene_id
            parent = parent.get('parent')
        return None

    def _scene_of_registered_img(self, img_url: str | Path) -> str | None:
        """Owning scene of a REGISTERED image url (``0rig___<id>`` filename or
        an image-url lookup); None for unregistered/unknown files."""
        sim = self.scene_image_manager()
        id_prefix = SceneDef.id_and_prefix_from_filename(img_url)
        oid = id_prefix[0] if id_prefix is not None else sim.id_from_url(img_url)
        if oid and sim.is_id(oid):
            img = sim.img_from_id(oid)
            return img.scene_id if img is not None else None
        return None

    def scenes_update(self) -> None:
        from .scene import Scene

        for id in self.ids:
            try:
                scene = Scene(self, id)
            except FileNotFoundError as e:
                self._log(str(e), level='warning')
                continue
            except ValueError as e:
                self._log(str(e), level='warning')
                continue
            scene.update()

    def scene_image_manager(self) -> SceneImageManager:
        return SceneImageManager(dbc=self._dbc)

    def scene_set_manager(self) -> Any:
        from .scene_set_manager import SceneSetManager

        return SceneSetManager(dbc=self._dbc)

    @staticmethod
    def _json_read(url: Path) -> dict:
        if not url.exists():
            return {}

        data = {}
        with url.open('r') as f:
            data = json.load(f)
        return data

    @staticmethod
    def _json_write(url: Path, data: dict) -> None:
        if not url.parent.exists():
            return
        with url.open('w') as f:
            json.dump(data, f)

    def _log(self, msg: str, level: str = 'info') -> None:
        if self._verbose > 0:
            print(f'[scm:{level}] {msg}', file=sys.stderr)
