"""Unit tests for the deterministic melody reduction (melody.py)."""

import pytest

from muscriptor.guitar_arrangement import MidiNote, reduce_to_melody


def note(ordinal, pitch, onset, offset=None):
    return MidiNote(
        id=f"track:0/channel:0/note:{ordinal}",
        track_index=0,
        channel=0,
        pitch=pitch,
        onset_ticks=onset,
        offset_ticks=onset if offset is None else offset,
        velocity=100,
    )


def test_dyad_keeps_the_top_note_and_drops_the_rest():
    notes = (note(1, 60, 0, 240), note(2, 67, 0, 240), note(3, 72, 240, 480))
    kept, reduction = reduce_to_melody(notes, "top")
    assert [n.pitch for n in kept] == [67, 72]
    assert reduction.dropped_note_count == 1
    assert reduction.to_dict() == {
        "policy": "top",
        "dropped_note_count": 1,
        "dropped": [{"tick": 0, "pitch": 60}],
    }


def test_bottom_policy_keeps_the_lowest_note():
    notes = (note(1, 60, 0, 240), note(2, 67, 0, 240))
    kept, _ = reduce_to_melody(notes, "bottom")
    assert [n.pitch for n in kept] == [60]


def test_kept_notes_keep_their_identity():
    notes = (note(1, 60, 0, 240), note(2, 67, 0, 240), note(3, 72, 240, 480))
    kept, _ = reduce_to_melody(notes, "top")
    assert [n.id for n in kept] == [
        "track:0/channel:0/note:2",
        "track:0/channel:0/note:3",
    ]
    # Onsets/offsets/velocities are never touched.
    assert (kept[0].onset_ticks, kept[0].offset_ticks) == (0, 240)


def test_a_full_chord_collapses_to_one_note():
    # The profile of the real-world file: six simultaneous onsets.
    notes = tuple(
        note(i, pitch, 0, 240) for i, pitch in enumerate([47, 54, 57, 63, 69, 71])
    )
    kept, reduction = reduce_to_melody(notes, "top")
    assert [n.pitch for n in kept] == [71]
    assert reduction.dropped_note_count == 5


def test_unisons_collapse_without_touching_distinct_onsets():
    # Same tick AND pitch (a transcription double-fire) collapses; the same
    # pitch at a different tick stays.
    notes = (note(1, 60, 0, 240), note(2, 60, 0, 240), note(3, 60, 240, 480))
    kept, reduction = reduce_to_melody(notes, "top")
    assert [n.onset_ticks for n in kept] == [0, 240]
    assert reduction.dropped_note_count == 1


def test_monophonic_input_is_unchanged():
    notes = (note(1, 60, 0, 480), note(2, 62, 480, 960))
    kept, reduction = reduce_to_melody(notes, "top")
    assert kept == notes
    assert reduction.dropped_note_count == 0


def test_unknown_policy_is_rejected():
    with pytest.raises(ValueError, match="unknown melody policy"):
        reduce_to_melody((), "skyline_v2")
