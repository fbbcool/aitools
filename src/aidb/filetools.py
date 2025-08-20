from pathlib import Path
import shutil
import re
import uuid


from aidb.dbdefines import *

def diffpipe_lora_rename(url_models_relative: Path | str, test: bool = False) -> None:
    models = PATH_LOCAL_MODELS
    path_source = models / url_models_relative
    
    if not path_source.exists():
        return
    if not path_source.is_dir():
        return
    
    name = path_source.name

    folders_source: list[Path] = [path_source]
    # check if valid subfolders exist
    valid_folders = ["high", "low", "high_0875", "low_0875"]
    for valid_folder in valid_folders:
        if (path_source / valid_folder).exists():
            folders_source.append(path_source / valid_folder)
    
    loras: list[Path] = []
    for folder in folders_source:
        for lora in folder.glob(f"{DIFFPIPE_NAME_LORA}*{SUFFIX_SAFETENSORS}"):
            loras.append(folder / lora)
    
    if not loras:
        print("no loras found")
        return
    
    for lora in loras:
        print(lora)

        # the lora stem has a number enclosed by braces. extract them
        num=-1
        match = re.search(r'\d+', lora.stem)
        if match:
            num = int(match.group())
        if num < 0:
            continue

        # do a 2-digit name from int
        num_str = f"{num:02d}"
        target_name = f"{name}-{num_str}"
        target_path = (lora.parent / target_name).with_suffix(".safetensors")
        print(target_path)
        if not test:
            lora.rename(target_path)

def collect_tagged_files(src_folder: str | Path, to_folder: str | Path | None = None, tag: str = "ai_select", recursive: bool = False) -> list[Path]:
    import macos_tags
    src_folder = Path(src_folder)
    if not src_folder.exists():
        return []
    if not src_folder.is_dir():
        return []
    
    # iterate all files
    files = []
    if recursive:
        files = list(src_folder.rglob("*"))
    else:
        files = list(src_folder.iterdir())

    tagged_files: list[Path] = []
    for file in files:
        if file.is_file():
            # Check if the file has the specified tag
            tags_macos = macos_tags.get_all(str(file))
            for tag_macos in tags_macos:
                if tag_macos.name == tag:
                    tagged_files.append(file)
                    break
    
    if to_folder is not None:
        to_folder = Path(to_folder)
        if not to_folder.exists():
            to_folder.mkdir(parents=True)
        for from_file in tagged_files:
            to_file = (to_folder / str(uuid.uuid4())).with_suffix(from_file.suffix)
            print(f"copying {from_file} to {to_file}")
            shutil.copy(from_file, to_file)

    return tagged_files
