from pathlib import Path

from .config import config
from .pool import Pool

class Pools:
    def __init__(self, root: Path | str):
        self.root: Path = Path(root)
        self._poolnames: list[str] | None = None

    @property
    def poolnames(self) -> list[str]:
        if not self._poolnames:
            self._poolnames = [f.name for f in self.root.iterdir() if f.is_dir()]
        return self._poolnames
    
    @property
    def pool(self, poolname: str) -> Pool:
        return Pool(poolname)
    
    def url_pool(self, poolname: str):
        return Path(self.root, poolname)
    
    
    def __len__(self):
        return len(self.poolnames)
    
    def __iter__(self):
        n = len(self)
        i=0
        while i < n:
            yield i, self[i]
            i+=1

    def __getitem__(self, index: int | str) -> Pool:
        if isinstance(index,int):
            if index >= len(self):
                raise IndexError(f"no pool with index {index}!")
            poolname = self.poolnames[index]
        elif isinstance(index,str):
            if index in self.poolnames:
                poolname = index
            else:
                raise ValueError(f"couldn't find poolname {poolname}!")

        return Pool(self.url_pool(poolname))

pools: Pools = Pools(config.path_pools)
    

