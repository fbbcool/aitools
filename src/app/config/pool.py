from pathlib import Path
import shutil
from typing import Final, Generator, Literal, TypedDict
import pandas as pd

from .caption import CaptionItem, Caption
from .selection import Selection

class PoolItem(TypedDict):
    orig: Path | None
    cap: CaptionItem | None
    orig_hd: Path | None
    cap_hd: CaptionItem | None
    orig_unref: Path | None
    cap_unref: CaptionItem | None

    @staticmethod
    def defaults() -> 'PoolItem':
        return PoolItem(
            orig=None,
            cap=CaptionItem.defaults(),
            orig_hd=None,
            cap_hd=CaptionItem.defaults(),
            orig_unref=None,
            cap_unref=CaptionItem.defaults(),
        )

class TagAction(TypedDict):
    action: Literal["delete", "deselect","deselect_notags", "replace", "no_action", "undef"]
    payload: str

class TagsSummary(TypedDict):
    selection: Selection
    action: TagAction

class TrainItem(TypedDict):
    idx: int
    img_url_pool: Path
    caps: CaptionItem

class TrainTagAction(TypedDict):
    action: Literal["delete", "deselect","deselect_notags", "replace", "no_action", "undef"]
    payload: str
    selection: list[int] # of TrainItem idx, which should correspond to pool selection idxs! Valuable tag score data!

class TrainCfg:
    poolname: str = "None"
    id: str = "id_empty"
    trigger: str = "1trigger"
    size: int = 150
    wh: int = 1024
    poolitem: list[TrainItem]
    tagaction: dict[str, TrainTagAction] # actions to convert wd14 to train tags

class PoolCfg(TypedDict):
    tags: dict[str, PoolItem]
    selection: Selection
    train: TrainCfg

