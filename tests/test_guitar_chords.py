"""Chord (onset event) solver tests: shapes, locks, DP, structured errors.

The named fixtures (E major, F major, the impossible 7-note event) are the
acceptance fixtures of the v3 spec; every assertion is on the JSON document
or on structured error details, never on solver internals.
"""

import json

import pytest

from muscriptor.guitar_arrangement import (
    IncompatibleChordLocksError,
    TooManyChordNotesError,
    UnplayableChordError,
    arrange,
)
from muscriptor.guitar_arrangement.events import (
    analyze_polyphony,
    group_into_events,
)
from muscriptor.guitar_arrangement.models import MidiNote
from muscriptor.guitar_arrangement.phrases import split_event_phrases

from .midi_build import melody_midi

E_MAJOR = (40, 47, 52, 56, 59, 64)
F_MAJOR = (41, 48, 53, 57, 60, 65)


def _locks(locks: list[dict]) -> str:
    return json.dumps({"version": 1, "locks": locks})


def _notes_by_pitch(document):
    return {note["pitch"]: note for note in document["notes"]}


# ---------------------------------------------------------------------------
# Dyad / triad
# ---------------------------------------------------------------------------


def test_dyad_gets_distinct_strings_and_keeps_both_notes():
    document = arrange(melody_midi([(64, 0, 480), (67, 0, 480)]), filename="s.mid")
    assert document["metrics"]["note_count"] == 2
    notes = _notes_by_pitch(document)
    assert notes[64]["string"] != notes[67]["string"]
    for note in document["notes"]:
        open_pitch = document["instrument"]["open_pitches"][note["string"] - 1]
        assert open_pitch + note["fret"] == note["pitch"]
    # Both notes sit in one onset event, in the same column of time.
    assert document["events"][0]["onset_ticks"] == 0
    assert len(document["events"][0]["note_ids"]) == 2


def test_triad_keeps_three_notes():
    document = arrange(
        melody_midi([(60, 0, 480), (64, 0, 480), (67, 0, 480)]), filename="s.mid"
    )
    assert document["metrics"]["note_count"] == 3
    assert len({note["string"] for note in document["notes"]}) == 3
    assert document["polyphony_analysis"]["largest_onset_group"] == 3


# ---------------------------------------------------------------------------
# E major вЂ” the canonical six-string fixture
# ---------------------------------------------------------------------------


def test_e_major_six_notes_on_six_distinct_strings():
    document = arrange(
        melody_midi([(p, 0, 1920) for p in E_MAJOR]), filename="emajor.mid"
    )
    assert document["schema_version"] == 3
    assert document["metrics"]["note_count"] == 6
    notes = _notes_by_pitch(document)
    assert sorted(note["string"] for note in document["notes"]) == [1, 2, 3, 4, 5, 6]
    for pitch, note in notes.items():
        open_pitch = document["instrument"]["open_pitches"][note["string"] - 1]
        assert open_pitch + note["fret"] == pitch
    assert document["polyphony_analysis"]["largest_onset_group"] == 6


def test_e_major_locked_form_is_accepted():
    """The known open-E shape can be pinned with locks and comes back intact."""
    locks = _locks(
        [
            {"note_id": "track:0/channel:0/note:1", "string": 6, "fret": 0},
            {"note_id": "track:0/channel:0/note:2", "string": 5, "fret": 2},
            {"note_id": "track:0/channel:0/note:3", "string": 4, "fret": 2},
            {"note_id": "track:0/channel:0/note:4", "string": 3, "fret": 1},
            {"note_id": "track:0/channel:0/note:5", "string": 2, "fret": 0},
            {"note_id": "track:0/channel:0/note:6", "string": 1, "fret": 0},
        ]
    )
    document = arrange(
        melody_midi([(p, 0, 1920) for p in E_MAJOR]),
        filename="emajor.mid",
        overrides_text=locks,
    )
    assert document["metrics"]["note_count"] == 6
    notes = _notes_by_pitch(document)
    expected = {40: (6, 0), 47: (5, 2), 52: (4, 2), 56: (3, 1), 59: (2, 0), 64: (1, 0)}
    for pitch, (string, fret) in expected.items():
        assert (notes[pitch]["string"], notes[pitch]["fret"]) == (string, fret)
        assert notes[pitch]["locked"]


