# Agent quickstart — using aitools + the scene DB

Orientation for an AI agent that needs to **use** this repo (not refactor it). Read this
first, then `CLAUDE.md` only if you need architecture depth. Scope covered here:
query scenes, create/edit scenes, run the caption/suggest pipeline, use & compile
HF datasets. The training internals (`Trainer`, `AInstaller`, `train_prepare.py`) are
out of scope — see `CLAUDE.md` §Architecture for those.

---

## 0. Preconditions — set env BEFORE importing anything

Several modules read env vars at **import time**; importing `aidb` without them raises
`KeyError`. Source the activation script rather than exporting by hand:

```sh
source activate.fish            # local (fish)   — sets PYTHONPATH=src, HOME_AIT, CONF_AIT, ...
# or, on training/remote boxes:
source 000_install/aitools.sh
```

Key vars (all set by the scripts above):

| var | meaning |
|-----|---------|
| `PYTHONPATH` | must include `src/` — packages import as `aidb`, `ait`, `trainer` |
| `CONF_AIT` | `$HOME_AIT/conf`, read by `ConfigReader` |
| `AIDB_SCENE_CONFIG` | **which DB profile**: `prod`, `test`, or `default` (= `prod`) |
| `AIDB_SCENE_DEFAULT` | default scene subdir for the CLI |

**Pick your profile deliberately.** `test` → `conf/aidb/dbc_scenes_test.yaml` (throwaway,
what the pytest suite uses). `prod` → the real curated dataset. When in doubt, `test`.
Never hardcode the profile in code — thread it through as the `config=` argument.

Sanity check before doing anything else:

```python
from aidb import SceneManager
scm = SceneManager(config='test', verbose=0)   # raises if Mongo unreachable / env unset
```

---

## 1. The object model (30-second version)

Three Mongo collections, each with a **manager** (queries the collection) and an
**entity** (one document):

| collection | manager | entity | what it is |
|-----------|---------|--------|-----------|
| `scenes`  | `SceneManager` | `Scene` | a group of related images |
| `images`  | `SceneImageManager` | `SceneImage` | one image + its labels/captions |
| `sets`    | `SceneSetManager` | `SceneSet` | a *query* over images → a training dataset |

Managers hang off one `DBConnection` (configured by `config=`). Get the sub-managers
from the top one:

```python
scm = SceneManager(config='test')
sim = scm.scene_image_manager()      # SceneImageManager
ssm = scm.scene_set_manager()        # SceneSetManager
```

**ObjectIds are `str` in every public API.** Mongo stores `ObjectId`, but you pass and
receive 24-char hex strings. `DBConnection.to_oid()` converts when you go raw.

`SceneDef` (`src/aidb/scene/scene_common.py`) is the schema-of-truth: every field name,
filename prefix, separator, rating bound is a `Final` constant there. Read documents with
`SceneDef.FIELD_*`, never string literals.

---

## 2. Read / query

```python
# by id
scene = scm.scene_from_id_or_url(scene_id)     # Scene
img   = sim.img_from_id(image_id)              # SceneImage  (None if missing)

# iterate ids
for sid in scm.ids(): ...
for iid in scm.ids_from_rating(min=1, max=5): ...     # rating-filtered

# arbitrary Mongo query
for iid in scm.ids_from_query({SceneDef.FIELD_RATING: {'$gte': 1}}): ...

# on a Scene
scene.imgs_active()        # list[SceneImage], non-suppressed
scene.imgs_sorted()

# read fields on a SceneImage
img.labels_ng              # list[str]  — canonical curator labels
img.hints                  # str | None — canonical curator hint
img.data                  # raw dict
img.data.get(SceneDef.FIELD_CAPTION_JOY)
```

**Semantic image similarity** — "same motif?", dedup, grouping by content
(pixel hashes only catch near-duplicates):

```python
from ait.tools.images import embed

vecs = embed(['/path/a.png', '/path/b.webp', '/path/c.jpg'])  # one batched call
sim = float(vecs[0] @ vecs[1])   # cosine similarity — vectors are L2-normalized
```

