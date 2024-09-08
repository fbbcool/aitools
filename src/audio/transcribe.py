import whisper
#import soundfile as sf
import torch
import json
from whisper.utils import get_writer
from pathlib import Path
from typing import Final

from src.audio.common import _ofile_wo_audio_ext, _ofile_w_ext, _ofile_attach_metadata, EXT_JSON_TRANSCRIBE, EXT_AUDIO, DIR_METADATA

def _subtitles(ifile: Path, result: dict, format="srt"):
    opath = ifile.parent
    ofile = _ofile_wo_audio_ext(ifile).name

    writer = get_writer("srt", str(opath)) # get srt,tsv,vtt writer for the current directory
    writer(result, ofile, {}) # add empty dictionary for 'options

def _transcribe_file(ifile: Path, model="medium.en", subtitles=True, force=False):
    ofile_json = _ofile_w_ext(ifile, EXT_JSON_TRANSCRIBE)

    if ofile_json.exists():
        if not force:
            return

    #torch.cuda.init()
    #print(f"num mps devices: {torch.mps.device_count()}")
    #device = torch.device("mps")
    device = "cpu"
    #model = "tiny"
    model = "base"
    #model = "medium"
    #model = "large"

    fp16 = True
    if device == "cpu":
        model_whisper = whisper.load_model(model)
        fp16 = False
    else:
        model_whisper = whisper.load_model(model).to(device)

    result = model_whisper.transcribe(str(ifile), language="en", fp16=fp16)

    with ofile_json.open("+wt") as f:
        json.dump(result, f, indent=2)

    if subtitles:
        _subtitles(ifile, result)

    return result

def _get_model_whisper():
    import whisper

    # specify the path to the input audio file
    input_file = "H:\\path\\3minfile.WAV"

    # specify the path to the output transcript file
    output_file = "H:\\path\\transcript.txt"

    # Cuda allows for the GPU to be used which is more optimized than the cpu
    torch.cuda.init()
    device = "mps" # if torch.cuda.is_available() else "cpu"

    # Load audio file
    audio_data, sample_rate = sf.read(input_file, always_2d=True)

    #load whisper model
    model_size = "tiny"
    print("loading model :", model_size)
    model = whisper.load_model(model_size).to(device)
    print(model_size, "model loaded")

    # Initialize variables
    results = []
    language = "en"

    # Transcribe audio
    with torch.cuda.device(device):
        result = model.transcribe(audio_data, language=language, fp16=True, word_timestamps=True)

def _transcribe_fiorfo(fiorfo: str, subtitles=True, force=False):

    ifiorfo = Path(fiorfo)

    ifiles = []
    if ifiorfo.is_file():
        ifile = _ofile_attach_metadata(ifiorfo).with_suffix(EXT_AUDIO)
        ifiles = [ifile]
    else:
        ipath = Path(ifiorfo, DIR_METADATA)
        ifiles = ipath.glob(f"*{EXT_AUDIO}")

    for ifile in ifiles:
        _transcribe_file(ifile, subtitles=subtitles, force=force)
