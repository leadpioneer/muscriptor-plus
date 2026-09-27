"""Unit tests for phrase splitting, the DP solver, locks and serialization.

No real tuning is needed for the DP-behaviour tests: solve_phrase accepts
synthetic candidate lists, so the tests exercise the dynamic programming
itself rather than the fretboard generator.
"""

import pytest

from muscriptor.guitar_arrangement import (
    FretPosition,
    InvalidOverridesError,
    MidiNote,
    STANDARD_TUNING,
    SolverConfig,
    UnplayableNoteError,
    arrange,
    solve_phrase,
    split_phrases,
)

from .midi_build import melody_midi


def _note(index, pitch, onset, duration):
    return MidiNote(
        id=f"n{index}",
        track_index=0,
        channel=0,
        pitch=pitch,
        onset_ticks=onset,
        offset_ticks=onset + duration,
        velocity=100,
    )


# --- Phrase splitting ------------------------------------------------------


def test_gap_longer_than_threshold_starts_a_new_phrase():
    # 480 ticks_per_beat, threshold 1.0 beat = 480 ticks.
    notes = (
        _note(0, 64, 0, 240),
        _note(1, 67, 720, 240),  # gap 480 → new phrase
        _note(2, 71, 960, 240),  # gap 0 → same phrase
    )
    phrases = split_phrases(notes, ticks_per_beat=480, phrase_gap_beats=1.0)
    assert [len(p.notes) for p in phrases] == [1, 2]
    assert [p.index for p in phrases] == [0, 1]


def test_short_gap_keeps_one_phrase():
    notes = (
        _note(0, 64, 0, 240),
        _note(1, 67, 480, 240),  # gap 240 < 480
    )
    phrases = split_phrases(notes, 480, 1.0)
    assert len(phrases) == 1


def test_negative_gap_from_overlap_counts_as_zero():
    notes = (
        _note(0, 64, 0, 960),
        _note(1, 67, 240, 240),  # onset inside the previous note
    )
    phrases = split_phrases(notes, 480, 1.0)
    assert len(phrases) == 1


# --- DP solver -------------------------------------------------------------


def _candidates(*specs):
    return tuple(
        tuple(FretPosition(string=s, fret=f) for s, f in options)
        for options in specs
    )


def test_dp_moves_early_notes_to_avoid_a_late_jump():
    """The spec's key scenario: the phrase ends where only fret ~7 works, and
    the solver must place the *early* notes up there too instead of playing
    low and jumping."""
    config = SolverConfig(
        fret_movement_weight=1.0,
        string_movement_weight=0.1,
        large_position_change_threshold=2,
        large_position_change_weight=10.0,
        high_fret_start=12,
        high_fret_weight=0.01,
    )
    notes = (
        _note(0, 60, 0, 50),
        _note(1, 62, 100, 50),
        _note(2, 64, 200, 50),
    )
    candidates = _candidates(
        ((1, 2), (2, 7)),  # cheap low position or an equally legal high one
        ((1, 2), (2, 7)),
        ((2, 7),),  # the end of the phrase forces the high area
    )
    solution = solve_phrase(notes, candidates, config)
    # Greedy per-note minimum frets would give 2, 2, 7 with a large jump.
    assert [a.position.fret for a in solution.assigned] == [7, 7, 7]
    assert solution.cost == 0.0


def test_without_the_jump_penalty_staying_low_is_fine():
    """Sanity: the solver minimizes the configured cost — remove the jump
    penalty and the low position wins again."""
    config = SolverConfig(
        fret_movement_weight=1.0,
        string_movement_weight=0.1,
        large_position_change_threshold=2,
        large_position_change_weight=0.0,
        high_fret_start=12,
        high_fret_weight=0.01,
    )
    notes = (_note(0, 60, 0, 50), _note(1, 62, 100, 50))
    candidates = _candidates(((1, 2), (2, 7)), ((1, 2), (2, 7)))
    solution = solve_phrase(notes, candidates, config)
    assert [a.position.fret for a in solution.assigned] == [2, 2]


def test_ties_are_broken_deterministically():
    config = SolverConfig(string_movement_weight=0.1)
    notes = (_note(0, 60, 0, 50), _note(1, 60, 100, 50))
    # (1,3) and (2,3) are symmetric; with equal keys the first candidate in
    # the (sorted) list wins — the smaller (fret, string).
    candidates = _candidates(((1, 3), (2, 3)), ((1, 3), (2, 3)))
    first = solve_phrase(notes, candidates, config)
    second = solve_phrase(notes, candidates, config)
    assert [a.position for a in first.assigned] == [
        FretPosition(string=1, fret=3),
        FretPosition(string=1, fret=3),
    ]
    assert [a.position for a in first.assigned] == [
        a.position for a in second.assigned
    ]