One 384-dim L2-normalized float32 numpy vector per input path (png/jpg/webp/gif),
order matching the input; an unreadable file yields `None` in its slot instead of
raising. The model loads once per process and the whole list runs in batched
chunks — call it with the full list, not in a loop. `model=` is a
`group:variant` key into the `conf/models` DB (default `dinov2:small`, see
`conf/models/models_dinov2.json`; `dinov2:base` swaps in the bigger variant —
add new variants in the JSON, not in code); files are materialized locally via
the ait downloader (`ait.install.snapshot_from_db`). Device auto-selects:
batches of **more than 3** readable images run on the GPU when available,
smaller ones on CPU (the model is small enough to coexist with a running
ComfyUI — which is never touched); an explicit `device='cpu'`/`'cuda'` always
wins. `batch_size=` (default 16) bounds memory. Similarity scale with
dinov2:small (calibrated by agent-aidb on enhancer renders, board task 68,
2026-08-21): near-identical pose ≳0.93; same scene, different pose/framing
~0.77–0.93 (same-scene pairs range down to 0.44); different scene ≤0.77
(strongest cross-scene pair measured: 0.768); unrelated images ≲0.3. For
grouping renders into scenes, the validated two-stage rule is: union-find
cluster at cosine ≥0.775, then attach leftover singletons to the group of
their best link when that link is ≥0.65 (true singletons top out at ~0.56).
Recalibrate if the embedding model or render style changes.

**Stored embeddings** — `embed(paths, store=True)` writes each freshly computed
vector back into its PNG as a model-keyed metadata payload: a tEXt chunk named
`embedding-<group>-<variant>` (default `embedding-dinov2-small`, schema
`ait.image.embedding.v1` with `model`, `dim`, `vector`). Any later `embed()`
call with the matching model serves such files straight from the chunk — a
fully stored batch never even loads the model. `refresh=True` ignores stored
payloads and recomputes (rewriting them when combined with `store=True`). The
write is chunk-level: pixels and every other chunk (`prompt`, `workflow`,
`parent_metadata`) stay byte-identical; non-PNG inputs are computed but never
written to. Caveat: storing changes the file's bytes, so a stored copy no
longer byte-matches an unstored duplicate (relevant for `scene_adopt_img`'s
idempotent re-adopt check — store either before distributing copies or on all
of them).

To *only read* stored payloads — no torch, no model load, safe on boxes
without the ML stack:

```python
from ait.tools.images import embed_stored

vecs = embed_stored(paths)     # same list contract as embed();
                               # None = unreadable OR no stored payload
```

**Embedding cheatsheet**

```python
from ait.tools.images import embed, embed_stored

embed(paths)                          # compute (cached files served from chunk)
embed(paths, store=True)              # compute + persist into the PNGs
embed(paths, store=True, refresh=True)# force recompute + rewrite payloads
embed(paths, model='dinov2:base')     # bigger variant (conf/models DB key)
embed(paths, device='cpu')            # pin device (else auto: >3 imgs → GPU)
embed_stored(paths)                   # read-only, no torch/model — never computes
embed_stored(paths, model='dinov2:base')  # payload lookup is model-scoped
```

| aspect | contract |
|---|---|
| return | `list`, one entry per input, order preserved — even for a single path |
| entry | L2-normalized 384-dim float32 numpy vector (`dinov2:small`) |
| n/a → `None` | unreadable/missing file; for `embed_stored` also: no payload, other model, malformed payload, non-PNG. Never raises. |
| similarity | `float(v1 @ v2)` — dot product IS cosine; same scene ~0.77–0.93 (down to 0.44), different scene ≤0.77, unrelated ≲0.3; scene grouping: cluster ≥0.775, attach ≥0.65 (task 68) |
| payload | PNG tEXt chunk `embedding-<group>-<variant>` (e.g. `embedding-dinov2-small`), schema `ait.image.embedding.v1` |
| store | PNG only, pixels + all other chunks byte-identical; changes file bytes (byte-identity checks!) |
| device | auto: >3 images needing compute **and** CUDA available → GPU, else CPU; explicit `device=` wins |
| model | `group:variant` key into `conf/models/models_dinov2.json` — add variants there, not in code |

---

## 3. Create / edit scenes

Scenes are created **from image files/dirs on disk**, not conjured empty:

```python
new_ids = scm.new_scene_from_urls('/path/to/imgs_or_dir')   # list[str] scene ids
scm.scenes_update()                                          # refresh derived state
```

