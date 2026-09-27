"""Preprocessing: optional audio preparation steps that run before transcription.

The first (and for now only) step is lead-vocal removal: an opt-in pass that
splits the uploaded track into `vocals` and `instrumental` stems with
`audio-separator` and feeds the instrumental stem to the transcription model
instead of the original mix.

The layer is deliberately isolated from `TranscriptionModel`: the server hands
the upload to an `AudioPreprocessor`, gets back a `PreprocessResult` pointing
at the audio to transcribe, and the rest of the pipeline is unchanged. When no
preprocessing is requested the original audio flows through exactly as before.
"""

from muscriptor.preprocessing.artifacts import StemStore
from muscriptor.preprocessing.base import AudioPreprocessor, PreprocessResult
from muscriptor.preprocessing.errors import (
    FFmpegNotFoundError,
    ModelLoadError,
    PreprocessError,
    SeparationError,
    StemNotFoundError,
)
from muscriptor.preprocessing.models import (
    VOCAL_MODEL_ID,
    SeparationSettings,
    default_model_cache_dir,
)
from muscriptor.preprocessing.vocal_removal import VocalRemovalPreprocessor

__all__ = [
    "AudioPreprocessor",
    "FFmpegNotFoundError",
    "ModelLoadError",
    "PreprocessError",
    "PreprocessResult",
    "SeparationError",
    "SeparationSettings",
    "StemNotFoundError",
    "StemStore",
    "VOCAL_MODEL_ID",
    "VocalRemovalPreprocessor",
    "default_model_cache_dir",
]
