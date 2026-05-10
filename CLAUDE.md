# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment setup

Code in `src/` is imported as top-level packages (e.g. `from aidb import ...`, `from ait.tools.files import ...`), so `PYTHONPATH` **must** include `src/`. The `.vscode/settings.json` sets this for editors; shells should source `000_install/aitools.sh` (training/remote) or `activate.fish` (local), which export:

- `HOME_AIT` — repo root (used by `Trainer`, `Templater`, scripts via `os.environ`)
- `WORKSPACE` — working tree where training/installer artifacts go (defaults `/workspace`)
- `CONF_AIT` — points to `$HOME_AIT/conf` (read by `ConfigReader`, `AInstallerDB`)
- `AIDB_SCENE_CONFIG` — selects the MongoDB/storage profile: `prod`, `test`, or `default` (= `prod`)
- `AIDB_SCENE_DEFAULT` — default scene subdirectory used by `aidb_scene.py`

Several modules access these env vars at **import time** (e.g. `templater.py`, `ainstall.py`), so importing `aidb`/`trainer`/`templater` without them set will raise `KeyError`.

## Common commands

```sh
# install deps (pick one based on environment)
pip install -r requirements.txt           # local dev (includes gradio, pytest)
pip install -r requirements_remote.txt    # remote/training boxes (no gradio)
pip install -r requirements_local.txt     # extras: jupyterlab, mypy, black, flake8

# tests (pytest is the framework, despite what AGENTS.md suggests)
pytest                                    # full suite (test/)
pytest test/test_scene.py::TestSceneManager::test_instance   # single test
# tests require a reachable MongoDB matching conf/aidb/dbc_scenes_test.yaml

# type check / format
mypy src/                                 # config in mypy.ini
ruff check src/ && ruff format src/       # config in pyproject.toml (line-length 100, single quotes)

# main CLI (driven by clipboard contents)
python script/aidb_scene.py <cmd> [config=test|prod] [params...]
# cmds: app | new | update | url | move | imgs_info | imgs_register | imgs_rate

# launch the gradio scene-rating app
python script/aidb_scene.py app           # serves on :7861

# training (remote box, after sourcing 000_install/aitools.sh)
train_install                             # clones diffusion-pipe + aitools, installs deps
train_run                                 # runs train_prepare.py then ./train.sh

# install ComfyUI / model variants (works off conf/models/*.json model DB)
python script/ainstall_comfyui.py $HOME_COMFY <group>   # group e.g. qwen:edit, wan22:t2v
```

## Architecture

The repo is two layered systems sharing a single `src/` package tree:

### 1. `aidb` — MongoDB-backed scene/image dataset manager

`aidb` ("AI database") tracks training-image collections in MongoDB. Three collections — `scenes`, `images`, `sets` — are abstracted by parallel manager/entity pairs:

- `SceneManager` ↔ `Scene`
- `SceneImageManager` ↔ `SceneImage`
- `SceneSetManager` ↔ `SceneSet`

All managers hang off a single `DBConnection`, which is configured via `ConfigReader` reading `conf/aidb/dbc_scenes_<config>.yaml`. The `<config>` is selected by the `SceneConfig = Literal['test', 'prod', 'default']` argument threaded through every manager constructor — never hardcode; pass it through.

`SceneDef` (in `src/aidb/scene/scene_common.py`) is the schema-of-truth: every collection field name, filename prefix (`0rig`, `thumbnail`, `train`), separator (`___`), and rating range lives there as `Final` constants. Use `SceneDef.FIELD_*` rather than string literals when reading/writing documents, and use `SceneDef.filename_*_from_id` / `id_and_prefix_from_filename` helpers for path↔id conversion.

ObjectIds are stored as `ObjectId` in Mongo but exchanged as `str` in public APIs; `DBConnection.to_oid()` handles the conversion safely. `HFDataset` (in `src/aidb/scene/hfdataset.py`) is the bridge that publishes a `SceneSet` to a Hugging Face dataset repo for training.

