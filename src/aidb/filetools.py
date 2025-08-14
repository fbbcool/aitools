from pathlib import Path
import re

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
    # check if "high" exists as a folder
    if (path_source / "high").exists():
        folders_source.append(path_source / "high")
    # check if "low" exists as a folder
    if (path_source / "low").exists():
        folders_source.append(path_source / "low")
    
    
    loras: list[Path] = []
    for folder in folders_source:
        for lora in folder.glob(f"{DIFFPIPE_NAME_LORA}*.safetensors"):
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