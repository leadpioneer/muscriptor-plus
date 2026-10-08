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
    assert positions == tuple(sorted(positions, key=lambda p: (p.fret, p.string)))


def test_pitch_below_every_string_is_an_error():
    with pytest.raises(UnplayableNoteError) as excinfo:
        possible_positions(30, STANDARD_TUNING, 24)
    assert excinfo.value.details["pitch"] == 30
    assert "30" in str(excinfo.value)
    assert "octave" in str(excinfo.value).lower()


def test_pitch_above_the_reachable_range_is_an_error():
    # Highest open string 64 + max_fret 24 → the top reachable pitch is 88.
    with pytest.raises(UnplayableNoteError) as excinfo:
        possible_positions(90, STANDARD_TUNING, 24)
    assert excinfo.value.details["pitch"] == 90
    assert excinfo.value.details["high_pitch"] == 88


def test_playable_ceiling_reaches_beyond_the_highest_open_string():
    # F#5 (78) sits 14 frets above the open 1st string: playable, even though
    # it lies above every open pitch (the old error message claimed 64).
    positions = possible_positions(78, STANDARD_TUNING, 24)
    assert FretPosition(string=1, fret=14) in positions


def test_error_message_reports_the_true_playable_range():
    with pytest.raises(UnplayableNoteError) as excinfo:
        possible_positions(37, STANDARD_TUNING, 24)
    text = str(excinfo.value)
    assert "40–88" in text
    assert excinfo.value.details["low_pitch"] == 40
    assert excinfo.value.details["high_pitch"] == 88


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


# --- Ergonomic fingerings (v2) ----------------------------------------------

from muscriptor.guitar_arrangement import (  # noqa: E402
    SolverConfig,
    possible_fingerings,
)


def test_closed_note_gets_four_finger_states():
    from muscriptor.guitar_arrangement import FretPosition as FP

    config = SolverConfig()
    states = possible_fingerings(FP(string=1, fret=7), config)
    # Finger 1 in position 7, finger 2 in position 6, … finger 4 in position 4.
    assert [(s.hand_position, s.finger) for s in states] == [
        (7, 1),
        (6, 2),
        (5, 3),
        (4, 4),
    ]
    for state in states:
        assert state.position.fret == state.hand_position + state.finger - 1


def test_low_fret_constrains_the_fingers():
    config = SolverConfig()
    # Fret 1: only finger 1 (hand position 1) keeps hand_position >= 1.
    states = possible_fingerings(FretPosition(string=1, fret=1), config)
    assert [(s.hand_position, s.finger) for s in states] == [(1, 1)]


def test_open_string_states_cover_hand_positions():
    config = SolverConfig()
    states = possible_fingerings(FretPosition(string=1, fret=0), config)
    # finger 0 everywhere, one state per valid hand position (24-3 = 21).
    assert len(states) == config.hand_position_limit
    assert all(s.finger == 0 for s in states)
    assert [s.hand_position for s in states] == list(
        range(1, config.hand_position_limit + 1)
    )


def test_hand_position_limit_is_bounded_and_overridable():
    assert SolverConfig(max_fret=24).hand_position_limit == 21
    assert SolverConfig(max_fret=12).hand_position_limit == 9
    config = SolverConfig(max_fret=24, max_hand_position=7)
    assert config.hand_position_limit == 7
    assert len(possible_fingerings(FretPosition(string=1, fret=0), config)) == 7
