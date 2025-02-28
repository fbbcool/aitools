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
        self.tags: dict = {}
        self.name : str | None = poolname
        if self.name is None:
            return
        self.root = pools.url_pool(self.name)
        self.df: pd.DataFrame
        self.selection: Selection

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
            caption = Captions()
            
            url_tag = Path(url_img).with_suffix(".caption_wd14")
            caption["wd14"] = []
            if url_tag.exists():
                with url_tag.open() as f:
                    caption["wd14"] = [f.read()]
            
            url_tag = Path(url_img).with_suffix(".txt")
            caption["train"] = []
            if url_tag.exists():
                with url_tag.open() as f:
                    caption["train"] = [f.read()]
            
            
            
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
    def tags_summary_reduced(self) -> dict:
        tags = {}
        for tag in self.tags.keys():
            tag_summary: TagsSummary = self.tags[tag]
            if tag_summary["action"]["action"] == "no_action":
                continue
            if tag_summary["action"]["action"] == "undef":
                continue
            tags |= {tag: tag_summary}
        return tags

    def build_tags_train(self, trigger: str) -> None:
        tags_summary_reduced = self.tags_summary_reduced
        for idx, row in self:
            new_tags = [trigger]
            wd14 = row["img_caps"]["wd14"]
            if not wd14:
                return
            tags = wd14[0].split(",")
            for tag in tags:
                if tag in tags_summary_reduced.keys():
                    tag_summary: TagsSummary = tags_summary_reduced[tag]
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
    def safe_tags_train(self) -> None:
        for idx, row in self:
            tags = row["img_caps"]["train"]
            if tags:
                tags_joined = tags[0]
            else:
                return
            for tag in tags[1:]:
                tags_joined += f",{tag}"

            url_img = row["img_url"]
            url_tag = Path(url_img).with_suffix(".txt")
            with url_tag.open("t+w") as f:
                f.write(tags_joined)
                f.close()

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
