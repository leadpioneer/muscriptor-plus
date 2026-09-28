"""Onset-event grouping, polyphony analysis and phrase splitting tests."""

from muscriptor.guitar_arrangement.events import (
    analyze_polyphony,
    group_into_events,
)
from muscriptor.guitar_arrangement.models import MidiNote
from muscriptor.guitar_arrangement.phrases import split_event_phrases

TPB = 480


def _note(ordinal, pitch, onset, offset):
    return MidiNote(
        id=f"track:0/channel:0/note:{ordinal}",
        track_index=0,
        channel=0,
        pitch=pitch,
        onset_ticks=onset,
        offset_ticks=offset,
        velocity=100,
    )


def test_event_ordering_is_pitch_descending_then_id():
    notes = (
        _note(1, 60, 0, 240),
        _note(2, 67, 0, 240),
        _note(3, 64, 0, 240),
    )
    events = group_into_events(notes)
    assert len(events) == 1
    # Highest pitch first; ties on equal pitch fall back to note id.
    assert [n.pitch for n in events[0].notes] == [67, 64, 60]


def test_events_are_indexed_sequentially_by_onset():
    notes = (
        _note(1, 60, 480, 720),
        _note(2, 64, 0, 240),
        _note(3, 67, 0, 240),
    )
    events = group_into_events(notes)
    assert [e.index for e in events] == [0, 1]
    assert [e.onset_ticks for e in events] == [0, 480]


def test_polyphony_analysis_counts_onsets_and_activity():
    # Two notes start together and ring; a third starts later, overlapping.
    notes = (
        _note(1, 60, 0, 960),
        _note(2, 67, 0, 480),
        _note(3, 72, 480, 960),
    )
    events = group_into_events(notes)
    analysis = analyze_polyphony(events)
    assert analysis.note_count == 3
    assert analysis.onset_event_count == 2
    assert analysis.polyphonic_event_count == 1
    assert analysis.largest_onset_group == 2
    # Elementary intervals: [0,480) has 2 active, [480,960) has 2 active.
    assert analysis.overlapping_region_count == 2
    assert analysis.max_active_notes == 2
    assert analysis.strictly_monophonic is False


def test_polyphony_analysis_detects_strict_monophony():
    notes = (
        _note(1, 60, 0, 240),
        _note(2, 62, 240, 480),
    )
    analysis = analyze_polyphony(group_into_events(notes))
    assert analysis.strictly_monophonic is True
    assert analysis.overlapping_region_count == 0
    assert analysis.polyphonic_event_count == 0


def test_phrase_split_uses_the_end_of_the_whole_chord():
    """A chord with staggered durations, then real silence → new phrase."""
    events = group_into_events(
        (
            _note(1, 40, 0, 1920),  # long bass note of the chord
            _note(2, 64, 0, 480),
            _note(3, 67, 2400, 2880),  # starts after everything stopped
        )
    )
    phrases = split_event_phrases(events, TPB, phrase_gap_beats=1.0)
    assert len(phrases) == 2
    assert [e.onset_ticks for e in phrases[0]] == [0]
    assert [e.onset_ticks for e in phrases[1]] == [2400]


def test_overlapping_bass_note_is_not_silence():
    """The next onset happens while the long bass note still sounds → the
    events stay in one phrase even though the short note ended long ago."""
    events = group_into_events(
        (
            _note(1, 40, 0, 4800),  # rings across the next onset
            _note(2, 64, 0, 480),
            _note(3, 67, 2400, 2880),
        )
    )
    phrases = split_event_phrases(events, TPB, phrase_gap_beats=1.0)
    assert len(phrases) == 1


def test_note_off_before_the_next_onset_is_still_one_phrase_below_threshold():
    events = group_into_events(
        (
            _note(1, 60, 0, 240),
            _note(2, 62, 240, 480),
        )
    )
    phrases = split_event_phrases(events, TPB, phrase_gap_beats=1.0)
    assert len(phrases) == 1
