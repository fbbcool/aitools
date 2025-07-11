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
    def __init__(self, repo_id: str, file_meta: str = "metadata.jsonl"):
        self.repo_id = repo_id
        self.file_meta = file_meta
        self._data = None
        self._meta = self._load_meta()
        self._img_files = ["train/" + line["file_name"] for line in self._meta]
        self._tags:list[dict] = [json.loads(line["tags"]) for line in self._meta]

    def _load_meta(self):
        try:
            file_path = hf_hub_download(repo_id=self.repo_id, filename="train/"+self.file_meta, repo_type="dataset")
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
    def tags(self) -> list[dict]:
        return self._tags
    
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
    
    def pil(self, idx: int) -> Image.Image:
        if not isinstance(idx, int):
            raise ValueError("Index not an integer!")
        # check idx vs. size
        if idx < 0:
            raise IndexError("Index out of bounds for tags list.")
        if idx >= len(self):
            raise IndexError("Index out of bounds for tags list.")

        file_img = hf_hub_download(repo_id=self.repo_id, filename=self.img_files[idx], repo_type="dataset")
        return Image.open(file_img)

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

    def __len__(self):
        return len(self._meta)

    def __getitem__(self, idx):
        return self._meta[idx]

    def save_to_jsonl(self):
        if self._meta is None:
            print("No meta to save.")
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
            bp_prompt.append(bp_tag)
        
        # comma separated string
        bp_str = ",".join(bp_prompt)
        prompt = f"Write a very long detailed description for this image, especially about the interaction of the female giantess woman and the small man in terms of {bp_str}."

        # TODO
        print(prompt)
        return prompt

    def make_folder_train(self, to_folder:str = "", force = False) -> None:
        # create folder
        path_folder = Path(to_folder)
        if path_folder.exists() and not force:
            print(f"Folder '{to_folder}' already exists. Use force=True to overwrite.")
            return
        elif path_folder.exists() and force:
            print(f"Folder '{to_folder}' exists. Removed due to force option!")
            shutil.rmtree(path_folder)
            
        path_folder.mkdir(parents=True, exist_ok=True)

        for idx in range(len(self)):
            # caption
            caption = self.prompt(idx)
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
