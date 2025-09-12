from audio.extract import _extract_audio_fiorfo
from audio.transcribe import _transcribe_fiorfo

def transcribe(fiorfo: str, extract_audio=True, subtitles=True, force=False):
    if extract_audio:
        _extract_audio_fiorfo(fiorfo, force=force)
    _transcribe_fiorfo(fiorfo, subtitles=subtitles, force=force)