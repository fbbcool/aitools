from pathlib import Path

from config import config

class Pools:
    def __init__(self, root: Path):
        self.root: Path = root

    @property
    def labels(self) -> list[str]:
        return [f.name for f in self.root.iterdir() if f.is_dir()]

pools: Pools = Pools(config.path_pools)
    

