from src.audio.extract import _extract_audio_folder
from src.audio.transcribe import _transcribe_folder

def transcribe(folder: str, extract_audio=True, subtitles=True):
    if extract_audio:
        _extract_audio_folder(folder)
    _transcribe_folder(folder, subtitles=subtitles)