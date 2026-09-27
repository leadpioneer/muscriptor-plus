"""Separation model identifiers and settings for the preprocessing layer.

Keeping the model id and its knobs here (rather than as string literals in the
server or the UI) is what lets a future provider — BS-RoFormer, Demucs, … — be
added without touching anything outside this package.
"""

import dataclasses
import sys
from dataclasses import dataclass
from pathlib import Path


# Kimberley Jensen's Mel-Band-RoFormer vocal model, as listed in
# audio-separator's model registry (UVR's "MelBand Roformer Vocals").
# Single-stem vocal model: audio-separator derives the instrumental by
# inverting the vocals against the mix.
VOCAL_MODEL_ID = "vocals_mel_band_roformer.ckpt"


@dataclass(frozen=True)
class SeparationSettings:
    """Knobs handed to the separation provider.

    Only the settings that matter for reproducibility are exposed; everything
    else uses the audio-separator defaults. `device` is informational — it is
    recorded into `PreprocessResult.settings` — because audio-separator picks
    CUDA on its own when torch reports it available.
    """

    model_id: str = VOCAL_MODEL_ID
    output_format: str = "WAV"
    # Peaks above this fraction of full scale are attenuated before inference;
    # the audio-separator default, spelled out so results are reproducible.
    normalization_threshold: float = 0.9
    device: str = "auto"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def default_model_cache_dir() -> Path:
    """Where separation model weights are cached across runs.

    audio-separator downloads a model into `model_file_dir` and reuses the
    file on every later run, so this must be a stable per-user location rather
    than a per-request temp dir.
    """
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path.home() / ".cache"
    return base / "muscriptor" / "audio-separator"
