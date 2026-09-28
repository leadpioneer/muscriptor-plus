"""Shared MuseScore fixtures: skip-based availability for integration tests."""

import pytest

from muscriptor.utils.sheets import MuseScoreNotFoundError, find_musescore


def musescore_binary() -> str:
    """The MuseScore 4 binary path; the test module skips when absent."""
    return find_musescore()


def musescore_available() -> bool:
    try:
        find_musescore()
    except MuseScoreNotFoundError:
        return False
    return True


@pytest.fixture(scope="session")
def _musescore():
    return find_musescore()
