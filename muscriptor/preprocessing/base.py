"""Contracts shared by preprocessing steps."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class PreprocessResult:
    """Outcome of one preprocessing pass over an uploaded audio file.

    `audio_for_transcription` is the file the transcription model should run
    on: the instrumental stem for vocal removal, or the original input when a
    step passes audio through unchanged. Stem paths point at files in
    `output_dir` that stay readable for as long as the caller keeps them.
    """

    input_path: Path
    audio_for_transcription: Path
    vocals_path: Path | None
    instrumental_path: Path | None
    processor_id: str
    model_id: str | None
    model_version: str | None
    settings: dict[str, Any]
    duration_seconds: float


class AudioPreprocessor(Protocol):
    """A single optional step that prepares uploaded audio for transcription.

    Implementations must not modify `input_path` and must write every artifact
    into `output_dir` (creating it if needed). Failures raise `PreprocessError`
    subclasses — never a silent fallback to the original audio.
    """

    processor_id: str

    def process(
        self,
        input_path: Path,
        output_dir: Path,
        device: str,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> PreprocessResult:
        """Run the step; return what the transcription pipeline should consume."""
        ...