The Gradio review/rating UI is in `src/aidb/app/` (cell components + `tab_search_and_rate.py`), launched by `script/aidb_scene.py app`.

### 2. `ait` + `trainer` + `templater` — install & train pipeline

Training a model is orchestrated by `trainer.Trainer` (`src/trainer/trainer.py`), which composes three pieces:

- **`AInstaller`** (`src/ait/install/ainstall.py`) reads `conf/models/models_*.json` (a layered JSON DB keyed by `group/variant/target`) and downloads model files from HF/CivitAI/HTTP. Variants are selected by strings like `qwen:edit`, `train_zimage:turbo`. Same installer is reused by `script/ainstall_comfyui.py` for runtime model installs.
- **`Templater`** (`src/templater/templater.py`) renders config files from `conf/diffpipe/templates/`. Variables use `___` as a parameter separator (`model___ckpt_path` → `[model] ckpt_path = ...` in toml). Empty strings auto-disable a line by prepending `#`. Both the dataset toml and the diffusion-pipe toml are produced this way.
- **`HFDataset`** pulls training images and triggers from the HF hub.

`Trainer.__init__` runs the whole pipeline synchronously: install → render dataset toml → render trainer toml → materialize dataset symlinks → write `train.sh`. The user-facing entrypoint is `script/train_prepare.py`, which is meant to be edited directly to set `model`, `variant`, `dataset_repo_ids`, and config overrides — there is **no CLI argument parsing**; this script is part of the configuration surface.

### Cross-cutting

- `src/ait/tools/files.py` is the canonical place for file-type predicates (`is_img_or_vid`, `is_dir`) and url/dir helpers used across both layers.
- Notebooks in `nb/` are exploratory; the `.vscode/settings.json` sets `jupyter.notebookFileRoot` to `src/` so notebooks can `import aidb`/`ait` directly.
- `src/depr_*` directories are deprecated — don't extend them; if you find yourself reading them to understand current behavior, double-check against the non-`depr_` equivalent first.
- **`claude_*` MongoDB collections** — Claude may freely create, read, and write to collections prefixed `claude_` in the active `scenes_<config>` database (alongside the canonical `scenes` / `images` / `sets`) to persist AI-side scratch state: caption-priority rankings, batch run artifacts, scoring caches. These are not source-of-truth; the canonical collections are unaffected. Schema is whatever the writing tool defines — document it in the slash command or script that owns the collection. Direct access is via `DBConnection._get_collection('claude_xxx')`.
- **Caption skins (`conf/skins/*.json`)** — A single JSON per captioning recipe holds source fields (entities, interaction, label groups, rules, forbidden vocab, concepts, model & LoRA refs) plus a derived `_built` block (composed directive, flat label lookup, reverse indices, union forbidden, source_hash). Schema lives at `conf/skins/_schema.json`. The build phase (`python -m ait.caption.skin_build <name>`) composes derived fields from source. Use-time consumers — `JoyNG` (pure runtime, `src/ait/caption/joy_ng.py`), `JoySceneDBNG` (orchestrator, `src/ait/caption/joy_scenedb_ng.py`), and the `/v1-status` / `/todo-ai` slash commands — read derived fields via `SkinRegistry().get(name)` (`src/ait/caption/skin.py`). Today only `1xlasm` lives there; the legacy `Joy` / `JoySceneDB` classes still back the other 15 caption recipes (the keys in `joy.py`'s `CONTENT_SYSTEM`/`CONTENT_PROMPT` dicts) until each migrates to its own JSON.

## Code style (project-specific points beyond AGENTS.md)

- Line length 100, single-quoted strings (ruff format), Python 3.10+ syntax (`X | None`, `list[str]`).
- `Final` for module/class constants is used pervasively in `SceneDef` and similar — match that pattern when adding constants there.
- Logging convention: each manager has a `_log(self, msg, level='info')` that prints `[<tag>:<level>] msg` only when `self._verbose > 0`. Use it instead of bare `print` inside these classes.