def test_f_major_locked_barre_shape_is_preserved():
    """F barre: locks pin 1-1/2-1/3-2/4-3/5-3/6-1 and must survive solving."""
    locks = _locks(
        [
            {"note_id": "track:0/channel:0/note:1", "string": 6, "fret": 1},
            {"note_id": "track:0/channel:0/note:2", "string": 5, "fret": 3},
            {"note_id": "track:0/channel:0/note:3", "string": 4, "fret": 3},
            {"note_id": "track:0/channel:0/note:4", "string": 3, "fret": 2},
            {"note_id": "track:0/channel:0/note:5", "string": 2, "fret": 1},
            {"note_id": "track:0/channel:0/note:6", "string": 1, "fret": 1},
        ]
    )
    document = arrange(
        melody_midi([(p, 0, 1920) for p in F_MAJOR]),
        filename="fmajor.mid",
        overrides_text=locks,
    )
    assert document["metrics"]["note_count"] == 6
    notes = _notes_by_pitch(document)
    expected = {41: (6, 1), 48: (5, 3), 53: (4, 3), 57: (3, 2), 60: (2, 1), 65: (1, 1)}
    for pitch, (string, fret) in expected.items():
        assert (notes[pitch]["string"], notes[pitch]["fret"]) == (string, fret)
    # The finger annotation is honest about the barre (finger 1 across the
    # fret-1 strings) and the event is flagged complete.
    event = document["events"][0]
    assert event["finger_assignment_complete"]
    barre = next(b for b in event["barres"] if b["fret"] == 1)
    assert barre["finger"] == 1
    assert barre["from_string"] == 1 and barre["to_string"] == 6


def test_two_chord_locks_adapt_the_rest_of_the_chord():
    """Pin two notes of E major; the other four re-solve around them."""
    document = arrange(
        melody_midi([(p, 0, 1920) for p in E_MAJOR]),
        filename="emajor.mid",
        overrides_text=_locks(
            [
                {"note_id": "track:0/channel:0/note:4", "string": 3, "fret": 1},
                {"note_id": "track:0/channel:0/note:5", "string": 2, "fret": 0},
            ]
        ),
    )
    assert document["metrics"]["note_count"] == 6
    assert document["metrics"]["locked_notes"] == 2
    notes = _notes_by_pitch(document)
    assert (notes[56]["string"], notes[56]["fret"]) == (3, 1)
    assert (notes[59]["string"], notes[59]["fret"]) == (2, 0)
    assert sorted(note["string"] for note in document["notes"]) == [1, 2, 3, 4, 5, 6]
    for note in document["notes"]:
        open_pitch = document["instrument"]["open_pitches"][note["string"] - 1]
        assert open_pitch + note["fret"] == note["pitch"]


def test_conflicting_locks_on_one_string_are_rejected():
    data = melody_midi([(p, 0, 480) for p in (60, 64, 67)])
    # note:1 (60) and note:2 (64) both pinned to string 3.
    with pytest.raises(IncompatibleChordLocksError) as excinfo:
        arrange(
            data,
            filename="s.mid",
            overrides_text=_locks(
                [
                    {"note_id": "track:0/channel:0/note:1", "string": 3, "fret": 5},
                    {"note_id": "track:0/channel:0/note:2", "string": 3, "fret": 9},
                ]
            ),
        )
    assert sorted(excinfo.value.details["note_ids"]) == [
        "track:0/channel:0/note:1",
        "track:0/channel:0/note:2",
    ]
    assert excinfo.value.details["strings"] == [3, 3]


def test_unlock_returns_the_automatic_shape():
    data = melody_midi([(p, 0, 480) for p in E_MAJOR])
    locked = arrange(
        data,
        filename="s.mid",
        overrides_text=_locks(
            [{"note_id": "track:0/channel:0/note:2", "string": 5, "fret": 2}]
        ),
    )
    free = arrange(data, filename="s.mid")
    assert locked["metrics"]["locked_notes"] == 1
    assert free["metrics"]["locked_notes"] == 0
    assert [note["string"] for note in free["notes"]] == [
        note["string"] for note in locked["notes"]
    ]
    assert [note["fret"] for note in free["notes"]] == [
        note["fret"] for note in locked["notes"]
    ]


# ---------------------------------------------------------------------------
# Structured errors: too many notes, impossible unison
# ---------------------------------------------------------------------------


def test_seven_notes_give_a_structured_error():
    pitches = (36, 40, 43, 47, 50, 53, 56)
    with pytest.raises(TooManyChordNotesError) as excinfo:
        arrange(melody_midi([(p, 0, 480) for p in pitches]), filename="s.mid")
    details = excinfo.value.details
    assert details["onset_ticks"] == 0
    # Pitches come in event order (highest first).
    assert details["pitches"] == sorted(pitches, reverse=True)
    assert details["available_strings"] == 6
    assert len(details["note_ids"]) == 7
    # No note was silently dropped: all ids are listed.
    assert all("note:" in nid for nid in details["note_ids"])