def test_empty_candidates_are_an_error_not_a_crash():
    notes = (_note(0, 60, 0, 50),)
    with pytest.raises(UnplayableNoteError):
        solve_phrase(notes, _candidates(()), SolverConfig())


# --- Locks (through the pipeline) ------------------------------------------


def _two_note_midi():
    return melody_midi([(64, 0, 240), (67, 240, 240)])


def test_lock_on_a_legal_position_is_honoured():
    result = arrange(
        _two_note_midi(),
        filename="song.mid",
        overrides_text=(
            '{"version": 1, "locks": [{"note_id": '
            '"track:0/channel:0/note:1", "string": 3, "fret": 9}]}'
        ),
    )
    first = result["notes"][0]
    assert first["locked"] is True
    assert (first["string"], first["fret"]) == (3, 9)
    second = result["notes"][1]
    assert second["locked"] is False
    assert result["metrics"]["locked_notes"] == 1


def test_lock_that_changes_the_pitch_is_rejected():
    # String 2 fret 9 sounds 68, but the note is pitch 64.
    with pytest.raises(InvalidOverridesError) as excinfo:
        arrange(
            _two_note_midi(),
            filename="song.mid",
            overrides_text=(
                '{"version": 1, "locks": [{"note_id": '
                '"track:0/channel:0/note:1", "string": 2, "fret": 9}]}'
            ),
        )
    assert "pitch" in str(excinfo.value)


def test_lock_with_an_unknown_note_id_is_rejected():
    with pytest.raises(InvalidOverridesError) as excinfo:
        arrange(
            _two_note_midi(),
            filename="song.mid",
            overrides_text=(
                '{"version": 1, "locks": [{"note_id": "no/such/note", '
                '"string": 1, "fret": 0}]}'
            ),
        )
    assert "unknown note id" in str(excinfo.value)


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"version": 2, "locks": []}',
        '{"version": 1, "locks": [{"note_id": "x"}]}',
        '{"version": 1, "locks": [{"note_id": "x", "string": 0, "fret": 1}]}',
        '{"version": 1, "locks": [{"note_id": "x", "string": 1, "fret": -1}]}',
    ],
)
def test_malformed_overrides_are_rejected(text):
    with pytest.raises(InvalidOverridesError):
        arrange(_two_note_midi(), filename="song.mid", overrides_text=text)


# --- End-to-end property checks --------------------------------------------

_MELODIES = [
    [(64, 0, 240), (67, 240, 240), (71, 480, 240), (67, 720, 240)],
    [(45, 0, 480), (52, 480, 480), (57, 960, 480)],
    [(76, 0, 120), (74, 240, 120), (71, 480, 120), (69, 720, 120), (64, 960, 480)],
]


@pytest.mark.parametrize("melody", _MELODIES)
def test_arrangement_preserves_music_and_stays_physical(melody):
    result = arrange(melody_midi(melody), filename="song.mid")
    notes = result["notes"]
    assert len(notes) == len(melody)
    open_pitches = STANDARD_TUNING.open_pitches
    for original, arranged in zip(melody, notes):
        pitch, onset, duration = original
        assert arranged["pitch"] == pitch
        assert arranged["onset_ticks"] == onset
        assert arranged["offset_ticks"] == onset + duration
        string, fret = arranged["string"], arranged["fret"]
        assert 1 <= string <= len(open_pitches)
        assert 0 <= fret <= result["instrument"]["max_fret"]
        # Physically consistent: the position really sounds the note's pitch.
        assert open_pitches[string - 1] + fret == pitch
        # And it was among the legal choices.
        assert {"string": string, "fret": fret} in arranged["legal_positions"]


def test_identical_input_gives_identical_output():
    data = melody_midi(_MELODIES[0])
    assert arrange(data, filename="song.mid") == arrange(
        data, filename="song.mid"
    )


def test_thousands_of_notes_are_handled_quickly_enough():
    """No hard ms threshold (CI-unstable), but a pathological blowup would
    still hang the suite: 5000 notes must simply complete."""
    melody = [(60 + (i % 20), i * 120, 100) for i in range(5000)]
    result = arrange(melody_midi(melody), filename="song.mid")
    assert result["metrics"]["note_count"] == 5000
    assert result["metrics"]["phrase_count"] == 1

