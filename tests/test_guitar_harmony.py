"""Jazz chord-symbol detection and its MusicXML rendering.

The detector reads the finished timeline (melody and accompaniment together):
these tests pin down the vocabulary, the melody tolerance, the
disambiguation rules (bass picks between pitch-class twins) and the
`<harmony>` output.
"""

import xml.etree.ElementTree as ET

import pytest

from muscriptor.guitar_arrangement import (
    InvalidArrangementError,
    arrange,
    arrangement_json_to_musicxml,
    detect_chord_labels,
)
from muscriptor.guitar_arrangement.models import MidiNote

from .midi_build import melody_midi


def _notes(spec):
    return [
        MidiNote(
            id=f"n{pitch}@{onset}",
            track_index=0,
            channel=0,
            pitch=pitch,
            onset_ticks=onset,
            offset_ticks=onset + duration,
            velocity=100,
        )
        for pitch, onset, duration in spec
    ]


def _labels(notes, sigs=()):
    return [(c.tick, c.label) for c in detect_chord_labels(notes, 480, sigs)]


# Am / C / Dm / E7 block chords, one bar each, with the root in the bass.
_PROGRESSION = [
    (45, 0, 1920),
    (52, 0, 1920),
    (57, 0, 1920),
    (60, 0, 1920),
    (48, 1920, 1920),
    (52, 1920, 1920),
    (55, 1920, 1920),
    (60, 1920, 1920),
    (50, 3840, 1920),
    (57, 3840, 1920),
    (62, 3840, 1920),
    (65, 3840, 1920),
    (40, 5760, 1920),
    (47, 5760, 1920),
    (50, 5760, 1920),
    (56, 5760, 1920),
]


def test_block_progression_is_detected_bar_by_bar():
    assert _labels(_notes(_PROGRESSION)) == [
        (0, "Am"),
        (1920, "C"),
        (3840, "Dm"),
        (5760, "E7"),
    ]


def test_melody_inside_the_chord_does_not_break_the_label():
    # A high G (chord tone) and a ninth D (colour) over C major.
    assert _labels(
        _notes([(48, 0, 960), (52, 0, 960), (55, 0, 960), (79, 240, 240)])
    ) == [(0, "C")]
    assert _labels(
        _notes([(48, 0, 960), (52, 0, 960), (55, 0, 960), (74, 0, 960)])
    ) == [(0, "Cadd9")]


def test_short_passing_note_is_tolerated():
    # A brief F over C major is a passing tone, not a sus4.
    assert _labels(
        _notes([(48, 0, 960), (52, 0, 960), (55, 0, 960), (65, 0, 120)])
    ) == [(0, "C")]


def test_bass_disambiguates_pitch_class_twins():
    # A C E G: named Am7 with an A bass, C6 with a C bass.
    assert _labels(
        _notes([(45, 0, 960), (52, 0, 960), (60, 0, 960), (67, 0, 960)])
    ) == [(0, "Am7")]
    assert _labels(
        _notes([(48, 0, 960), (52, 0, 960), (55, 0, 960), (57, 0, 960)])
    ) == [(0, "C6")]


def test_chord_tone_bass_becomes_a_slash_chord():
    assert _labels(_notes([(52, 0, 960), (60, 0, 960), (67, 0, 960)])) == [(0, "C/E")]


def test_seventh_and_half_diminished_vocabulary():
    assert _labels(
        _notes([(50, 0, 960), (53, 0, 960), (57, 0, 960), (60, 0, 960)])
    ) == [(0, "Dm7")]
    assert _labels(
        _notes([(59, 0, 960), (62, 0, 960), (65, 0, 960), (69, 0, 960)])
    ) == [(0, "Bm7b5")]


def test_dyads_and_clusters_are_not_named():
    assert _labels(_notes([(48, 0, 960), (52, 0, 960)])) == []
    assert _labels(_notes([(60, 0, 960), (61, 0, 960), (62, 0, 960)])) == []
    assert _labels(_notes([(60, 0, 960)])) == []


def test_single_beat_blip_between_equal_labels_is_absorbed():
    notes = _notes(
        [
            (45, 0, 480),
            (61, 0, 480),
            (64, 0, 480),  # A major, beat 1
            (48, 480, 480),
            (52, 480, 480),
            (55, 480, 480),  # C major, beat 2
            (45, 960, 480),
            (61, 960, 480),
            (64, 960, 480),  # A major, beat 3
        ]
    )
    assert _labels(notes) == [(0, "A")]


def test_arrangement_document_carries_chord_symbols():
    document = arrange(
        melody_midi([(p, t, d) for p, t, d in _PROGRESSION]), filename="prog.mid"
    )
    assert [(c["tick"], c["label"]) for c in document["chords"]] == [
        (0, "Am"),
        (1920, "C"),
        (3840, "Dm"),
        (5760, "E7"),
    ]
    assert document["chords"][0]["root"] == "A"
    assert document["chords"][0]["kind"] == "m"
    assert document["chords"][0]["bass"] is None


def test_chord_detection_can_be_disabled():
    document = arrange(
        melody_midi(_PROGRESSION), filename="prog.mid", detect_chords=False
    )
    assert document["chords"] == []


def _harmonies(xml_bytes):
    return list(ET.fromstring(xml_bytes).iter("harmony"))


def test_musicxml_renders_chords_as_harmony_elements():
    document = arrange(melody_midi(_PROGRESSION), filename="prog.mid")
    root = ET.fromstring(arrangement_json_to_musicxml(document))
    harmonies = list(root.iter("harmony"))
    assert len(harmonies) == 4
    first = harmonies[0]
    assert first.findtext("root/root-step") == "A"
    assert first.findtext("kind") == "minor"
    assert first.find("bass") is None
    kinds = [h.findtext("kind") for h in harmonies]
    assert kinds == ["minor", "major", "minor", "dominant"]


def test_musicxml_harmony_supports_bass_and_degrees():
    document = arrange(
        melody_midi([(48, 0, 960), (52, 0, 960), (55, 0, 960), (74, 0, 960)]),
        filename="c.mid",
    )
    assert document["chords"][0]["kind"] == "add9"
    harmony = _harmonies(arrangement_json_to_musicxml(document))[0]
    assert harmony.findtext("kind") == "major"
    assert harmony.findtext("degree/degree-value") == "9"
    assert harmony.findtext("degree/degree-type") == "add"

    slash = arrange(
        melody_midi([(52, 0, 960), (60, 0, 960), (67, 0, 960)]), filename="slash.mid"
    )
    harmony = _harmonies(arrangement_json_to_musicxml(slash))[0]
    assert harmony.findtext("bass/bass-step") == "E"


def test_musicxml_chords_can_be_disabled():
    document = arrange(melody_midi(_PROGRESSION), filename="prog.mid")
    xml_bytes = arrangement_json_to_musicxml(document, chords=False)
    assert _harmonies(xml_bytes) == []


def test_musicxml_rejects_malformed_chords():
    document = arrange(melody_midi(_PROGRESSION), filename="prog.mid")
    document["chords"] = [{"tick": 0, "root": "A", "kind": "polka"}]
    with pytest.raises(InvalidArrangementError):
        arrangement_json_to_musicxml(document)