def test_impossible_unison_gives_unplayable_chord_not_a_dropped_note():
    # MIDI 40 can only sound on string 6 (fret 0) in standard tuning.
    with pytest.raises(UnplayableChordError) as excinfo:
        arrange(melody_midi([(40, 0, 480), (40, 0, 480)]), filename="s.mid")
    details = excinfo.value.details
    assert details["pitches"] == [40, 40]
    assert details["available_strings"] == 6
    assert details["reason"]


def test_two_identical_pitches_survive_on_two_strings():
    # MIDI 55 sounds on string 3 fret 0 AND string 4 fret 5.
    document = arrange(melody_midi([(55, 0, 480), (55, 0, 480)]), filename="s.mid")
    assert document["metrics"]["note_count"] == 2
    strings = sorted(note["string"] for note in document["notes"])
    assert strings == [3, 4]
    for note in document["notes"]:
        open_pitch = document["instrument"]["open_pitches"][note["string"] - 1]
        assert open_pitch + note["fret"] == 55


# ---------------------------------------------------------------------------
# Global DP across a chord sequence
# ---------------------------------------------------------------------------


def test_dp_moves_early_note_for_a_higher_next_event():
    """Pitch 52 can sit at fret 2 (low) or fret 12+ (high); pitch 76 is only
    reachable high. The global DP must pre-position the first event high вЂ”
    a greedy solver would park it at the nut."""
    document = arrange(
        melody_midi([(52, 0, 480), (76, 480, 480)]), filename="s.mid"
    )
    first = _notes_by_pitch(document)[52]
    assert first["fret"] >= 12
    second = _notes_by_pitch(document)[76]
    assert second["fret"] >= 12


def test_chord_progression_prefers_a_usable_high_shape():
    """A low first chord followed by a high-only chord: the first chord's
    high alternative wins when the next event demands it."""
    document = arrange(
        melody_midi(
            [
                (52, 0, 480),
                (64, 0, 480),
                (76, 480, 480),
                (79, 960, 480),
            ]
        ),
        filename="s.mid",
    )
    notes = _notes_by_pitch(document)
    # The second event (76, 79) is only playable high; the first event's
    # shapes must have followed it up the neck — e.g. the pitch-52 note
    # no longer sits at fret 2.
    assert notes[76]["fret"] >= 12
    assert notes[52]["fret"] >= 7


# ---------------------------------------------------------------------------
# Candidate accounting
# ---------------------------------------------------------------------------


def test_candidate_cap_is_reported_honestly():
    from muscriptor.guitar_arrangement import SolverConfig

    document = arrange(
        melody_midi([(60, 0, 480), (64, 0, 480), (67, 480, 480)]),
        filename="s.mid",
        config=SolverConfig(max_chord_candidates=2),
    )
    metrics = document["metrics"]
    assert metrics["generated_candidates"] > metrics["pruned_candidates"]
    pruned_events = [
        event for event in document["events"] if event["pruned_candidates"]
    ]
    assert pruned_events
    for event in pruned_events:
        assert event["optimal_within"] == "retained_candidates"


def test_arrangement_is_byte_stable_v3():
    data = melody_midi([(p, 0, 480) for p in E_MAJOR])
    first = arrange(data, filename="s.mid")
    second = arrange(data, filename="s.mid")
    assert json.dumps(first) == json.dumps(second)


# ---------------------------------------------------------------------------
# Out-of-range input: aggregated diagnosis, never a silent fix
# ---------------------------------------------------------------------------


def test_out_of_range_notes_are_reported_all_at_once():
    from muscriptor.guitar_arrangement import UnplayableNoteError

    # A bass line below the lowest string (like a transcription of a song
    # with a real bass guitar): the error must list every offender, not
    # fail on the first one.
    with pytest.raises(UnplayableNoteError) as excinfo:
        arrange(
            melody_midi([(37, 0, 240), (39, 240, 240), (64, 480, 240)]),
            filename="s.mid",
        )
    details = excinfo.value.details
    assert details["offender_count"] == 2
    assert details["offender_pitches"] == [37, 39]
    assert details["low_pitch"] == 40
    # The playable ceiling includes fretted notes above the highest open
    # string: 64 + 24 = 88.
    assert details["high_pitch"] == 88
    text = str(excinfo.value)
    assert "2 of 3" in text
    assert "40–88" in text
    assert "+12 semitones" in text


def test_melody_top_policy_can_rescue_below_range_notes():
    # The low note shares its onset with a higher one, so the explicit `top`
    # reduction removes it before the range check — the arrangement succeeds.
    document = arrange(
        melody_midi([(37, 0, 480), (64, 0, 480)]),
        filename="s.mid",
        melody_policy="top",
    )
    assert [n["pitch"] for n in document["notes"]] == [64]
