"""Errors raised by preprocessing steps.

Every subclass of `PreprocessError` renders a user-facing explanation via
plain `str(e)`: the server puts that string into its error payload and the UI
shows it as-is, so the messages are written for the person reading them.
"""


class PreprocessError(Exception):
    """Base class for preprocessing failures.

    A failed preprocessing step never falls back to the original audio: the
    caller stops the job and reports this error instead of transcribing the
    mix the user asked to have cleaned up.
    """


class FFmpegNotFoundError(PreprocessError):
    """The `ffmpeg` binary required by the separation stack is not on PATH."""


class ModelLoadError(PreprocessError):
    """The separation model could not be loaded or downloaded."""


class SeparationError(PreprocessError):
    """The separation library failed while splitting the audio."""


class StemNotFoundError(PreprocessError):
    """The separation finished but did not produce an expected stem file."""
