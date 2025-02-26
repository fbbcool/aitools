from pathlib import Path
from typing import Final, Generator, TypedDict

import pandas as pd


from PIL import Image

from .captions import Captions
from .selection import Selection
from .pools import pools

POOL_IDX_NAME: Final = "pool"
POOL_IDX_SUFFIX: Final = ".index"
POOL_IMG_SUFFIXES: Final = [".jpg", ".JPG", ".jpeg", ".JPEG", ".png", ".PNG", ".webp"]

class PoolItemDict(TypedDict):
    img: Image.Image | None = None
    img_url: Path | None = None
    img_caps: Captions | None = None

class Pool:
    def __init__(self, pool: str, force: bool = False):
        self.root = pools.url_pool(pool)
        self.df: pd.DataFrame
        self.selection: Selection

        if not self.root.is_dir():
            print(f"error: no pool found ({str(self.root)})!")
            return
        
        self._index(force=force)
        

    def _index(self, force: bool = False) -> None:
        if not force:
            if self.load_index(descr=None):
                return

        rows:list[PoolItemDict] = []
        for url_img in self._urls_img:
            row = PoolItemDict()
            row["img"] = None
            row["img_url"] = url_img
            row["img_caps"] = None
            rows.append(row)
        if not rows:
            print(f"error: no imgs found in pool ({str(self.root)})!")
            return
        columns = list(rows[0].keys())
        self.df = pd.DataFrame(rows, columns=columns)
        self.selection = Selection(self.df)
        self.selection.all
        
    def load_index(self, descr: str | None = None) -> bool:
        return False
    def save_index(self, descr: str | None = None, overwrite: bool = False) -> None:
        pass

    def get_image(self, idx: int) -> Image.Image:

        pass

    def make_train(self, resize: int | None = None) -> None:
        pass

    @property
    def _urls_img(self) -> Generator:
        for file in self.root.iterdir():
            if not file.is_file():
                continue
            if file.suffix in POOL_IMG_SUFFIXES:
                yield file
    def __getitem__(self, index: int) -> PoolItemDict:
        ret = self.df.iloc[index].to_dict(into=PoolItemDict)
        return ret
    def __setitem__(self, index, item: PoolItemDict):
        columns = list(item.keys())
        for column in columns:
            self.df.at[index, column] = item[column]