class Pool:
    FOLDER_ORIGS: Final = "origs"
    POOL_IDX_NAME: Final = "pool"
    POOL_IDX_SUFFIX: Final = ".index"
    POOL_IMG_TARGET_SUFFIX: Final = ".png"
    POOL_IMG_SUFFIXES: Final = list(set([POOL_IMG_TARGET_SUFFIX, ".jpg", ".JPG", ".jpeg", ".JPEG", ".png", ".PNG", ".webp",".tiff",".TIFF"]))
    POOL_FILES_SKIP: Final = [".DS_Store"]
    POOL_FOLDER_ORIG: Final = "origs"
    POOL_SIZE_MAX: Final = 1000

    def __init__(self, root: Path | str, force: bool = False):
        self.name : str | None = None
        self.root = Path(root)
        if not self.root.exists():
            return
        if self.root.is_dir():
            self.name = self.root.stem
        else:
            return
        
        self.tags: dict[str, PoolItem] = {}
        self.df: pd.DataFrame
        self.selection: Selection

        self._index(force=force)
    
    def _index(self, force: bool = False) -> None:
        if not force:
            if self.load_index(descr=None):
                return

        # orig files must be sorted first:
        cands = []
        for cand in self._origs_by_file:
            cands.append(str(cand))
        cands.sort()

        # orig files split into ok/nok
        rows:list[PoolItem] = []
        rows_rejected:list[PoolItem] = []
        for cand in cands:
            cand = Path(cand)
            
            row = PoolItem.defaults()

            cap = Caption.dict_from_img(cand)
            row["orig"] = cand
            row["cap"] = cap

            url_hd = self.get_hd(cand)
            if (url_hd):
                cap_hd = Caption.dict_from_img(url_hd)
                row["orig_hd"] = url_hd
                row["cap_hd"] = cap_hd

            url_unref = self.get_unref(cand)
            if (url_unref):
                cap_unref = Caption.dict_from_img(url_unref)
                row["orig_unref"] = url_unref
                row["cap_unref"] = cap_unref

            if cand.stem == f"{len(rows):04}":
                rows.append(row)
            else:
                rows_rejected.append(row)
            
        # now, deal with the noks (w/ captions!)
        for nok in rows_rejected:
            idx = len(rows)
            name_new = f"{idx:04}"
            
            self.move_poolitem_by_name(nok, name_new)

            rows.append(nok)
        
        
        # put the final data into the dataframe
        if not rows:
            print(f"error: no imgs found in pool ({str(self.root)})!")
            self.name = None
            return
        columns = list(rows[0].keys())
        self.df = pd.DataFrame(rows, columns=columns)

        self.selection = Selection(self.df)
        self.selection.all
        self._build_tags_summary
    
    def move_poolitem_by_name(self, item: PoolItem, name: str) -> None:
        """
        moves all inner url data in the item as well as physically the files.
        
        HANDLE WITH CARE!
        """
        
        # cap needs to moved first
        self._move_poolitem_cap_by_name(item, name)
        
        # then origs
        for types_img in ["orig", "orig_hd", "orig_unref"]:
            src: Path = item[types_img]
            if src:
                target = Path(src.parent, f"{name}").with_suffix(src.suffix)
                src.rename(target)
                item[types_img] = target
    
    def _move_poolitem_cap_by_name(self, item: PoolItem, name: str) -> None:
        """
        moves all inner url data in the item as well as physically the files.
        
        HANDLE WITH CARE!
        """
        for type_img in ["orig", "orig_hd", "orig_unref"]:
            url_img = item[type_img]
            url_caps = Caption.urls_from_img(url_img)
            for src in url_caps:
                target = Path(src.parent, f"{name}").with_suffix(src.suffix)
                src.rename(target)

    
    @property
    def _build_tags_summary(self) -> None:
        for idx, row in self:
            caps = row["cap"]["wd14"]
            if not caps:
                continue 
            tags = Caption.split_data(caps)
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
    def url_origs(self) -> Path:
        url = Path(self.root, Pool.FOLDER_ORIGS)
        if not url.is_dir():
            return url.mkdir(parents=True)
        return url
    @property
    def url_origs_hd(self) -> Path:
        url = Path(self.root, f"{Pool.FOLDER_ORIGS}_hd")
        if not url.is_dir():
            return url.mkdir(parents=True)
        return url
    @property
    def url_origs_unref(self) -> Path:
        url = Path(self.root, f"{Pool.FOLDER_ORIGS}_unref")
        if not url.is_dir():
            return url.mkdir(parents=True)
        return url

    @property
    def _origs_by_file(self) -> Generator:
        files = []
        for file in self.url_origs.iterdir():
            if not file.is_file():
                continue
            if file.suffix in self.POOL_IMG_SUFFIXES:
                yield file
    @property
    def origs(self) -> Generator:
        for _, orig in self:
            yield orig["orig"]
    @property
    def origs_hd(self) -> Generator:
        for _, orig in self:
            yield orig["orig_hd"]
    @property
    def origs_unref(self) -> Generator:
        for _, orig in self:
            yield orig["orig_unref"]

    def get_hd(self, url_img: Path | str) -> Path | None:
        path = Path(url_img)
        if not path.is_file():
            return
        target = Path(self.url_origs_hd, path.name)
        if not target.is_file():
            return
        return target


    def get_unref(self, url_img: Path | str) -> Path | None:
        path = Path(url_img)
        if not path.is_file():
            return
        target = Path(self.url_origs_unref, path.name)
        if not target.is_file():
            return
        return target


        
    def load_index(self, descr: str | None = None) -> bool:
        return False
    def save_index(self, descr: str | None = None, overwrite: bool = False) -> None:
        pass

    def make_train(self, resize: int | None = None) -> None:
        pass

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


    # CLASS HELPERS
    @classmethod
    def is_img(cls, url: Path | str) -> bool:
        p = Path(url)

        if not p.exists():
            return False
        if p.is_dir():
            return False
        
        suffix = p.suffix
        if suffix in cls.POOL_IMG_SUFFIXES:
            return True
        
        return False

    # TOOLS

    
    @property
    def _files_categorize(self) -> dict[str, list[Path]]:
        """
        categorizes recursivlely all files in a pool and puts them into one of four lists of Paths:
        
        {img:[imgs], cap:[caps], dir:[dirs], unk[unknowns]}
        """
        ret = {
            "img": [],
            "cap": [],
            "dir": [],
            "unknown": [],
            "skip": [],
        }
        for url in self.url_origs.rglob("*"):
            path = Path(url)
            suffix = path.suffix


            if path.name in self.POOL_FILES_SKIP:
                ret["skip"].append(path)
            elif path.name.startswith("."):
                ret["unknown"].append(path)
            elif path.is_dir():
                ret["dir"].append(path)
            elif Caption.is_file(path):
                ret["cap"].append(path)
            elif self.is_img(path):
                ret["img"].append(path)
            else:
                ret["unknown"].append(path)
        return ret
        
    def __getitem__(self, index: int) -> PoolItem:
        ret = self.df.iloc[index].to_dict(into=PoolItem)
        return ret
    def __setitem__(self, index, item: PoolItem):
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