Editing an existing scene or image — mutate via setters, then **persist explicitly**:

```python
img = sim.img_from_id(image_id)
img.set_rating(3)
img.set_labels_ng([...])       # see guardrails before writing this in prod!
img.db_store()                 # <-- nothing is saved until you call this
```

`Scene` has parallel `set_rating` / `set_labels` / `push_label` / `db_store`.
**Rule: every setter is in-memory; a change is durable only after `db_store()`.**

Filing a **loose render** (e.g. a ComfyUI output in `~/Downloads`) into the scene
it belongs to — don't hand-roll the resolve + move:

```python
scene_id = scm.scene_adopt_img('/path/to/render.png')             # move (default)
scene_id = scm.scene_adopt_img('/path/to/render.png', move=False) # copy, keep source
```

**Enhancer renders route differently.** A render carrying a 1xlasm-enhancer
iteration payload (own or inherited, per `ait.tools.images.metadata()` trust
rules) belongs to the creative unit of its *enhancer* scene, **not** to the DB
scene of its source image — the enhancer changed the prompt. Its payload
`scene_id` (an enhancer scene id — never resolve it against the `scenes`
collection) is matched against `scenes_linked.ids_scene_enh` across scenes:

- a matching scene already holding the file byte-identical wins (idempotent);
- exactly one match → adopted there (and the enhancer id is kept present in
  that scene's `ids_scene_enh`);
- multiple matches → the scene whose folder has the newest file mtime wins;
- **no match** → with `subdir_new='some_subdir'` a new scene is created under
  that subdir, seeded with the enhancer id, and the file adopted there;
  **without** `subdir_new` the call returns `None` — the distinct
  "unmatched, subdir needed" outcome — with zero side effects, so you can ask
  the operator for a subdir and retry.

Every successful payload adoption also records the **derivation**: the
payload's `url` (the enhancer scene's canonical image path — the ONLY bridge
to DB scenes) is resolved to its *origin* DB scene (registered image → its
`scene_id`, else the url's directory as a scene url) and appended to the
adopting scene's `scenes_linked.ids_scene_db.sourced`. Links are **one-way
child → origin**: the origin scene gets no backlink. An unresolvable origin
(payload url null / outside the scenes tree / dir not a scene) never blocks
the adoption, but the miss is visible in the result (see outcome contract).

Payload-less renders resolve as before: the file's own registration first, else
the embedded `parent_metadata` provenance chain (`metadata()['parent']` —
parent registered → its scene; else the parent's directory as scene url).

Outcome contract: **truthy str** = adopted scene id; **`None`** = enhancer
payload matched no scene and no `subdir_new` was given; **`False`** = nothing
resolves / never-overwrite collision — on both non-str outcomes **nothing** is
touched on disk or in the DB. Payload-path successes are an `AdoptOutcome`
(exported from `aidb`) — a `str` subclass that compares/serializes as the
scene id and carries `id_origin: str | None` plus `origin_unresolved: bool`,
so an origin miss is in the result, not silent. The file lands as an
*unregistered* render: no image doc is inserted (registration stays a curator
step). A same-named file already in the scene folder is only accepted when
byte-identical (idempotent re-adopt); different content → `False`, never
overwritten.

**Image↔scene membership — use the canonical API (board task 70).** The three
`SceneManager` primitives are the recommended (and only supported) way to
change which images belong to which scene:

```python
scm.img_add('/outside/render.png', scene_id)         # move in (default); move=False copies
scm.img_delete(img_or_url)                           # file url, 0rig___<id> name, or image id
scm.img_move(img_or_url, scene_id_target)            # scene → scene, doc kept consistent
```

- **Timestamp contract**: every call bumps `timestamp_updated` of **every
  involved scene iff a change actually happened** — no bump on a no-op
  (byte-identical re-add, already-in-target move) or an aborted call (name
  collision with different content → `False`). Scene docs are also born with
  `timestamp_created`/`timestamp_updated` at creation. This guarantee is what
  the scene self-scan staleness rule (board task 69) relies on — which is why
  **direct file moves into/out of scene folders are unsupported**: they leave
  the timestamp untouched and the scan cache stale (recoverable only via
  `force`).
- `img_add` places the file as an *unregistered* render under the same
  never-overwrite rule as `scene_adopt_img`; registration stays a curator
  step. `scene_adopt_img` remains the right call for *loose* renders whose
  scene must be resolved — internally it places through the same primitive.
- `img_delete` on a **registered** image is a **hard delete**: the image doc
  is removed from `images` together with the file (no trash tier — ratings/
  labels on that doc are gone). Unregistered files must live inside a scene
  folder; deleting arbitrary files is refused.
- `img_move` of a registered image rewrites the doc (`url_parent`/`url`) so
  doc ↔ file stay resolvable; both scenes get the bump. A source outside any
  scene degrades to add semantics.

**Scene self-scan — cached derived properties (board task 69).** Scene docs
carry a machine-maintained `scan` field: one sub-doc per property, each with
its own `ts` next to its value fields. Recompute happens only when a property
is missing, `force=True`, or `timestamp_updated > scan[prop].ts` — **pure
DB-timestamp semantics**: files appearing on disk alone do NOT trigger a
recompute (the membership API above guarantees the bump for sanctioned
changes; after hand-filing, pass `force=True`). Scan writes are targeted
`$set scan.<prop>` and never bump `timestamp_updated`.

```python
scene.scan()                          # all properties; {prop: 'computed'|'skipped'|...}
scene.scan(props=['embedding'], force=True)
scm.scan_all(query={...})             # batch sweep, near-free when fresh
```

First property `embedding` — scene-level dinov2 aggregate over ALL image
files in the folder (registered, unregistered, prototype alike): `mean`
(component-wise, stored as computed — re-normalize before cosine) and
`sigma3` (component-wise 3·std, for per-component membership band tests),
plus `model`, `n_imgs`, `ts`. Per-image vectors are PNG-chunk cached
(`embed(store=True)` — byte mutation accepted), so a re-scan after adding
one image only infers that file. A stored-vs-default model mismatch also
triggers recompute.

Adding a second property = **one registry entry + one compute function** in
`Scene` (`src/aidb/scene/scene.py`):

```python
def _scan_myprop(self) -> dict | None:      # value sub-doc, WITHOUT ts
    return {SceneDef.FIELD_...: ...}        # None = not computable

SCAN_REGISTRY = {
    SceneDef.SCAN_PROP_EMBEDDING: _scan_embedding,
    SceneDef.SCAN_PROP_MYPROP: _scan_myprop,   # ← that's all
}
```

(`_SCAN_STALE_EXTRA` optionally adds a per-property recompute trigger
evaluated on the stored value doc — e.g. the embedding's model check —
without loading any model.)

**`scenes_linked` semantics** — optional scene-doc object with
`ids_scene_enh` (enhancer scene ids present among the scene's images) and
`ids_scene_db`, an object `{neighbors: [str], sourced: [str]}` of DB-scene →
DB-scene links: `sourced` holds the scenes this scene was derived from
(direct origin only — deeper ancestry stays recoverable transitively;
one-way, no backlinks), `neighbors` is reserved for future association and
unused today. Absent field/keys read as the empty structure — old docs need
no migration (`SceneDef.scenes_linked_from_data`). It is
**machine-maintained bookkeeping, not curator ground truth**: it never
justifies touching `labels_ng`/`hints`/`caption*`/ratings, and machines may
write it without curator confirmation (writes deliberately don't bump
`timestamp_updated`). Maintained by: `scene_adopt_img` (match + create paths,
both keys) and `new_scene_from_urls` (both keys seeded from the imported
images' payloads at creation). **Not** maintained by: manual folder drops +
`update_from_url` / `scenes_update`, and registration/rating/caption flows —
after hand-filing renders, call `scm.scene_seed_enh_links(scene_id)` (seeds
both keys; or rerun `script/scenes_linked_backfill.py`, idempotent) to catch
the links up. The scene-editor UI renders every id in `ids_scene_db`
(sourced + neighbors) as a standard scene cell below the scene's images —
click opens that scene in a new scene-editor tab.

---

## 4. Caption / suggest — use the slash-command API, not raw classes

The captioning pipeline is exposed as slash commands. Prefer these over importing
`Joy*` classes directly — they encode the correct compose→caption→validate order,
route through the persistent GPU server, and respect the curator field rules.

| command | does |
|---------|------|
| `/joy_server start\|stop\|status` | lifecycle for the GPU captioner (loads model once; ~24 GiB VRAM) |
| `/img_suggest <id>` | probe JoyCaption → write `labels_ng_SUGGESTION` / `hints_SUGGESTION` (**never** canonical) |
| `/img_caption <id>` | compose caption_prompt → caption → validate+autofix, for one image |
| `/imgs_*` variants | batch versions (scoped by set/rating) |

GPU prereq: ≥16 GiB free. If the GPU is contested, **ask the user to free it and wait —
never kill ComfyUI yourself.** Start the server once at the top of a session
(`/joy_server start`) so per-image calls are ~5-10 s instead of ~30 s.

---

## 5. HF datasets — read an existing one

`HFDataset` (`src/aidb/scene/hfdataset.py`) bridges a HF dataset repo. It reads
`train/metadata.jsonl` (one line per image: `file_name`, `file_type`, `caption`):

```python
from aidb.scene.hfdataset import HFDataset
hfd = HFDataset('fbbcool/1fem_alexandra')
len(hfd)
for iid in hfd.ids(): hfd.caption_from_id(iid)
hfd.url_file_from_id(iid)      # local cached image path
```

Tokens: `HF_TOKEN` is **read-only**; `HF_TOKEN_RW` is for writes. Use the RW token only
when you actually push.

---

## 6. Compile a SceneSet → training dataset

A `SceneSet` is a saved query over images. `compile()` materializes the matching images
(resized per the set's ratios/resolutions) + `metadata.jsonl` into a local `train/` dir:

```python
ssm = scm.scene_set_manager()
set_id = ssm.make_new(name='my_set', descr='...', query={...}, trigger=None)
sset = ssm.set_from_id_or_name('my_set')
sset.compile()      # writes  <config.train_url>/my_set/train/{images, metadata.jsonl}
```

Notes:
- `trigger` on the set is the caption trigger word; leave `None` for triggerless LoRAs.
- Compile writes to disk only. **Publishing to HF is a separate manual step** and MUST
  land the files under the `train/` prefix or the datasets loader breaks:
  ```python
  from huggingface_hub import upload_folder
  upload_folder(folder_path=str(train_dir), repo_id='fbbcool/my_set',
                repo_type='dataset', path_in_repo='train', token=os.environ['HF_TOKEN_RW'])
  ```

---

## 7. The CLI (clipboard-driven)

`script/aidb_scene.py <cmd>` reads params from the clipboard and writes results back to
it. Commands: `app | new | update | url | move | imgs_info | imgs_register | imgs_rate`.
`config=test|prod` overrides the profile per-invocation.

```sh
python script/aidb_scene.py app          # gradio review/rating UI on :7861
python script/aidb_scene.py imgs_info config=test
```

---

## 8. Guardrails — read before you write

1. **Canonical fields are curator-only.** `labels_ng`, `hints`, and the `caption_*`
   fields on a `SceneImage` are the human curator's source of truth. An agent writes
   them only when the user *explicitly* asks. Suggestions go to the `*_SUGGESTION`
   fields (`set_labels_ng_suggestion` / `set_hints_suggestion`) — those are yours.
2. **`rating >= 1` means curator-locked.** Don't bump ratings unless told to.
3. **Scratch state → `claude_*` collections.** You may freely create/read/write Mongo
   collections prefixed `claude_` in the active DB (via `DBConnection._get_collection`).
   The canonical `scenes`/`images`/`sets` are unaffected. Document the schema wherever
   the tool that owns it lives.
4. **Nothing persists without `db_store()`** (entities) or the manager's insert/update.
5. **`prod` vs `test`.** Default to `test` for experiments. Only touch `prod` when the
   task is explicitly about the real dataset.
6. **GPU:** never kill ComfyUI to free VRAM; report contention and wait.
7. **HF writes** use `HF_TOKEN_RW`; reads use `HF_TOKEN`. Uploads go under `train/`.
8. **`depr_*` dirs are dead** — don't read them to learn current behavior.

---

## Where to look next

- `CLAUDE.md` — full architecture, env setup, training pipeline.
- `src/aidb/scene/scene_common.py` — `SceneDef`, the field/const schema.
- `conf/aidb/dbc_scenes_*.yaml` — DB connection profiles.
- Slash-command definitions — the caption/suggest/validate pipeline API surface.
