import subprocess
import os
from pathlib import Path

from src.audio.common import _ofile_attach_metadata

def _extract_audio_folder(folder: str, output_ext: str =".mp3"):
    """Converts video to audio directly using `ffmpeg` command
    with the help of subprocess module"""

    ipath = Path(folder)

    for ifile in ipath.glob("*.mp4"):
        ofile = ifile.with_suffix(output_ext)
        ofile = _ofile_attach_metadata(ofile)
        print(f"{ifile} -> {ofile}")
        subprocess.call(
            ["ffmpeg", "-vn", "-y", "-i", str(ifile), str(ofile)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            )