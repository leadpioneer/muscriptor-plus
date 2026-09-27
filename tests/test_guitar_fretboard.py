"""Unit tests for fretboard geometry: presets and position generation."""

import pytest

from muscriptor.guitar_arrangement import (
    FretPosition,
    GuitarTuning,
    STANDARD_TUNING,
    UnplayableNoteError,
    possible_positions,
)


def test_standard_tuning_has_the_documented_open_pitches():
    assert STANDARD_TUNING.name == "standard"
    assert STANDARD_TUNING.string_count == 6
    # String 1 first (highest sounding): E4 B3 G3 D3 A2 E2.
    assert STANDARD_TUNING.open_pitches == (64, 59, 55, 50, 45, 40)


def test_possible_positions_for_e4():
    positions = possible_positions(64, STANDARD_TUNING, 24)
    assert FretPosition(string=1, fret=0) in positions
    assert FretPosition(string=2, fret=5) in positions
    assert FretPosition(string=3, fret=9) in positions
    assert FretPosition(string=4, fret=14) in positions
    assert FretPosition(string=5, fret=19) in positions
    assert FretPosition(string=6, fret=24) in positions
    # Deterministic order: ascending fret, then string.
    assert positions == tuple(
        sorted(positions, key=lambda p: (p.fret, p.string))
    )


def test_pitch_below_every_string_is_an_error():
    with pytest.raises(UnplayableNoteError) as excinfo:
        possible_positions(30, STANDARD_TUNING, 24)
    assert excinfo.value.details["pitch"] == 30
    assert "30" in str(excinfo.value)
    assert "octave" in str(excinfo.value).lower()


def test_pitch_above_the_reachable_range_is_an_error():
    # Lowest string 40 + max_fret 24 → the top reachable pitch is 64.
    with pytest.raises(UnplayableNoteError) as excinfo:
        possible_positions(90, STANDARD_TUNING, 24)
    assert excinfo.value.details["pitch"] == 90
    assert excinfo.value.details["high_pitch"] == 64


def test_max_fret_limits_the_candidates():
    positions = possible_positions(64, STANDARD_TUNING, 4)
    assert positions == (FretPosition(string=1, fret=0),)


def test_generator_supports_any_number_of_strings():
    ukulele = GuitarTuning(name="ukulele", open_pitches=(69, 64, 60, 55))
    assert possible_positions(64, ukulele, 12) == (
        FretPosition(string=2, fret=0),
        FretPosition(string=3, fret=4),
        FretPosition(string=4, fret=9),
    )
    seven_string = STANDARD_TUNING.open_pitches + (35,)
    wide = GuitarTuning(name="seven", open_pitches=seven_string)
    # Pitch 40 is the 6th string open and the 7th string's 5th fret.
    assert possible_positions(40, wide, 24) == (
        FretPosition(string=6, fret=0),
        FretPosition(string=7, fret=5),
    )
