import subprocess
import os
from pathlib import Path

def convert_video_to_audio_ffmpeg(path: str, output_ext: str ="mp3"):
    """Converts video to audio directly using `ffmpeg` command
    with the help of subprocess module"""

    ipath = Path(path)

    for ifile in ipath.glob("*.mp4"):
        ofile = ifile.with_suffix(output_ext)
        subprocess.call(["ffmpeg -nv", "-y", "-i", str(ifile), str(ofile)], 
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT)