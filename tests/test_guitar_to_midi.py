"""Tests for the arrangement JSON → MIDI round trip (to_midi.py)."""

import pytest

from muscriptor.guitar_arrangement import (
    InvalidArrangementError,
    UnsupportedArrangementError,
    arrange,
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
    with pytest.raises(UnsupportedArrangementError):
        arrangement_json_to_midi({"schema_version": 1})
    with pytest.raises(UnsupportedArrangementError):
        arrangement_json_to_midi({"schema_version": 9})
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


# ---------------------------------------------------------------------------
# v3: retrigger order, polyphony, tempo and meter
# ---------------------------------------------------------------------------


def test_retrigger_writes_note_off_before_note_on():
    """Two same-pitch notes back to back: the release of the first must be
    written before the onset of the second, or the retriggered note dies."""
    document = _arrange()
    # Mutate into a retrigger: pitch 60, offset of note 1 == onset of note 2.
    notes = document["notes"]
    notes[0]["pitch"] = 60
    notes[1]["pitch"] = 60
    notes[1]["onset_ticks"] = notes[0]["offset_ticks"]
    _, events, _ = _parsed_notes(arrangement_json_to_midi(document))
    at_tick = [(kind, p) for kind, t, p, _ in events if t == notes[0]["offset_ticks"]]
    assert ("off", 60) in at_tick and ("on", 60) in at_tick
    # note_off strictly before note_on at the same tick.
    first_off = next(i for i, (kind, _) in enumerate(at_tick) if kind == "off")
    first_on = next(i for i, (kind, _) in enumerate(at_tick) if kind == "on")
    assert first_off < first_on


def test_polyphonic_event_round_trips_all_notes():
    from .test_guitar_chords import E_MAJOR

    document = arrange(melody_midi([(p, 0, 1920) for p in E_MAJOR]), filename="s.mid")
    _, events, _ = _parsed_notes(arrangement_json_to_midi(document))
    ons = sorted((p, t) for kind, t, p, _ in events if kind == "on")
    assert ons == sorted((p, 0) for p in E_MAJOR)
    offs = sorted((p, t) for kind, t, p, _ in events if kind == "off")
    assert offs == sorted((p, 1920) for p in E_MAJOR)


def test_tempo_and_time_signature_maps_are_written_back():
    from mido import MetaMessage, MidiTrack

    from .midi_build import raw_midi

    conductor = [
        MetaMessage("track_name", name="conductor", time=0),
        MetaMessage("set_tempo", tempo=600000, time=0),
        MetaMessage("time_signature", numerator=3, denominator=4, time=0),
        MetaMessage("set_tempo", tempo=400000, time=960),
    ]
    guitar = [
        MetaMessage("track_name", name="guitar", time=0),
        __import__("mido").Message("note_on", note=64, velocity=100, time=0),
        __import__("mido").Message("note_off", note=64, velocity=0, time=240),
    ]
    data = raw_midi([conductor, guitar])
    document = arrange(data, filename="s.mid", track=1)
    # The parser picked the maps from the conductor track and marked nothing
    # as a default.
    tempos = document["source"]["tempo_events"]
    assert [(t["tick"], t["tempo"], t["is_default"]) for t in tempos] == [
        (0, 600000, False),
        (960, 400000, False),
    ]
    meter = document["source"]["time_signature_events"]
    assert meter[0]["numerator"] == 3 and meter[0]["denominator"] == 4
    assert meter[0]["is_default"] is False

    _, events, _ = _parsed_notes(arrangement_json_to_midi(document))
    midi = __import__("mido").MidiFile(
        file=__import__("io").BytesIO(arrangement_json_to_midi(document))
    )
    tempos_back = [
        (msg.tempo, sum(m.time for m in midi.tracks[0][: i + 1]))
        for i, msg in enumerate(midi.tracks[0])
        if isinstance(msg, MetaMessage) and msg.type == "set_tempo"
    ]
    assert tempos_back == [(600000, 0), (400000, 960)]
    meters_back = [
        (msg.numerator, msg.denominator)
        for msg in midi.tracks[0]
        if isinstance(msg, MetaMessage) and msg.type == "time_signature"
    ]
    assert meters_back == [(3, 4)]


def test_missing_tempo_is_a_marked_default_not_invented_bpm():
    data = melody_midi([(64, 0, 240)])
    document = arrange(data, filename="s.mid")
    tempos = document["source"]["tempo_events"]
    assert len(tempos) == 1
    assert tempos[0]["tempo"] == 500000
    assert tempos[0]["is_default"] is True
    meters = document["source"]["time_signature_events"]
    assert meters[0]["numerator"] == 4 and meters[0]["denominator"] == 4
    assert meters[0]["is_default"] is True
