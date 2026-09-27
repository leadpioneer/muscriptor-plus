"""API tests for POST /arrange/guitar.

Reuses the fake transcription model from test_server (the endpoint must not
touch it) and programmatically built MIDI fixtures.
"""

import json

from fastapi.testclient import TestClient

from muscriptor.server import create_app

from .midi_build import melody_midi
from .test_server import make_model

_SONG = melody_midi([(64, 0, 240), (67, 240, 240), (71, 480, 240)])


def _client() -> TestClient:
    return TestClient(create_app(make_model()))


def _post(client: TestClient, data: bytes = _SONG, **fields):
    return client.post(
        "/arrange/guitar",
        files={"file": ("song.mid", data, "audio/midi")},
        data={k: str(v) for k, v in fields.items() if v is not None},
    )


def test_upload_returns_the_arrangement_document():
    resp = _post(_client())
    assert resp.status_code == 200
    document = resp.json()
    assert document["schema_version"] == 1
    assert document["source"]["filename"] == "song.mid"
    assert document["source"]["ticks_per_beat"] == 480
    assert document["instrument"]["name"] == "standard_guitar"
    assert document["instrument"]["string_numbering"] == "1_is_highest"
    assert document["instrument"]["open_pitches"] == [64, 59, 55, 50, 45, 40]
    assert document["metrics"]["note_count"] == 3
    for note in document["notes"]:
        open_pitch = document["instrument"]["open_pitches"][note["string"] - 1]
        assert open_pitch + note["fret"] == note["pitch"]
        assert note["legal_positions"]


def test_ambiguous_tracks_give_422_with_candidates():
    from mido import Message, MetaMessage

    from .midi_build import raw_midi

    def track(name, pitch):
        return [
            MetaMessage("track_name", name=name, time=0),
            Message("note_on", note=pitch, velocity=100, time=0),
            Message("note_off", note=pitch, velocity=0, time=240),
        ]

    data = raw_midi([track("A", 64), track("B", 40)])
    resp = _post(_client(), data=data)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "ambiguous_track"
    assert len(detail["details"]["tracks"]) == 2
    # The explicit choice succeeds.
    resp = _post(_client(), data=data, track=1)
    assert resp.status_code == 200
    assert resp.json()["source"]["track_index"] == 1


def test_polyphonic_input_gives_422():
    data = melody_midi([(64, 0, 240), (67, 0, 240)])
    resp = _post(_client(), data=data)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "polyphonic_input"
    assert detail["details"]["pitches"] == [64, 67]


def test_invalid_overrides_give_400():
    resp = _post(
        _client(),
        overrides=json.dumps({"version": 7, "locks": []}),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_overrides"


def test_lock_that_changes_pitch_gives_400():
    resp = _post(
        _client(),
        overrides=json.dumps(
            {
                "version": 1,
                "locks": [
                    {"note_id": "track:0/channel:0/note:1", "string": 2, "fret": 9}
                ],
            }
        ),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_overrides"


def test_broken_midi_gives_400():
    resp = _post(_client(), data=b"garbage bytes")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_midi"


def test_unknown_tuning_gives_400():
    resp = _post(_client(), tuning="drop_z")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_overrides"


def test_result_is_serialization_stable():
    first = _post(_client()).content
    second = _post(_client()).content
    assert first == second
