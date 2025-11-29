# Lazy imports to avoid loading heavy dependencies at startup
__all__ = [
    "AudioExtractor",
    "ASRProcessor", 
    "SubtitleManager",
    "Transcoder",
    "TTSEngine",
    "VideoBurner"
]

def __getattr__(name):
    if name == "AudioExtractor":
        from .audio_extractor import AudioExtractor
        return AudioExtractor
    elif name == "ASRProcessor":
        from .asr_processor import ASRProcessor
        return ASRProcessor
    elif name == "SubtitleManager":
        from .subtitle_manager import SubtitleManager
        return SubtitleManager
    elif name == "Transcoder":
        from .transcoder import Transcoder
        return Transcoder
    elif name == "TTSEngine":
        from .tts_engine import TTSEngine
        return TTSEngine
    elif name == "VideoBurner":
        from .video_burner import VideoBurner
        return VideoBurner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
