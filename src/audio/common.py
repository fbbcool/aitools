
from pathlib import Path
from typing import Final

EXT_AUDIO: Final = ".mp3"
EXT_JSON_TRANSCRIBE: Final = ".json_transcribe"
DIR_METADATA: Final = "___metadata"

def _ofile_attach_metadata(file: Path) -> Path:
    opath = Path(file.parent, DIR_METADATA)
    opath.mkdir(parents=False, exist_ok=True)
    return Path(opath, file.name)

def _ofile_wo_audio_ext(file: Path) -> Path:
    ofile = Path(str(file).replace(EXT_AUDIO,""))
    #ofile = Path(ofile.parent, DIR_METADATA, ofile.name)
    return ofile

def _ofile_w_ext(file: Path, ext: str) -> Path:
    return Path(f"{str(_ofile_wo_audio_ext(file))}{ext}")
