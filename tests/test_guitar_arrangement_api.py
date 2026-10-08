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
    assert document["schema_version"] == 3
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


def test_polyphonic_onset_is_arranged_by_default():
    """Since v3 a dyad is normal input: both notes survive on distinct strings."""
    data = melody_midi([(64, 0, 240), (67, 0, 240)])
    resp = _post(_client(), data=data)
    assert resp.status_code == 200
    document = resp.json()
    assert document["metrics"]["note_count"] == 2
    assert len({note["string"] for note in document["notes"]}) == 2
    analysis = document["polyphony_analysis"]
    assert analysis["onset_event_count"] == 1
    assert analysis["polyphonic_event_count"] == 1
    assert analysis["largest_onset_group"] == 2
    assert analysis["strictly_monophonic"] is False
    # The event structure links both notes to one event id.
    assert len({note["event_id"] for note in document["notes"]}) == 1
    assert document["events"][0]["note_ids"] == [
        note["id"] for note in document["notes"]
    ]


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


def test_arrangement_to_musicxml_endpoint_returns_fingering_preserving_xml():
    import xml.etree.ElementTree as ET

    data = melody_midi([(p, 0, 480) for p in (60, 64, 67)])
    arrange_resp = _post(_client(), data=data)
    document = arrange_resp.json()
    resp = _client().post(
        "/arrange/guitar/musicxml",
        files={
            "document": (
                "arrangement.json",
                json.dumps(document).encode(),
                "application/json",
            )
        },
    )
    assert resp.status_code == 200
    assert "musicxml" in resp.headers["content-type"]
    root = ET.fromstring(resp.content)
    assert root.tag == "score-partwise"
    assert len(list(root.iter("technical"))) == 3


def test_arrangement_to_pdf_endpoint_engraves_via_musescore():
    import zipfile
    import io

    data = melody_midi([(p, 0, 480) for p in (60, 64, 67)])
    document = _post(_client(), data=data).json()
    resp = _client().post(
        "/arrange/guitar/pdf",
        files={
            "document": (
                "arrangement.json",
                json.dumps(document).encode(),
                "application/json",
            )
        },
    )
    assert resp.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    names = archive.namelist()
    assert "full_score.pdf" in names
    pdf = archive.read("full_score.pdf")
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1000


def test_arrangement_to_pdf_endpoint_503_without_musescore(monkeypatch):
    from muscriptor.utils import sheets

    def _raise():
        raise sheets.MuseScoreNotFoundError("MuseScore was not found")

    monkeypatch.setattr(sheets, "find_musescore", _raise)
    data = melody_midi([(60, 0, 480)])
    document = _post(_client(), data=data).json()
    resp = _client().post(
        "/arrange/guitar/pdf",
        files={
            "document": (
                "arrangement.json",
                json.dumps(document).encode(),
                "application/json",
            )
        },
    )
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["code"] == "musescore_unavailable"


def test_arrangement_to_pdf_endpoint_gives_400_for_a_broken_document():
    resp = _client().post(
        "/arrange/guitar/pdf",
        files={
            "document": (
                "arrangement.json",
                b'{"schema_version": 9}',
                "application/json",
            )
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unsupported_arrangement_schema"


def test_result_is_serialization_stable():
    first = _post(_client()).content
    second = _post(_client()).content
    assert first == second


def test_melody_reduction_via_melody_form_field():
    # Two simultaneous onsets: kept by default, reduced only on request.
    data = melody_midi([(60, 0, 240), (67, 0, 240), (72, 240, 240)])
    default = _post(_client(), data=data)
    assert default.status_code == 200
    assert default.json()["metrics"]["note_count"] == 3
    resp = _post(_client(), data=data, melody="top")
    assert resp.status_code == 200
    document = resp.json()
    assert document["melody_reduction"] == {
        "policy": "top",
        "dropped_note_count": 1,
        "dropped": [{"tick": 0, "pitch": 60}],
    }
    assert document["metrics"]["note_count"] == 2
    assert [note["pitch"] for note in document["notes"]] == [67, 72]
    # Byte-stable across identical requests, with the reduction included.
    assert _post(_client(), data=data, melody="top").content == resp.content


def test_melody_bottom_policy_keeps_the_low_note():
    data = melody_midi([(60, 0, 240), (67, 0, 240)])
    resp = _post(_client(), data=data, melody="bottom")
    assert resp.status_code == 200
    assert [note["pitch"] for note in resp.json()["notes"]] == [60]


def test_melody_reduction_drops_locks_for_removed_notes():
    data = melody_midi([(60, 0, 240), (67, 0, 240), (72, 240, 240)])
    # The pitch-60 note is dropped by the reduction; its id would have been
    # "track:0/channel:0/note:1". A lock referencing it must fail clearly.
    resp = _post(
        _client(),
        data=data,
        melody="top",
        overrides=json.dumps(
            {
                "version": 1,
                "locks": [
                    {"note_id": "track:0/channel:0/note:1", "string": 3, "fret": 5}
                ],
            }
        ),
    )
    assert resp.status_code == 400
    assert "unknown note id" in resp.json()["detail"]["message"]


def test_unknown_melody_policy_gives_400():
    resp = _post(_client(), melody="skyline_v2")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_melody_policy"


def test_arrangement_to_midi_endpoint_round_trips():
    arrange_resp = _post(_client())
    document = arrange_resp.json()
    resp = _client().post(
        "/arrange/guitar/midi",
        files={
            "document": ("arrangement.json", arrange_resp.content, "application/json")
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/midi")
    assert "attachment" in resp.headers["content-disposition"]
    # The returned MIDI parses and carries exactly the document's notes.
    import io

    from mido import MidiFile

    midi = MidiFile(file=io.BytesIO(resp.content))
    assert midi.ticks_per_beat == document["source"]["ticks_per_beat"]
    onsets = []
    for track in midi.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                onsets.append((tick, msg.note))
    assert sorted(onsets) == sorted(
        (n["onset_ticks"], n["pitch"]) for n in document["notes"]
    )


def test_arrangement_to_midi_endpoint_rejects_garbage():
    resp = _client().post(
        "/arrange/guitar/midi",
        files={"document": ("a.json", b"not json", "application/json")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_arrangement"
    resp = _client().post(
        "/arrange/guitar/midi",
        files={
            "document": (
                "a.json",
                json.dumps({"schema_version": 9}).encode(),
                "application/json",
            )
        },
    )
    assert resp.status_code == 400


def test_arrangement_to_tab_endpoint_returns_text():
    arrange_resp = _post(_client())
    resp = _client().post(
        "/arrange/guitar/tab",
        files={
            "document": ("arrangement.json", arrange_resp.content, "application/json")
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text
    assert text.count("\n") == 5  # six string lines
    assert text.splitlines()[0].startswith("E4")
