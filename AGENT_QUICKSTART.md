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
