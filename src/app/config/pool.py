from pathlib import Path
from typing import Final, Generator, Literal, TypedDict

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

class TagAction(TypedDict):
    action: Literal["delete", "deselect","deselect_notags", "replace", "no_action", "undef"]
    payload: str

class TagsSummary(TypedDict):
    selection: Selection
    action: TagAction

class Pool:
    def __init__(self, poolname: str | None = None, force: bool = False):
        self.name : str | None = poolname
        if self.name is None:
            return
        self.root = pools.url_pool(self.name)
        self.df: pd.DataFrame
        self.selection: Selection
        self.tags: dict = {}

        if not self.root.is_dir():
            print(f"error: no pool found ({str(self.root)})!")
            self.name = None
            return
        
        self._index(force=force)
        

    def _index(self, force: bool = False) -> None:
        if not force:
            if self.load_index(descr=None):
                return

        rows:list[PoolItemDict] = []
        for url_img in self._urls_img:
            row = PoolItemDict()
            url_wd14 = Path(url_img).with_suffix(".caption_wd14")
            caption = Captions()
            caption["wd14"] = []
            if url_wd14.exists():
                with url_wd14.open() as f:
                    caption["wd14"] = [f.read()]
            row["img"] = None
            row["img_url"] = url_img
            row["img_caps"] = caption
            rows.append(row)
        if not rows:
            print(f"error: no imgs found in pool ({str(self.root)})!")
            self.name = None
            return
        columns = list(rows[0].keys())
        self.df = pd.DataFrame(rows, columns=columns)
        self.selection = Selection(self.df)
        self.selection.all
        self._build_tags_summary
        
    def load_index(self, descr: str | None = None) -> bool:
        return False
    def save_index(self, descr: str | None = None, overwrite: bool = False) -> None:
        pass

    def get_image(self, idx: int) -> Image.Image:
        if self[idx]["img"] is None:
            with Image.open(self[idx]["img_url"]) as im:
                self[idx] |= {"img": im}
        return self[idx]["img"]

    def make_train(self, resize: int | None = None) -> None:
        pass

    @property
    def _urls_img(self) -> Generator:
        for file in self.root.iterdir():
            if not file.is_file():
                continue
            if file.suffix in POOL_IMG_SUFFIXES:
                yield file


    @property
    def _build_tags_summary(self) -> None:
        for idx, row in self:
            tags = row["img_caps"]["wd14"][0].split(",")
            for tag in tags:
                if tag in self.tags.keys():
                    tag_summary: TagsSummary = self.tags[tag]
                    tag_summary["selection"] += idx
                else:
                    tag_summary = TagsSummary()
                    tag_summary["selection"] = self.selection.clone_empty
                    tag_summary["selection"] += idx
                    tag_summary["action"] = TagAction()
                    tag_summary["action"]["action"] = "undef"
                    tag_summary["action"]["payload"] = ""
                    self.tags |= {tag: tag_summary}
    @property
    def reduce_tags_summary(self) -> None:
        tags = {}
        for tag in self.tags.keys():
            tag_summary: TagsSummary = self.tags[tag]
            if tag_summary["action"]["action"] == "no_action":
                continue
            if tag_summary["action"]["action"] == "undef":
                continue
            tags |= {tag: tag_summary}
        self.tags = tags

    @property
    def rebuild_tags(self) -> None:
        for idx, row in self:
            new_tags = []
            tags = row["img_caps"]["wd14"][0].split(",")
            for tag in tags:
                if tag in self.tags:
                    tag_summary: TagsSummary = self.tags[tag]
                    action = tag_summary["action"]["action"]
                    payload = tag_summary["action"]["payload"]
                    if action == "deselect":
                        self.selection -= idx
                    elif action == "delete":
                        tag = ""
                    elif action == "replace":
                        tag = payload
                if tag:
                    new_tags.append(tag)
            self[idx]["img_caps"]["train"] = new_tags
    @property
    def tags_ordered(self) -> list[str]:
        data = []
        for tag, tag_sum in self.tags.items():
            data.append({"tag": tag, "size": len(tag_sum["selection"])})
        df = pd.DataFrame(data)
        df = df.sort_values("size")
        return list(reversed(df["tag"].to_list()))


    def __getitem__(self, index: int) -> PoolItemDict:
        ret = self.df.iloc[index].to_dict(into=PoolItemDict)
        return ret
    def __setitem__(self, index, item: PoolItemDict):
        columns = list(item.keys())
        for column in columns:
            self.df.at[index, column] = item[column]
    def __len__(self):
        if self.name is None:
            return 0
        return len(self.df.index)
    def __iter__(self):
        n = len(self)
        i=0
        while i < n:
            yield i, self[i]
            i+=1
