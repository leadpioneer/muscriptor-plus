"""Normalization to standard tuning and chord-overflow reduction.

Covers the detuned-transcription case: a part recorded half a step down whose
low roots sit below the standard low E (39 < 40), octave-duplicate artefacts
below the range, onsets with more notes than strings, and the strict policies
that opt out of either behaviour.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from muscriptor.guitar_arrangement import (
    TooManyChordNotesError,
    UnplayableNoteError,
    arrange,
)
from muscriptor.main import app

from .midi_build import melody_midi

runner = CliRunner()

# An Eb-major barre voicing the way a half-step-down guitar sounds it: every
# note is a semitone below its standard position, so the root Eb2 (39) is
# below the standard low E (40).
_EB_CHORD = [
    (39, 0, 480),
    (46, 0, 480),
    (51, 0, 480),
    (55, 0, 480),
    (58, 0, 480),
    (63, 0, 480),
]

# One event with an out-of-range note and its exact octave twin in range:
# the model artifact the normalization removes.
_PHANTOM = [
    (37, 0, 480),
    (44, 0, 480),
    (49, 0, 480),
    (61, 0, 480),
    (64, 0, 480),
    (70, 0, 480),
]


def _document(notes, **kwargs) -> dict:
    return arrange(melody_midi(notes), filename="case.mid", **kwargs)


def _write(tmp_path: Path, notes) -> Path:
    path = tmp_path / "case.mid"
    path.write_bytes(melody_midi(notes))
    return path


def test_standard_in_range_part_is_untouched():
    document = _document([(64, 0, 240), (67, 240, 240), (71, 480, 240)])
    normalization = document["normalization"]
    assert normalization["transposition_semitones"] == 0
    assert normalization["dropped"] == []
    assert normalization["target_tuning"] == "standard"
    assert document["chord_reductions"] == []
    assert [note["pitch"] for note in document["notes"]] == [64, 67, 71]


def test_octave_phantom_below_range_is_dropped_without_shifting():
    document = _document(_PHANTOM)
    normalization = document["normalization"]
    assert normalization["transposition_semitones"] == 0
    assert [d["pitch"] for d in normalization["dropped"]] == [37]
    assert {d["reason"] for d in normalization["dropped"]} == {"octave_duplicate"}
    assert min(note["pitch"] for note in document["notes"]) >= 40


def test_systematic_detuned_roots_shift_the_whole_part_up():
    notes = []
    for index in range(12):
        onset = index * 480
        notes.extend((pitch, onset, 240) for pitch, _onset, _duration in _EB_CHORD)
    document = _document(notes)
    normalization = document["normalization"]
    assert normalization["transposition_semitones"] == 1
    assert normalization["dropped"] == []
    assert normalization["source_low_pitch"] == 39
    pitches = [note["pitch"] for note in document["notes"]]
    assert min(pitches) == 40
    assert max(pitches) == 64


def test_bass_range_part_moves_up_an_octave():
    document = _document([(28, 0, 480), (33, 0, 480), (38, 0, 480)])
    normalization = document["normalization"]
    assert normalization["transposition_semitones"] == 12
    assert normalization["dropped"] == []
    assert min(note["pitch"] for note in document["notes"]) == 40


def test_in_range_octave_doubling_is_kept():
    document = _document([(60, 0, 480), (72, 0, 480)])
    assert document["normalization"]["transposition_semitones"] == 0
    assert document["normalization"]["dropped"] == []
    assert sorted(note["pitch"] for note in document["notes"]) == [60, 72]


def test_impossible_range_reports_the_original_offenders():
    with pytest.raises(UnplayableNoteError) as excinfo:
        _document([(28, 0, 480), (90, 0, 480)])
    message = str(excinfo.value)
    assert "28" in message and "90" in message
    # Nothing was shifted to hide the problem.
    assert excinfo.value.details["offender_pitches"] == [28, 90]


def test_no_normalize_keeps_the_plain_range_error():
    with pytest.raises(UnplayableNoteError) as excinfo:
        _document(_EB_CHORD, normalize=False)
    assert excinfo.value.details["low_pitch"] == 40


def test_oversized_onset_is_reduced_to_a_playable_subset():
    seven = [
        (42, 0, 480),
        (46, 0, 480),
        (49, 0, 480),
        (54, 0, 480),
        (58, 0, 480),
        (63, 0, 480),
        (66, 0, 480),
    ]
    document = _document(seven)
    assert len(document["notes"]) == 6
    reductions = document["chord_reductions"]
    assert [r["onset_ticks"] for r in reductions] == [0]
    assert reductions[0]["note_count"] == 7
    assert [d["reason"] for d in reductions[0]["dropped"]] == ["chord_overflow"]


def test_chord_overflow_error_policy_keeps_the_structured_error():
    seven = [
        (42, 0, 480),
        (46, 0, 480),
        (49, 0, 480),
        (54, 0, 480),
        (58, 0, 480),
        (63, 0, 480),
        (66, 0, 480),
    ]
    with pytest.raises(TooManyChordNotesError):
        _document(seven, chord_overflow="error")


def test_cli_no_normalize_fails_with_the_range_message(tmp_path):
    path = _write(tmp_path, _EB_CHORD)
    result = runner.invoke(
        app,
        ["arrange-guitar", str(path), "--no-normalize", "-o", str(tmp_path / "a.json")],
    )
    assert result.exit_code == 1
    assert "outside the fretboard" in result.output


def test_cli_chord_overflow_error_fails_cleanly(tmp_path):
    seven = [
        (42, 0, 480),
        (46, 0, 480),
        (49, 0, 480),
        (54, 0, 480),
        (58, 0, 480),
        (63, 0, 480),
        (66, 0, 480),
    ]
    path = _write(tmp_path, seven)
    result = runner.invoke(
        app,
        [
            "arrange-guitar",
            str(path),
            "--chord-overflow",
            "error",
            "-o",
            str(tmp_path / "a.json"),
        ],
    )
    assert result.exit_code == 1
    assert "strings" in result.output


def test_cli_writes_the_normalization_report(tmp_path):
    path = _write(tmp_path, _EB_CHORD)
    destination = tmp_path / "a.json"
    result = runner.invoke(app, ["arrange-guitar", str(path), "-o", str(destination)])
    assert result.exit_code == 0
    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["normalization"]["target_tuning"] == "standard"
