from pathlib import Path
import sys
import pprint
from typing import Any, Callable, ClassVar, Generator

from ait.tools.files import imgs_from_url, img_latest_from_url
from ait.tools.images import thumbnail_to_url

from .scene_common import SceneDef
from .scene_manager import SceneManager
from .scene_image import SceneImage


class Scene:
    def __init__(self, scm: SceneManager, id_or_url: Any) -> None:
        self._scm = scm

        data = None

        url = None
        if isinstance(id_or_url, Path):
            url = id_or_url
        if isinstance(id_or_url, str):
            try:
                url = Path(id_or_url)
            except Exception:
                url = None
        if url is not None:
            data = scm.data_from_url_dotfile(url)
            if data is None:
                data = scm.data_from_url_db(url)
                url = None

        if data is None:
            url = None
            data = scm.data_from_id(id_or_url)

        if data is None:
            raise ValueError('Scene does not exist')

        self._data = data
        self._url_called = url

        if self._url_called is None:
            if not self.url.exists():
                raise FileNotFoundError(
                    f"Scene (id={self.id}, url={self.url}) doesn't physically exist!"
                )

    @property
    def id(self) -> str:
        return str(self._data.get(SceneDef.FIELD_OID, ''))

    @property
    def data(self) -> dict:
        return self._data

    @property
    def url(self) -> Path:
        return self.url_from_data

    @property
    def urls_img(self) -> Generator:
        for url in imgs_from_url(self.url):
            yield url

    @property
    def ids_img(self) -> Generator:
        for url_img in self.urls_img:
            id = SceneDef.id_from_filename_orig(url_img)
            if id is not None:
                yield id

    @property
    def imgs(self) -> list[SceneImage]:
        im = self._scm.scene_image_manager()
        imgs: list[SceneImage] = []
        for id_img in self.ids_img:
            img = im.img_from_id(id_img)
            if img is None:
                continue
            imgs.append(img)
        return imgs

    @property
    def imgs_sorted(self) -> list[SceneImage]:
        return SceneDef.sort_by_rating(self.imgs)

    @property
    def imgs_active(self) -> list[SceneImage]:
        """Registered images that are NOT flagged as prototype."""
        return [img for img in self.imgs if not img.prototype]

    @property
    def imgs_prototype(self) -> list[SceneImage]:
        """Registered images that ARE flagged as prototype."""
        return [img for img in self.imgs if img.prototype]

    @property
    def is_prototype(self) -> bool:
        """
        True iff the scene has at least one registered image and every
        registered image has `prototype=True`. Empty scenes return False.
        """
        seen = False
        for img in self.imgs:
            seen = True
            if not img.prototype:
                return False
        return seen

    def make_prototype(self) -> tuple[int, int, int]:
        """
        Flag every registered image of this scene as prototype and persist.

        Returns `(n_done, n_skipped, n_failed)`:
          - n_done:    images flagged in this call (were not prototype yet)
          - n_skipped: images already flagged
          - n_failed:  images whose persist raised
        """
        n_done = 0
        n_skipped = 0
        n_failed = 0
        for img in self.imgs:
            if img.prototype:
                n_skipped += 1
                continue
            try:
                img.set_prototype(True)
                img.db_store()
                n_done += 1
            except Exception:
                n_failed += 1
        return n_done, n_skipped, n_failed

    def ids_img_from_query(self, query: dict) -> Generator:
        im = self._scm.scene_image_manager()

        ids_img = [id_img for id_img in self.ids_img]
        for id_img in im.ids_img_from_query(query, ids=ids_img):
            yield id_img

    def imgs_from_query(self, query: dict) -> Generator:
        im = self._scm.scene_image_manager()

        ids_img = [id_img for id_img in self.ids_img]
        return im.imgs_from_query(query, ids=ids_img)

    @property
    def url_thumbnail(self) -> Path:
        filename_thumbnail = SceneDef.filename_thumbnail_from_id(self.id)
        if filename_thumbnail is None:
            raise ValueError("Filename for thumbnail couldn't be created!")
        return self._scm.url_thumbs / filename_thumbnail

    @property
    def url_from_data(self) -> Path:
        return Path(self._data.get(SceneDef.FIELD_URL, ''))

    @property
    def img_display(self) -> SceneImage | None:
        """The registered image the scene app displays for this scene, or None.

        Selection: registered images reduced to the highest rating, newest
        ``updated`` first. Returns None when the scene has no registered images
        (the app then falls back to the newest render on disk — see
        `url_display`). Read-only, deterministic. Single source of truth shared
        with `_update_thumbnail`, so it can never diverge from the grid.
        """
        imgs = SceneDef.sort_by_timestamp_updated(SceneDef.reduce_by_rating_highest(self.imgs))
        return imgs[0] if imgs else None

    @property
    def url_display(self) -> Path | None:
        """The single image url the scene app displays for this scene.

        Matches the source of the grid thumbnail (see `_update_thumbnail`):
          1. `img_display` (highest-rated registered image, newest updated), else
          2. the newest render file in the scene folder.
        This is the full-resolution image the thumbnail is generated from — the
        image to read/replicate, not the downsized thumbnail. Returns None only
        for a scene with neither registered images nor renders on disk.
        Read-only, deterministic w.r.t. DB + folder state.
        """
        img = self.img_display
        if img is not None:
            return img.url_from_data
        return img_latest_from_url(self.url)

    def _url_sync(self) -> bool:
        """
        If scene was successfully instanciated from a specific url, this url
        will be synced to the url in the database.
        Warning: the url stored in the database will be overwritten and no checks
        of physical existence will be applied!
        """
        if self._url_called is None:
            return False
        url = str(self._url_called)
        if str(self.url_from_data) != url:
            self._data |= {SceneDef.FIELD_URL: url}
            return self.db_store()
        return False

    def update(self, force: bool = False) -> None:
        # add init data, if not present
        self._init_data()

        # scene url sync
        if self._url_sync():
            self._log(f'synced url[{self._url_called}]', level='info')

        # imgs sync
        # looks reg imgs in the scene root and syncs their:
        #   - urls
        for img in self.imgs:
            img_parent = img.data.get(SceneDef.FIELD_URL_PARENT, None)
            if img_parent != self.url:
                img._data |= {SceneDef.FIELD_URL_PARENT: str(self.url)}
                # img._dbstore()

        if self._update_thumbnail(force):
            self._log('thumbnail update.', level='info')

        # rating
        # if scene has reg imgs, set rating at least to img_reg
        if len([id_reg for id_reg in self.ids_img]) > 0:
            rating = self.data.get(SceneDef.FIELD_RATING, SceneDef.RATING_INIT)
            if rating < SceneDef.RATING_MIN_IMG_REG:
                self._data |= {SceneDef.FIELD_RATING: SceneDef.RATING_MIN_IMG_REG}

        # store
        if self.db_store():
            self._log('data update.', level='info')

    def _update_thumbnail(self, force: bool = False) -> bool:
        """
        prio:
        1. latest reg img
        2. latest non reg img
        """
        url_latest: Path | None = None
        ts_latest = 0.0
        # 1. reg imgs (shares the selection with `img_display`/`url_display`)
        img = self.img_display
        if img is not None:
            url_latest = img.url_from_data
            ts_latest = SceneDef.get_timestamp_update_from_data(img)

        # 2. non-reg imgs
        if url_latest is None:
            url_latest = img_latest_from_url(self.url)
            if url_latest is None:
                return False
            ts_latest = url_latest.stat().st_ctime

        if self.url_thumbnail.exists():
            ts_thumbnail = self.url_thumbnail.stat().st_ctime
            if ts_thumbnail > ts_latest:
                if not force:
                    return False
        thumbnail_to_url(url_latest, self.url_thumbnail, size=self._scm.config.thumbs_size)
        return True

    def _init_data(self) -> None:
        # rating
        if self._data.get(SceneDef.FIELD_RATING, None) is None:
            self.set_rating(self.rating)
        # labels
        if self._data.get(SceneDef.FIELD_LABELS, None) is None:
            self.set_labels(self.labels)

    # ------------------------------------------------------------------
    # scene self-scan (board task 69): per-property cached derived state
    # ------------------------------------------------------------------

    def scan(self, props: list[str] | None = None, force: bool = False) -> dict[str, str]:
        """Compute/refresh cached derived properties of this scene.

        Iterates `SCAN_REGISTRY` (or the given ``props`` subset) and
        recomputes a property only when it is missing, ``force=True``,
        ``timestamp_updated > scan[prop].ts``, or its optional
        `_SCAN_STALE_EXTRA` trigger fires (e.g. stored-vs-requested model
        mismatch). Pure DB-timestamp semantics: files appearing on disk
        alone do NOT trigger a recompute — the membership API (board task
        70) guarantees the bump for sanctioned changes; hand-filed files
        need ``force=True``.

        Fresh values are persisted per property via
        `SceneManager.scene_scan_write` — a targeted ``$set scan.<prop>``
        that deliberately does not bump ``timestamp_updated`` — and stamped
        with their own ``ts`` AFTER computing, so a fresh property stays
        fresh until the next real scene change.

        Returns ``{prop: outcome}`` with outcome one of ``'computed'`` /
        ``'skipped'`` / ``'failed'`` (not computable or write failed) /
        ``'unknown'`` (no registry entry).
        """
        names = list(self.SCAN_REGISTRY) if props is None else props
        stored = self._data.get(SceneDef.FIELD_SCAN)
        scan_doc: dict[str, Any] = dict(stored) if isinstance(stored, dict) else {}
        ts_updated = self._data.get(SceneDef.FIELD_TIMESTAMP_UPDATED) or 0.0

        result: dict[str, str] = {}
        for name in names:
            fn = self.SCAN_REGISTRY.get(name)
            if fn is None:
                self._log(f'scan: unknown property: {name}', level='warning')
                result[name] = 'unknown'
                continue
            if not force and self._scan_is_fresh(name, scan_doc.get(name), ts_updated):
                result[name] = 'skipped'
                continue
            value = fn(self)
            if value is None:
                result[name] = 'failed'
                continue
            value = dict(value)
            value[SceneDef.FIELD_SCAN_TS] = SceneDef.now_ts()
            if not self._scm.scene_scan_write(self.id, name, value):
                result[name] = 'failed'
                continue
            scan_doc[name] = value
            result[name] = 'computed'
            self._log(f'scan: {name} computed', level='info')

        self._data[SceneDef.FIELD_SCAN] = scan_doc
        return result

    def _scan_is_fresh(self, name: str, cur: Any, ts_updated: float) -> bool:
        """Skip rule of `scan()`: a stored property value is fresh iff it has
        a ``ts`` not older than the scene's ``timestamp_updated`` and its
        optional extra staleness trigger does not fire. Never loads a model."""
        if not isinstance(cur, dict):
            return False
        ts = cur.get(SceneDef.FIELD_SCAN_TS)
        if not isinstance(ts, (int, float)):
            return False
        if ts_updated > ts:
            return False
        stale_fn = self._SCAN_STALE_EXTRA.get(name)
        if stale_fn is not None and stale_fn(cur):
            return False
        return True

    def _scan_embedding(self) -> dict | None:
        """Scan property ``embedding``: scene-level dinov2 aggregate over ALL
        image files in the scene folder — registered, unregistered and
        prototype alike (`urls_img`).

        Two vectors side by side, deliberately NOT combined (board task 69):
        ``mean`` is the component-wise mean of the per-image embeddings,
        stored as computed (not re-normalized) — cosine on the re-normalized
        mean gives scene↔scene similarity directly on the calibrated dinov2
        scale (board task 68: cluster ≥0.775, attach ≥0.65); ``sigma3`` is
        the component-wise 3·std, enabling a per-component band test
        (diagonal-covariance style) for single-image membership.

        Per-image vectors come from `ait.tools.images.embed(store=True)` —
        PNG-chunk caching on purpose, so a re-scan after adding one image
        only runs inference for the new file (the resulting PNG byte
        mutation is accepted; see the `scene_adopt_img` byte-identity
        caveat). Returns None (→ outcome 'failed') when no image embeds.
        """
        import numpy as np

        from ait.tools.images import EMBED_MODEL_DEFAULT, embed

        urls = list(self.urls_img)
        vecs = [v for v in embed(urls, model=EMBED_MODEL_DEFAULT, store=True) if v is not None]
        if not vecs:
            self._log('scan: embedding: no embeddable images', level='warning')
            return None
        arr = np.stack(vecs).astype(float)
        return {
            SceneDef.FIELD_SCAN_MODEL: EMBED_MODEL_DEFAULT,
            SceneDef.FIELD_SCAN_N_IMGS: len(vecs),
            SceneDef.FIELD_SCAN_MEAN: arr.mean(axis=0).tolist(),
            SceneDef.FIELD_SCAN_SIGMA3: (3.0 * arr.std(axis=0)).tolist(),
        }

    @staticmethod
    def _scan_embedding_stale(cur: dict) -> bool:
        """Extra recompute trigger for ``embedding``: the stored value was
        computed with a different model than the current default."""
        from ait.tools.images import EMBED_MODEL_DEFAULT

        return cur.get(SceneDef.FIELD_SCAN_MODEL) != EMBED_MODEL_DEFAULT

    # Property registry: name → compute fn returning the value sub-doc
    # (WITHOUT `ts` — `scan()` stamps it) or None when not computable.
    # Adding a property = one entry here + one compute method; an extra
    # per-property staleness trigger (evaluated on the stored value doc,
    # no model load) is optional via `_SCAN_STALE_EXTRA`.
    SCAN_REGISTRY: ClassVar[dict[str, Callable[['Scene'], dict | None]]] = {
        SceneDef.SCAN_PROP_EMBEDDING: _scan_embedding,
    }
    _SCAN_STALE_EXTRA: ClassVar[dict[str, Callable[[dict], bool]]] = {
        SceneDef.SCAN_PROP_EMBEDDING: _scan_embedding_stale,
    }

    # @property
    # def rating(self) -> int: ...
    # def set_rating(self, val: int | str) -> None: ...
    # @property
    # def labels(self) -> list[str]: ...
    # def set_labels(self, val: list[str]) -> None: ...
    # def push_label(self, val: str) -> None: ...
    # def pop_label(self, val: str) -> None: ...
    # def switch_label(self, val: str) -> None: ...
    # @property
    # def super_labels(self) -> list[str]: ...
    # def push_super_label(self, val: str) -> None: ...
    # def pop_super_label(self, val: str) -> None: ...
    # def switch_super_label(self, val: str) -> None: ...
    # def db_store(self) -> bool: ...

    # Sceneical
    @property
    def rating(self) -> int:
        """
        Returns the rating as int.

        If rating isn't set, the init value is given.
        """
        get_data = self._data.get(SceneDef.FIELD_RATING, SceneDef.RATING_INIT)
        return get_data

    def set_rating(self, value: int | str) -> None:
        value = int(value)
        if value < SceneDef.RATING_MIN:
            value = SceneDef.RATING_MIN
        if value > SceneDef.RATING_MAX:
            value = SceneDef.RATING_MAX

        set_data = {SceneDef.FIELD_RATING: value}
        self._data |= set_data
        return

    @property
    def labels(self) -> list[str]:
        """
        Returns the labels as a list of strings.

        If labels aren't set, an empty list is given.
        """
        get_data = self._data.get(SceneDef.FIELD_LABELS, [])
        return get_data

    def set_labels(self, value: list[str]) -> None:
        if not isinstance(value, list):
            return

        set_data = {SceneDef.FIELD_LABELS: list(set(value))}
        self._data |= set_data
        return

    def push_label(self, label: str) -> None:
        """
        pushes a label to the labels.
        """
        labels = self.labels
        labels.append(label)
        labels = list(set(labels))
        self.set_labels(labels)
        return

    def pop_label(self, label: str) -> None:
        """
        pops a label from the labels.
        """
        labels = set(self.labels)
        labels.discard(label)
        labels = list(labels)
        self.set_labels(labels)
        return

    def switch_label(self, label: str) -> None:
        """
        switches a label from the labels.
        """
        if label in self.labels:
            self.pop_label(label)
        else:
            self.push_label(label)
        return

    def db_store(self) -> bool:
        return self._scm._db_update_scene(self._data)

    def __str__(self) -> str:
        ret = f'url: {self._url_called}\n'
        ret += 'data: ' + pprint.pformat(self._data)
        return ret

    def _log(self, msg: str, level: str = 'info') -> None:
        print(f'[scene id({self.id}):{level}] {msg}', file=sys.stderr)
