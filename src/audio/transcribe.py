import whisper
import json
from whisper.utils import get_writer
from pathlib import Path
from typing import Final

from src.audio.common import _ofile_wo_audio_ext, _ofile_w_ext, EXT_JSON_TRANSCRIBE, EXT_AUDIO, DIR_METADATA

def _subtitles(ifile: Path, result: dict, format="srt"):
    opath = ifile.parent
    ofile = _ofile_wo_audio_ext(ifile).name

    writer = get_writer("srt", str(opath)) # get srt,tsv,vtt writer for the current directory
    writer(result, ofile, {}) # add empty dictionary for 'options

def _transcribe_file(ifile: Path, subtitles=True):
    ofile_json = _ofile_w_ext(ifile, EXT_JSON_TRANSCRIBE)
    model = whisper.load_model("base")
    result = model.transcribe(str(ifile))

    with ofile_json.open("+wt") as f:
        json.dump(result, f, indent=2)

    if subtitles:
        _subtitles(ifile, result)

    return result

def _transcribe_folder(folder: str, subtitles=True):
    ipath = Path(folder, DIR_METADATA)

    for ifile in ipath.glob(f"*{EXT_AUDIO}"):
        _transcribe_file(ifile, subtitles=subtitles)
