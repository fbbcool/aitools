from enum import Enum, auto
import os
import sys
from typing import Final, Generator, Literal
import json
from huggingface_hub import hf_hub_download, snapshot_download
import requests
from tqdm import tqdm
from git import Repo  # pip install gitpython
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from pprint import pprint

AIT_PATH_CONF: Final = f"{os.environ['CONF_AIT']}/models"


class AInstallerDB:
    def __init__(
        self, srcdir: str = AIT_PATH_CONF, prefixes: list[str] = ["models_", "ainst_"]
    ):
        self._db: dict = {}
        self._srcdir: Path = Path(srcdir)
        self._prefixes: list[str] = prefixes

        self._make()

    def _make(self) -> None:
        """
        schema: /group/variant/target/[target_config]
        """
        files = []
        for prefix in self._prefixes:
            for file in self._srcdir.glob(f"{prefix}*.json"):
                files.append(file)

        for file in files:
            print(f"read {file.name}")
            with file.open() as json_data:
                groups = json.load(json_data)
            for group, update_data in groups.items():
                self._update_group(group, update_data)

    def _update_group(self, group: str, data: dict) -> None:
        group_data = self._db.get(group, {})
        for variant, update_data in data.items():
            variant_data = group_data.get(variant, {})
            group_data[variant] = self._update_variant(variant_data, update_data)
        self._db[group] = group_data

    def _update_variant(self, variant: dict, data: dict) -> None:
        for target, update_data in data.items():
            target_data = variant.get(target, [])
            target_data += update_data
            variant[target] = target_data
        return variant

    @property
    def db(self) -> dict:
        return self._db


class AInstaller:
    def __init__(
        self,
        group: str,
        install_type: Literal["comfyui", "diffpipe"] = "comfyui",
    ):
        self.db = AInstallerDB().db
        split = group.split(":")
        self.group = split[0]
        self.type = install_type
        self.variants = []
        if len(split) > 1:
            self.variants.append("common")
            self.variants.append(split[1])
        self.install()

    def install(self):
        for item in self._items:
            self._install_item(item)

    @property
    def _items(self) -> Generator:
        # common group
        print("items for common group:")
        group = self.db.get(self.type, {})
        for variant, data in group.items():
            # no variants given => install all
            # variants given => iinstall explicit
            if self.variants:
                if variant not in self.variants:
                    continue

            variant_data: dict = group.get(variant, {})
            if not variant_data:
                continue

            for target, target_data in variant_data.items():
                for config in target_data:
                    yield self._make_item(self.type, variant, target, config)
        # selected group
        print(f"items for selected group {self.group}:")
        group = self.db.get(self.group, {})
        for variant, data in group.items():
            # no variants given => install all
            # variants given => iinstall explicit
            if self.variants:
                if variant not in self.variants:
                    continue

            variant_data: dict = group.get(variant, {})
            if not variant_data:
                continue

            for target, target_data in variant_data.items():
                for config in target_data:
                    yield self._make_item(self.group, variant, target, config)

    def _make_item(self, group: str, variant: str, target: str, config: dict):
        item: dict = {
            "group": group,
            "variant": variant,
            "target": target,
            "config": config,
            "type": self.type,
        }

        # resolve download method
        method_download = item["config"].get("method_download", "auto")

        if method_download == "auto":
            if item["target"] == "custom_node":
                method_download = "github"
        if method_download == "auto":
            if item["config"].get("link", None) is not None:
                method_download = "civitai"
            elif item["config"].get("repo_id", None) is not None:
                method_download = "huggingface"

        if method_download == "auto":
            # auto couldn't be resolved
            print("Warning: auto download method couldn't be resolved.")

        item["config"] |= {"method_download": method_download}

        return item

    def _install_item(self, item: dict) -> None:
        str_setup = f"_setup_item_{item['type']}"
        setup = getattr(self, str_setup, None)
        if callable(setup):
            setup(item)
        else:
            print(f"warning: no item setup for type[{item['type']}]")
        self._install_item_generic(item)

    def _install_item_generic(self, item: dict) -> None:
        print("*** trying ***")
        pprint(item)
        if item.get("invalid", False):
            print("warning: item is invalid!")
            return
        target_dir = item.get("target_dir", "")
        if not target_dir:
            print("warning: item has no target directory!")
            return

        if item.get("skip", False):
            print("warning: item is skipped!")
            return

        config = item.get("config")
        method = config.get("method_download", "")
        if not method:
            print("warning: item has no download method!")
            return
        elif method == "huggingface":
            print("try download hf:")
            self._install_item_hf(item)
        elif method == "github":
            print("try clone github:")
            self._install_item_git(item)

    def _setup_item_comfyui(self, item: dict) -> dict:
        # build target url
        map_target_dirs = {
            "ckpt": "models/ckpt",
            "vae": "models/vae",
            "controlnet": "models/controlnet",
            "custom_node": "custom_nodes",
            "lora": "models/loras",
            "embedding": "models/embeddings",
            "clip": "models/clip",
            "clip_vision": "models/clip_vision",
            "ipadapter": "models/ipadapter",
            "unet": "models/unet",
            "upscale": "models/upscale_models",
            "diffusor": "models/diffusion_models",
            "transformer": "models/diffusion_models",
            "text_encoder": "models/text_encoders",
        }
        target_dir = map_target_dirs.get(item.get("target", "unknown"), "")
        if not target_dir:
            item["invalid"] = True
            return item

        group = item.get("group", "comfyui")
        target_dir = Path(target_dir)
        if group != self.type:
            target_dir = target_dir / group

        variant = item.get("variant", "common")
        if variant != "common":
            target_dir = target_dir / variant

        # apply subdir
        subdir = item["config"].get("subdir", "")
        file = item["config"].get("file", "")
        if subdir:
            if subdir == "auto":
                # check for high/low
                if "high" in file:
                    subdir = "high"
                if "HIGH" in file:
                    subdir = "high"
                if "low" in file:
                    subdir = "low"
                if "LOW" in file:
                    subdir = "low"
            if subdir != "auto":
                target_dir = target_dir / subdir

        target_dir = Path("/tmp/comfy") / target_dir
        item["target_dir"] = str(target_dir)

    def _setup_item_diffpipe(self, item: dict) -> dict:
        # build target url
        map_target_dirs = {
            "ckpt": "models/ckpt",
            "vae": "models/vae",
            "controlnet": "models/controlnet",
            "custom_node": "custom_nodes",
            "lora": "models/loras",
            "embedding": "models/embeddings",
            "clip": "models/clip",
            "clip_vision": "models/clip_vision",
            "ipadapter": "models/ipadapter",
            "unet": "models/unet",
            "upscale": "models/upscale_models",
            "diffusor": "models/diffusion_models",
            "transformer": "models/diffusion_models",
            "text_encoder": "models/text_encoders",
        }
        target_dir = map_target_dirs.get(item.get("target", "unknown"), "")
        if not target_dir:
            item["invalid"] = 1
            return item
        target_dir = Path(target_dir) / item.get("group")
        variant = item.get("variant", "common")
        if variant != "common":
            target_dir = target_dir / variant
        item["target_dir"] = str(target_dir)

        return item

    def _install_item_hf(self, item: dict) -> None:
        repo_id = item["config"].get("repo_id")
        file = item["config"].get("file", "")
        rename = item["config"].get("rename", "")

        target_dir = Path(item["target_dir"])
        target_dir.mkdir(parents=True, exist_ok=True)

        if not file:
            # use snaphot download
            link = Path(snapshot_download(repo_id=repo_id))
            for sft in Path(link).rglob("*.safetensors"):
                print(Path(sft).relative_to(link))

        else:
            # use hf download
            link = hf_hub_download(repo_id=repo_id, filename=file)
            src = Path(link)

            target_file = src.name
            if rename:
                target_file = Path(rename).with_suffix(src.suffix)
            target = target_dir / target_file

            self._symlink(src, target)

    def _symlink(self, src: str | Path, target: str | Path, directory=False):
        src = str(src)
        target = str(target)
        try:
            os.symlink(src, target, target_is_directory=directory)
        except OSError:
            os.remove(target)
            os.symlink(src, target, target_is_directory=directory)

    def download_wget(self, url: str, fname: str):
        resp = requests.get(url, stream=True)
        total = int(resp.headers.get("content-length", 0))

        fopath, _ = os.path.split(fname)
        if not os.path.exists(fopath):
            os.makedirs(fopath)
        try:
            with (
                open(fname, "wb") as file,
                tqdm(
                    desc=fname,
                    total=total,
                    unit="iB",
                    unit_scale=True,
                    unit_divisor=1024,
                ) as bar,
            ):
                for data in resp.iter_content(chunk_size=1024):
                    size = file.write(data)
                    bar.update(size)
        except Exception as e:
            print(f"Url download went wrong: {url}")
            print(e)

    def _install_item_git(self, item: dict) -> None:
        return
        repo_id = item["config"].get("repo_id")
        target_dir = Path(item["target_dir"])

        url = f"https://github.com/{repo_id}.git"
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        try:
            Repo.clone_from(url, target_dir, recursive=True)
        except Exception as e:
            print(f"Url git clone went wrong: {url} -> {target_dir}")
            print(e)
