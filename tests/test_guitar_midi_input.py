"""Unit tests for the mido adapter: parsing, ids, selection, monophony."""

import pytest

from muscriptor.guitar_arrangement import (
    AmbiguousTrackError,
    MidiParseError,
    PolyphonicInputError,
    TrackNotFoundError,
    parse_midi,
    select_notes,
)

from .midi_build import melody_midi, raw_midi


def test_absolute_ticks_note_off_velocity_zero_and_ids():
    data = melody_midi([(64, 0, 240), (67, 240, 480), (71, 960, 240)])
    parsed = parse_midi(data)
    assert parsed.ticks_per_beat == 480
    track = select_notes(parsed)
    assert track.track_index == 0
    assert track.channel == 0
    assert track.name == "Melody"
    assert [n.pitch for n in track.notes] == [64, 67, 71]
    assert [n.onset_ticks for n in track.notes] == [0, 240, 960]
    assert [n.offset_ticks for n in track.notes] == [240, 720, 1200]
    assert [n.id for n in track.notes] == [
        "track:0/channel:0/note:1",
        "track:0/channel:0/note:2",
        "track:0/channel:0/note:3",
    ]


def test_ids_are_stable_across_parses():
    data = melody_midi([(64, 0, 120), (66, 120, 120)])
    first = [n.id for n in select_notes(parse_midi(data)).notes]
    second = [n.id for n in select_notes(parse_midi(data)).notes]
    assert first == second


def test_velocity_zero_note_on_closes_the_note():
    data = raw_midi(
        [
            [
                mido_note_on(64, 100, 0),
                mido_note_on(64, 0, 240),  # note_on velocity 0 = note_off
            ]
        ]
    )
    notes = select_notes(parse_midi(data)).notes
    assert len(notes) == 1
    assert notes[0].onset_ticks == 0
    assert notes[0].offset_ticks == 240


def mido_note_on(pitch, velocity, delta, channel=0):
    from mido import Message

    return Message(
        "note_on", channel=channel, note=pitch, velocity=velocity, time=delta
    )


def test_track_channel_and_program_are_preserved():
    data = raw_midi(
        [
            [
                Meta_track_name("Lead"),
                Message_program(0, 30),
                mido_note_on(64, 100, 0),
                mido_note_on(64, 0, 120),
            ],
            [
                Meta_track_name("Drums"),
                Message_program(9, 0),
                mido_note_on(38, 100, 0, channel=9),
                mido_note_on(38, 0, 120, channel=9),
            ],
        ]
    )
    parsed = parse_midi(data)
    melody = select_notes(parsed, track=0)
    assert melody.name == "Lead"
    assert melody.program == 30
    drums = select_notes(parsed, track=1)
    assert drums.channel == 9
    assert drums.is_drum
    assert drums.program == 0


def Meta_track_name(name):
    from mido import MetaMessage

    return MetaMessage("track_name", name=name, time=0)


def Message_program(channel, program):
    from mido import Message

    return Message("program_change", channel=channel, program=program, time=0)


def test_single_note_bearing_track_is_autoselected_drums_ignored():
    data = raw_midi(
        [
            [
                Meta_track_name("Drums"),
                mido_note_on(38, 100, 0, channel=9),
                mido_note_on(38, 0, 120, channel=9),
            ],
            [Meta_track_name("Guitar"), mido_note_on(64, 100, 0), mido_note_on(64, 0, 120)],
        ]
    )
    selected = select_notes(parse_midi(data))
    assert selected.track_index == 1  # the only non-drum track
    assert not selected.is_drum


def test_several_tracks_is_ambiguous_with_candidates_listed():
    data = raw_midi(
        [
            [Meta_track_name("Guitar"), mido_note_on(64, 100, 0), mido_note_on(64, 0, 120)],
            [Meta_track_name("Bass"), mido_note_on(40, 100, 0), mido_note_on(40, 0, 120)],
        ]
    )
    parsed = parse_midi(data)
    with pytest.raises(AmbiguousTrackError) as excinfo:
        select_notes(parsed)
    candidates = excinfo.value.details["tracks"]
    assert [c["track_index"] for c in candidates] == [0, 1]
    assert {c["track_name"] for c in candidates} == {"Guitar", "Bass"}
    # Explicit selection works.
    assert select_notes(parsed, track=1).name == "Bass"


def test_unknown_track_is_a_clear_error():
    data = melody_midi([(64, 0, 120)])
    with pytest.raises(TrackNotFoundError):
        select_notes(parse_midi(data), track=5)


def test_file_without_notes_is_an_error():
    data = raw_midi([[Meta_track_name("Empty")]])
    with pytest.raises(TrackNotFoundError):
        select_notes(parse_midi(data))


def test_garbage_bytes_are_a_parse_error():
    with pytest.raises(MidiParseError):
        parse_midi(b"this is not a midi file at all")


def test_simultaneous_onsets_are_polyphonic():
    data = melody_midi([(64, 0, 240), (67, 0, 240), (71, 240, 240)])
    parsed = parse_midi(data)
    notes = select_notes(parsed).notes
    with pytest.raises(PolyphonicInputError) as excinfo:
        from muscriptor.guitar_arrangement import check_monophonic

        check_monophonic(notes)
    error = excinfo.value
    assert error.details["tick"] == 0
    assert error.details["pitches"] == [64, 67]
    assert "monophonic" in str(error)


def test_overlapping_durations_are_not_polyphony():
    # The second note starts before the first one ends (legato / ringing):
    # distinct onsets, so this is a legal monophonic line.
    data = melody_midi([(64, 0, 480), (67, 240, 240)])
    parsed = parse_midi(data)
    notes = select_notes(parsed).notes
    from muscriptor.guitar_arrangement import check_monophonic

    check_monophonic(notes)  # must not raise
    assert [n.onset_ticks for n in notes] == [0, 240]
