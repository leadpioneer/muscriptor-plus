"""Lead-vocal removal via `audio-separator` (Mel-Band-RoFormer vocal model).

Splits an uploaded track into `Vocals` and `Instrumental` stems; the
instrumental is what the transcription model should run on when the user asks
for vocal removal. The `audio_separator` import is deliberately inside
`process()`: this module must import cleanly on machines where the dependency
is not installed (e.g. Intel macs, where the pinned torch is too old for it).
"""

import dataclasses
import gc
import logging
import shutil
from pathlib import Path
from typing import Callable

from muscriptor.preprocessing.base import PreprocessResult
from muscriptor.preprocessing.errors import (
    FFmpegNotFoundError,
    ModelLoadError,
    SeparationError,
    StemNotFoundError,
)
from muscriptor.preprocessing.models import (
    SeparationSettings,
    default_model_cache_dir,
)

logger = logging.getLogger(__name__)

PROCESSOR_ID = "vocal-removal"

# Mapping of audio-separator stem names to the deterministic filenames this
# module asks for via `custom_output_names` (the extension follows the
# configured output format). Some audio-separator/model versions call the
# secondary stem "Instrumental", others "other" — both ARE the instrumental
# (the mix with the vocals removed), so both are mapped to one file name.
_STEM_FILENAMES = {
    "Vocals": "vocals",
    "Instrumental": "instrumental",
    "other": "instrumental",
    "Other": "instrumental",
}


class VocalRemovalPreprocessor:
    """Removes the lead vocal from a track, keeping both stems as artifacts."""

    processor_id = PROCESSOR_ID

    def __init__(self, settings: SeparationSettings | None = None) -> None:
        self.settings = settings or SeparationSettings()

    def process(
        self,
        input_path: Path,
        output_dir: Path,
        device: str,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> PreprocessResult:
        """Split `input_path` into vocals/instrumental; return the instrumental."""
        input_path = Path(input_path)
        output_dir = Path(output_dir)

        if not input_path.is_file():
            raise SeparationError(f"input audio file not found: {input_path}")
        # audio-separator shells out to ffmpeg for several input formats; fail
        # up front with an actionable message instead of a library traceback.
        if shutil.which("ffmpeg") is None:
            raise FFmpegNotFoundError(
                "vocal removal needs ffmpeg, but it was not found on PATH. "
                "Install ffmpeg (e.g. 'winget install Gyan.FFmpeg') and "
                "restart the server."
            )
        settings = dataclasses.replace(self.settings, device=device)
        output_dir.mkdir(parents=True, exist_ok=True)
        report = progress_callback or (lambda *_: None)

        # Imported lazily: see the module docstring.
        try:
            from audio_separator.separator import Separator
        except Exception as e:
            raise ModelLoadError(
                f"could not import the audio-separator package ({e}). Vocal "
                "removal needs it, with torch>=2.3 and numpy>=2."
            ) from e

        report(0.0, "loading separation model")
        separator = None
        try:
            separator = Separator(
                model_file_dir=str(default_model_cache_dir()),
                output_dir=str(output_dir),
                output_format=settings.output_format,
                normalization_threshold=settings.normalization_threshold,
            )
            try:
                separator.load_model(settings.model_id)
            except Exception as e:
                raise ModelLoadError(
                    f"could not load separation model '{settings.model_id}': {e}"
                ) from e

            report(0.3, "separating vocals from instrumental")
            try:
                produced = separator.separate(
                    str(input_path),
                    custom_output_names=_STEM_FILENAMES,
                )
            except Exception as e:
                if "out of memory" in str(e).lower():
                    raise SeparationError(
                        "vocal removal ran out of GPU memory. Close other GPU "
                        "applications or leave vocal removal off."
                    ) from e
                raise SeparationError(f"vocal separation failed: {e}") from e

            # Some audio-separator versions return bare file names (relative to
            # output_dir) instead of full paths — normalize them so the stems
            # can be read back and served no matter what the caller's CWD is.
            produced = [
                str(p if (p := Path(path)).is_absolute() else output_dir / path)
                for path in produced
            ]

            report(0.9, "locating stems")
            instrumental_path = _find_stem(produced, "instrumental")
            if instrumental_path is None:
                raise StemNotFoundError(
                    "vocal separation finished but produced no instrumental "
                    f"stem; files written: "
                    f"{[Path(p).name for p in produced] or 'none'}"
                )
            vocals_path = _find_stem(produced, "vocals")
        except SeparationError:
            raise
        except Exception as e:  # noqa: BLE001 — any other failure inside the
            # separation stack is reported as a readable SeparationError so
            # the job stops with a message, never with a silent fallback.
            raise SeparationError(f"vocal separation failed: {e}") from e
        finally:
            # The separator holds the (large) RoFormer weights in GPU memory.
            # Everything here runs under the transcription lock, so dropping
            # them NOW — before the MuScriptor model is used — is what keeps
            # both models from ever sharing VRAM. Dropping the last reference
            # alone doesn't return cached CUDA blocks to the driver; the
            # explicit gc.collect() + empty_cache() do (the same pattern the
            # server's model switcher uses).
            del separator
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:  # noqa: BLE001 — cleanup must never raise
                pass

        report(1.0, "done")
        logger.info(
            "vocal removal done: instrumental=%s (dir %s)",
            instrumental_path.name,
            output_dir,
        )
        return PreprocessResult(
            input_path=input_path,
            audio_for_transcription=instrumental_path,
            vocals_path=vocals_path,
            instrumental_path=instrumental_path,
            processor_id=self.processor_id,
            model_id=settings.model_id,
            model_version=None,
            settings=settings.to_dict(),
            duration_seconds=_duration_seconds(instrumental_path),
        )


def _find_stem(produced: list[str], stem: str) -> Path | None:
    """Locate `stem`'s output file among the paths `separate()` returned.

    Prefers the deterministic names requested via `custom_output_names`
    ("vocals.wav"/"instrumental.wav"); if the library version ignored them,
    falls back to matching the stem name inside whatever filename it produced
    ("Instrumental" or "other" for the instrumental).
    """
    for path in produced:
        if Path(path).stem == stem:
            return Path(path)
    for path in produced:
        name = Path(path).name.lower()
        if stem == "instrumental":
            hit = "instrumental" in name or (
                "other" in name and "vocals.wav" not in name
            )
        else:
            hit = (
                "vocals" in name and "instrumental" not in name and "other" not in name
            )
        if hit:
            return Path(path)
    return None


def _duration_seconds(path: Path) -> float:
    try:
        import soundfile as sf

        return float(sf.info(str(path)).duration)
    except Exception:  # noqa: BLE001 — metadata only, never fail the run for it
        return 0.0
