from pathlib import Path
from typing import TypedDict

class FoldersDict(TypedDict):
    root: str
    workspace: str
    pools: str
    trains: str

class ConfigDict(TypedDict):
    folders: FoldersDict

class Config():
    def __init__(self, config_dict: ConfigDict):
        self._config_dict = config_dict

    @property
    def path_workspace(self) -> Path:
        return Path(self._config_dict["folders"]["root"], self._config_dict["folders"]["workspace"])
    @property
    def path_pools(self) -> Path:
        return self.path_workspace / Path(self._config_dict["folders"]["pools"])


_folders: FoldersDict = {
    "root": "/Volumes/data/Project/AI/REPOS/aitools",
    "workspace": "workspace",
    "pools": "pools",
    "trains": "trains",
}

_config_dict: ConfigDict = {
    "folders": _folders,
}

config: Config = Config(_config_dict)
