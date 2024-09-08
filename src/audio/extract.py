import subprocess
import os
from pathlib import Path

from src.audio.common import _ofile_attach_metadata, _file_link_metadata, EXT_VIDEOS

def _extract_audio_fiorfo(fiorfo: str, output_ext: str =".mp3", force=False):

    ipath = Path(fiorfo)

    for ext_video in EXT_VIDEOS:
        ifiles = [ipath]
        if not ipath.is_file():
            ifiles = ipath.glob(f"*{ext_video}")
        
        for ifile in ifiles:
            _file_link_metadata(ifile)
            ofile = ifile.with_suffix(output_ext)
            ofile = _ofile_attach_metadata(ofile)

            if ofile.exists():
                if not force:
                    continue

            print(f"{ifile} -> {ofile}")
            subprocess.call(
                ["ffmpeg", "-vn", "-y", "-i", str(ifile), str(ofile)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                )