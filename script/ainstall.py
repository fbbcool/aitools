from enum import Enum, auto
import os
import sys
from typing import Final, Generator, Literal
from huggingface_hub import hf_hub_download, snapshot_download
import requests
from tqdm import tqdm
from git import Repo  # pip install gitpython
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

AIT_PATH_CONF: Final = os.environ("CONF_AIT")


def make_installer_db(
    srcdir: str = AIT_PATH_CONF, prefixes: list[str] = ["model_", "ainst_"]
) -> dict:
    """
    schema: /group/variant/target/[target_config]
    """
    srcdir = Path(srcdir)
    db: dict = {}
    return db


class AInstaller:
    def __init__(
        self,
        db: dict,
        group: str,
        install_type: Literal["comfyui", "diffpipe"] = "comfyui",
    ):
        self.db = db
        split = group.split(":")
        self.group = split[0]
        self.type = install_type
        self.variants = ["common"]
        if len(split) > 1:
            self.variants.append(split[1])
        self.install()

    def install(self):
        [self._install_item(item) for item in self._items]

    @property
    def _items(self) -> Generator:
        group = self.db.get(self.group, None)
        if group is None:
            return None

        for variant in self.variants:
            variant: dict | None = group.get(variant, None)
            if variant is None:
                continue
            for target in variant.keys():
                for config in target:
                    yield self._make_item(group, variant, target, config)

    def _make_item(self, group: str, variant: str, target: str, config: dict):
        item: dict = {
            "group": group,
            "variant": variant,
            "target": target,
            "config": config,
            "type": self.type,
        }
        return item

    def _install_item(self, item: dict) -> None:
        str_installer = f"_install_item_{item['type']}"
        installer = getattr(self, str_installer, None)
        if callable(installer):
            installer(item)
        else:
            print(f"warning: no installer for type[{item['type']}]")

    def _install_item_comfyui(self, item: dict) -> None:
        print("installler comfyui:/n")
        print(item)

    def _install_item_diffpipe(self, item: dict) -> None:
        print("installler diffpipe:/n")
        print(item)


if __name__ == "__main__":
    str_group = sys.argv[1]

    db: dict = make_installer_db()

    AInstaller(db, str_group)
