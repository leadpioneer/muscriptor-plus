"""CLI tests for `muscriptor arrange-guitar`.

Everything runs through typer's CliRunner against programmatically built
MIDI fixtures; the transcription model is never loaded (and the test proves
that).
"""

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from muscriptor.main import app

from .midi_build import melody_midi, raw_midi

runner = CliRunner()


def _write_midi(tmp_path: Path, notes, name="song.mid") -> Path:
    path = tmp_path / name
    path.write_bytes(melody_midi(notes))
    return path


def test_list_tracks_prints_the_table_and_skips_solving(tmp_path):
    path = _write_midi(tmp_path, [(64, 0, 240), (67, 240, 240)])
    result = runner.invoke(app, ["arrange-guitar", str(path), "--list-tracks"])
    assert result.exit_code == 0
    assert "track" in result.output
    assert "Melody" in result.output
    assert "2" in result.output  # note count


def test_successful_arrangement_writes_the_json(tmp_path):
    path = _write_midi(tmp_path, [(64, 0, 240), (67, 240, 240)])
    output = tmp_path / "arrangement.json"
    result = runner.invoke(
        app,
        ["arrange-guitar", str(path), "--track", "0", "--output", str(output)],
    )
    assert result.exit_code == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["schema_version"] == 2
    assert document["source"]["filename"] == "song.mid"
    assert document["metrics"]["note_count"] == 2
    for note in document["notes"]:
        open_pitch = document["instrument"]["open_pitches"][note["string"] - 1]
        assert open_pitch + note["fret"] == note["pitch"]


def test_ambiguous_track_fails_with_a_readable_error(tmp_path):
    data = raw_midi(
        [
            mido_note(64, 0, 120, 240, name="Guitar"),
            mido_note(40, 0, 120, 240, name="Bass"),
        ]
    )
    path = tmp_path / "two_tracks.mid"
    path.write_bytes(data)
    result = runner.invoke(app, ["arrange-guitar", str(path)])
    assert result.exit_code == 1
    assert "several note-bearing tracks" in result.output
    assert "Guitar" in result.output and "Bass" in result.output


def mido_note(pitch, start, duration, _end, name=""):
    """One-note track as a message list (delta times are already relative)."""
    from mido import Message, MetaMessage

    return [
        MetaMessage("track_name", name=name, time=0),
        Message("note_on", note=pitch, velocity=100, time=start),
        Message("note_off", note=pitch, velocity=0, time=duration),
    ]


def test_broken_midi_fails_cleanly(tmp_path):
    path = tmp_path / "broken.mid"
    path.write_bytes(b"definitely not a midi file")
    result = runner.invoke(app, ["arrange-guitar", str(path)])
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_overrides_file_pins_a_position(tmp_path):
    path = _write_midi(tmp_path, [(64, 0, 240)])
    overrides = tmp_path / "overrides.json"
    overrides.write_text(
        json.dumps(
            {
                "version": 1,
                "locks": [
                    {
                        "note_id": "track:0/channel:0/note:1",
                        "string": 3,
                        "fret": 9,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "arrangement.json"
    result = runner.invoke(
        app,
        [
            "arrange-guitar",
            str(path),
            "--overrides",
            str(overrides),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    document = json.loads(output.read_text(encoding="utf-8"))
    note = document["notes"][0]
    assert note["locked"] is True
    assert (note["string"], note["fret"]) == (3, 9)


def test_transcription_model_is_never_loaded(tmp_path):
    path = _write_midi(tmp_path, [(64, 0, 240)])
    with patch(
        "muscriptor.transcription_model.TranscriptionModel.load_model"
    ) as load_model:
        result = runner.invoke(
            app, ["arrange-guitar", str(path), "--list-tracks"]
        )
        assert result.exit_code == 0
        load_model.assert_not_called()
