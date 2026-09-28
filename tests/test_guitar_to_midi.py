"""Tests for the arrangement JSON → MIDI round trip (to_midi.py)."""

import pytest

from muscriptor.guitar_arrangement import (
    InvalidArrangementError,
    arrangement_json_to_midi,
)
from .midi_build import melody_midi
from .test_server import make_model


def _arrange(**fields) -> dict:
    from fastapi.testclient import TestClient

    from muscriptor.server import create_app

    data = melody_midi([(60, 0, 480), (64, 480, 480), (67, 960, 240)])
    client = TestClient(create_app(make_model()))
    resp = client.post(
        "/arrange/guitar",
        files={"file": ("song.mid", data, "audio/midi")},
        data={k: str(v) for k, v in fields.items() if v is not None},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _parsed_notes(midi_bytes: bytes):
    from mido import MidiFile

    midi = MidiFile(file=__import__("io").BytesIO(midi_bytes))
    assert midi.type == 0
    events = []
    for track in midi.tracks:
        tick = 0
        program = None
        for msg in track:
            tick += msg.time
            if msg.type == "program_change":
                program = msg.program
            elif msg.type == "note_on" and msg.velocity > 0:
                events.append(("on", tick, msg.note, msg.velocity))
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                events.append(("off", tick, msg.note, msg.velocity))
    return midi, events, program


def test_round_trip_preserves_notes_and_source_metadata():
    document = _arrange()
    midi_bytes = arrangement_json_to_midi(document)
    midi, events, program = _parsed_notes(midi_bytes)
    assert midi.ticks_per_beat == document["source"]["ticks_per_beat"]
    assert program == document["source"]["program"]
    # Every document note appears verbatim: same pitch/onset/velocity.
    expected = [
        (n["pitch"], n["onset_ticks"], n["offset_ticks"], n["velocity"])
        for n in document["notes"]
    ]
    ons = sorted((p, t, v) for kind, t, p, v in events if kind == "on")
    offs = sorted((p, t) for kind, t, p, v in events if kind == "off")
    assert ons == sorted((p, o, v) for p, o, f, v in expected)
    assert offs == sorted((p, f) for p, o, f, v in expected)


def test_output_is_byte_stable():
    document = _arrange()
    assert arrangement_json_to_midi(document) == arrangement_json_to_midi(document)


def test_reduction_drops_are_reflected_in_the_midi():
    # Two simultaneous onsets: only the reduced line ends up in the MIDI.
    from fastapi.testclient import TestClient

    from muscriptor.server import create_app

    data = melody_midi([(60, 0, 240), (67, 0, 240)])
    client = TestClient(create_app(make_model()))
    resp = client.post(
        "/arrange/guitar",
        files={"file": ("song.mid", data, "audio/midi")},
        data={"melody": "top"},
    )
    document = resp.json()
    _, events, _ = _parsed_notes(arrangement_json_to_midi(document))
    pitches = {p for kind, _, p, _ in events}
    assert pitches == {67}  # the top note; 60 was dropped


def test_invalid_documents_are_rejected():
    with pytest.raises(InvalidArrangementError):
        arrangement_json_to_midi({"schema_version": 3})
    with pytest.raises(InvalidArrangementError):
        arrangement_json_to_midi({"schema_version": 2})
    with pytest.raises(InvalidArrangementError):
        arrangement_json_to_midi("not a dict")
    bad_note = {
        "schema_version": 2,
        "source": {"ticks_per_beat": 480, "program": 24, "track_name": "x"},
        "notes": [{"pitch": 200, "onset_ticks": 0, "offset_ticks": 1, "velocity": 100}],
    }
    with pytest.raises(InvalidArrangementError):
        arrangement_json_to_midi(bad_note)
    bad_offset = {
        "schema_version": 2,
        "source": {"ticks_per_beat": 480, "program": 24, "track_name": "x"},
        "notes": [{"pitch": 60, "onset_ticks": 10, "offset_ticks": 10, "velocity": 100}],
    }
    with pytest.raises(InvalidArrangementError):
        arrangement_json_to_midi(bad_offset)
