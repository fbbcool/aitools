import whisper
import json
from whisper.utils import get_writer
from pathlib import Path
from typing import Final

EXT_AUDIO: Final = ".mp3"
EXT_JSON_TRANSCRIBE: Final = ".json_transcribe"

def _file_wo_audio_ext(file: Path) -> Path:
    return Path(str(file).replace(EXT_AUDIO,""))

def _file_w_ext(file: Path, ext: str) -> Path:
    return Path(f"{str(_file_wo_audio_ext(file))}{ext}")

def _subtitles(ifile: Path, result: dict, format="srt"):
    opath = ifile.parent
    ofile = _file_wo_audio_ext(ifile).name

    writer = get_writer("srt", str(opath)) # get srt,tsv,vtt writer for the current directory
    writer(result, ofile, {}) # add empty dictionary for 'options

def _transcribe_file(ifile: Path, subtitles=True):
    ofile_json = _file_w_ext(ifile, EXT_JSON_TRANSCRIBE)
    model = whisper.load_model("base")
    result = model.transcribe(str(ifile))

    with ofile_json.open("+wt") as f:
        json.dump(result, f, indent=2)

    if subtitles:
        _subtitles(ifile, result)

    return result

def _transcribe_folder(folder: str, subtitles=True):
    ipath = Path(folder)

    for ifile in ipath.glob(f"*{EXT_AUDIO}"):
        _transcribe_file(ifile, subtitles=subtitles)
