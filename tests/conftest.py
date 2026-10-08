"""Shared fixtures for muscriptor tests.

Integration tests need artifacts that are deliberately not in the repository
(model weights, an audio sample). Both are opt-in, via environment variables:

    MUSCRIPTOR_TEST_WEIGHTS  path to a .safetensors checkpoint
    MUSCRIPTOR_TEST_SONG     path to an audio file for end-to-end inference

For convenience the weights are also picked up from any legacy
``muscriptor_weights_*.safetensors`` dropped into the repository root. Tests
that need a missing artifact skip with a message instead of failing.
"""

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def _weights_path() -> Path | None:
    env = os.environ.get("MUSCRIPTOR_TEST_WEIGHTS")
    if env:
        return Path(env).expanduser()
    legacy = sorted(REPO_ROOT.glob("muscriptor_weights_*.safetensors"))
    return legacy[0] if legacy else None


def _song_path() -> Path | None:
    env = os.environ.get("MUSCRIPTOR_TEST_SONG")
    return Path(env).expanduser() if env else None


WEIGHTS_PATH = _weights_path()
SONG_PATH = _song_path()


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: tests that require model weights")


@pytest.fixture(scope="session")
def transcription_model():
    """Load the TranscriptionModel once for the whole test session."""
    if WEIGHTS_PATH is None or not WEIGHTS_PATH.exists():
        pytest.skip(
            "No test weights: set MUSCRIPTOR_TEST_WEIGHTS or drop a "
            "muscriptor_weights_*.safetensors into the repository root"
        )
    from muscriptor.transcription_model import TranscriptionModel

    return TranscriptionModel.load_model(weights_path=WEIGHTS_PATH, device="cpu")
