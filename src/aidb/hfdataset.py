import json
from pathlib import Path
import shutil
from typing import Final
import jsonlines
from huggingface_hub import hf_hub_download
from datasets import load_dataset
from PIL import Image

map_bodypart: Final = {
    "body": "body",
    "pussy": "pussy",
    "ass": "ass",
    "breast": "breast",
    "face": "face",
    "foot": "foot",
    "leg": "leg",
    "mouth": "mouth",
    "hand": "hand",
    "thigh": "thigh",
    "_step": "stepping on small man",
    "_penis": "penis",
    "+penis": "penis",
    "_1gts0": "",
    "__tbr": "",
}

class HFDatasetImg:
    def __init__(self, repo_id: str, file_meta: str = "metadata.jsonl", force_meta_dl: bool = False):
        self.repo_id = repo_id
        self.file_meta = file_meta
        self._data = None
        self._meta = self._load_meta(force_download=force_meta_dl)
        self._img_files = ["train/" + line["file_name"] for line in self._meta]
        self._tags:list[dict] = [json.loads(line["tags"]) for line in self._meta]
        
        self._prompts:list[str] = [line.get("prompt", "") for line in self._meta]

        self._captions:list[str] = [line.get("caption", "") for line in self._meta]
        self._captions_joy:list[str] = [line.get("caption_joy", "") for line in self._meta]
        for idx, caption in enumerate(self._captions):
            if not caption:
                capjoy = self._captions_joy[idx]
                if capjoy:
                    self._captions[idx] = capjoy
        
        self._ids: list[str] = [Path(file).stem for file in self.img_files]

    def _load_meta(self, force_download:bool = False):
        try:
            file_path = hf_hub_download(repo_id=self.repo_id, filename="train/"+self.file_meta, repo_type="dataset", force_download=force_download)
            if self.file_meta.endswith('.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            elif self.file_meta.endswith('.jsonl'):
                data = []
                with jsonlines.open(file_path) as reader:
                    for obj in reader:
                        data.append(obj)
                return data
            else:
                raise ValueError("Unsupported file format. Only .json and .jsonl are supported.")
        except Exception as e:
            print(f"Error loading dataset from Hugging Face Hub: {e}")
            return None

    @property
    def meta(self):
        return self._meta
    
    @property
    def img_files(self):
        return self._img_files
    
    @property
    def ids(self) -> list[str]:
        return self._ids
    
    def has_id(self, id: str) -> bool:
        return id in self._ids
    
    @property
    def tags(self) -> list[dict]:
        return self._tags
    
    @property
    def prompts(self) -> list[str]:
        return self._prompts
    
    @property
    def captions(self) -> list[str]:
        return self._captions
    @property
    def captions_joy(self) -> list[str]:
        return self._captions_joy
    
    @property
    def data(self):
        if not self._data:
            self._data = load_dataset(self.repo_id)
        return self._data
    
    def id2idx(self, id: str) -> int | None:
        for idx, img_file in enumerate(self.img_files):
            if Path(img_file).stem == id:
                return idx
        return None
    
    def pil(self, idx: int) -> Image.Image | None:
        if not isinstance(idx, int):
            raise ValueError("Index not an integer!")
        # check idx vs. size
        if idx < 0:
            raise IndexError("Index out of bounds for tags list.")
        if idx >= len(self):
            raise IndexError("Index out of bounds for tags list.")

        file_img = hf_hub_download(repo_id=self.repo_id, filename=self.img_files[idx], repo_type="dataset")
        img = Image.open(file_img)

        return img


    def img_extend_tags(self, idx: int, tags_extend: dict):
        if not isinstance(idx, int):
            raise ValueError("Index not an integer!")
        # check idx vs. size
        if idx < 0:
            raise IndexError("Index out of bounds for tags list.")
        if idx >= len(self):
            raise IndexError("Index out of bounds for tags list.")

        if not isinstance(tags_extend, dict):
            raise ValueError("Extended tags not a Dict!")
        
        self._tags[idx] |= tags_extend

    def img_set_caption(self, idx: int, caption: str):
        if not isinstance(idx, int):
            raise ValueError("Index not an integer!")
        # check idx vs. size
        if idx < 0:
            raise IndexError("Index out of bounds for tags list.")
        if idx >= len(self):
            raise IndexError("Index out of bounds for tags list.")

        if not isinstance(caption, str):
            raise ValueError("Caption not a String!")
        
        self._meta[idx] |= {"caption": caption}
    
    def img_set_caption_joy(self, idx: int, caption: str):
        if not isinstance(idx, int):
            raise ValueError("Index not an integer!")
        # check idx vs. size
        if idx < 0:
            raise IndexError("Index out of bounds for tags list.")
        if idx >= len(self):
            raise IndexError("Index out of bounds for tags list.")

        if not isinstance(caption, str):
            raise ValueError("Caption not a String!")
        
        self._meta[idx] |= {"caption_joy": caption}
    
    def img_download(self, idx: int) -> Path:
        if not isinstance(idx, int):
            raise ValueError("Index not an integer!")
        # check idx vs. size
        if idx < 0:
            raise IndexError("Index out of bounds for tags list.")
        if idx >= len(self):
            raise IndexError("Index out of bounds for tags list.")

        file_img = hf_hub_download(repo_id=self.repo_id, filename=self.img_files[idx], repo_type="dataset")
        return Path(file_img)

    def __len__(self):
        return len(self._meta)

    def __getitem__(self, idx):
        return self._meta[idx]

    def save_to_jsonl(self, force: bool = False):
        if self._meta is None:
            print("No meta to save.")
            return
        # if exists and not force, do nothing
        if Path(self.file_meta).exists() and not force:
            print(f"File '{self.file_meta}' already exists. Use force=True to overwrite.")
            return
            
        try:
            with jsonlines.open(self.file_meta, mode='w') as writer:
                writer.write_all(self._meta)
            print(f"Data successfully saved to {self.file_meta}")
        except Exception as e:
            print(f"Error saving data to JSONL: {e}")

    def prompt(self, idx: int) -> str | None: 
        if not isinstance(idx, int):
            raise ValueError("Index not an integer!")
        # check idx vs. size
        if idx < 0:
            raise IndexError("Index out of bounds for tags list.")
        if idx >= len(self):
            raise IndexError("Index out of bounds for tags list.")

        # read the bodyparts tags
        tags_custom = self._tags[idx].get("custom", {})
        bodypart_tags = tags_custom.get("bodypart", [])
        
        # build the prompt
        bp_prompt = []
        for bp_tag in bodypart_tags:
            mapped_tag = map_bodypart.get(bp_tag)
            if not mapped_tag:
                continue
            bp_prompt.append(mapped_tag)
        
        # comma separated string
        bp_str = ",".join(bp_prompt)
        if bp_str:
            bp_str = f" in terms of {bp_str}"
        #prompt = f"Write a very long detailed description for this image, especially about the interaction of the female giantess woman and the small man{bp_str}."
        prompt = f"Write a very long detailed description for this image, especially about the woman with big breasts and how they present their bodies."
        
        # !!! PROPOSAL more universal !!!
        #prompt = f"Write a very long detailed description for this image, especially wrt. the topics giantess and small man, femdom, giving handjob."

        # TODO
        print(prompt)
        return prompt

    def make_folder_train(self, to_folder:str = "", trigger: str = "", ids: list[str] = [], force = False) -> None:
        """
        TODO: maybe not the right place here! there is an explicit trainer class!
        """
        # create folder
        path_folder = Path(to_folder)
        if path_folder.exists() and not force:
            print(f"Folder '{to_folder}' already exists. Use force=True to overwrite.")
            return
        elif path_folder.exists() and force:
            print(f"Folder '{to_folder}' exists. Removed due to force option!")
            shutil.rmtree(path_folder)
            
        path_folder.mkdir(parents=True, exist_ok=True)

        idxs = range(len(self))
        if ids:
            idxs = []
            for id in ids:
                idx = self.id2idx(id)
                if idx:
                    idxs.append(idx)

        for idx in idxs:
            # caption
            caption = ""
            if trigger:
                caption = f"{trigger}, "
            caption += self.captions[idx]
            if caption:
                caption_path = Path(to_folder) / Path(self.img_files[idx]).with_suffix(".txt").name
                # write caption string to file
                with caption_path.open("w", encoding="utf-8") as f:
                    f.write(caption)

            # image
            img_path = Path(to_folder) / Path(self.img_files[idx]).name
            img_path_download = hf_hub_download(repo_id=self.repo_id, filename=self.img_files[idx], repo_type="dataset")
            # move downloaded img file to target folder
            shutil.move(img_path_download, img_path)
