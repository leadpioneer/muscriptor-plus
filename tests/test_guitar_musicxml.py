"""MusicXML export tests: exact string/fret, voices, determinism.

The integration tests need MuseScore 4 on the machine and are skipped
otherwise; everything else is hermetic.
"""

import xml.etree.ElementTree as ET

import pytest

from muscriptor.guitar_arrangement import (
    InvalidArrangementError,
    UnsupportedArrangementError,
    arrange,
    arrangement_json_to_musicxml,
)

from .midi_build import melody_midi
from .test_guitar_chords import E_MAJOR, F_MAJOR, _locks
from .test_utils_musescore import musescore_available, musescore_binary  # noqa: F401

E_MAJOR_LOCKS = _locks(
    [
        {"note_id": "track:0/channel:0/note:1", "string": 6, "fret": 0},
        {"note_id": "track:0/channel:0/note:2", "string": 5, "fret": 2},
        {"note_id": "track:0/channel:0/note:3", "string": 4, "fret": 2},
        {"note_id": "track:0/channel:0/note:4", "string": 3, "fret": 1},
        {"note_id": "track:0/channel:0/note:5", "string": 2, "fret": 0},
        {"note_id": "track:0/channel:0/note:6", "string": 1, "fret": 0},
    ]
)

F_MAJOR_LOCKS = _locks(
    [
        {"note_id": "track:0/channel:0/note:1", "string": 6, "fret": 1},
        {"note_id": "track:0/channel:0/note:2", "string": 5, "fret": 3},
        {"note_id": "track:0/channel:0/note:3", "string": 4, "fret": 3},
        {"note_id": "track:0/channel:0/note:4", "string": 3, "fret": 2},
        {"note_id": "track:0/channel:0/note:5", "string": 2, "fret": 1},
        {"note_id": "track:0/channel:0/note:6", "string": 1, "fret": 1},
    ]
)


def _technical_pairs(xml_bytes):
    root = ET.fromstring(xml_bytes)
    return sorted(
        (t.findtext("string"), t.findtext("fret")) for t in root.iter("technical")
    )


def test_e_major_six_notes_one_onset_with_exact_positions():
    document = arrange(
        melody_midi([(p, 0, 1920) for p in E_MAJOR]),
        filename="emajor.mid",
        overrides_text=E_MAJOR_LOCKS,
    )
    xml_bytes = arrangement_json_to_musicxml(document)
    root = ET.fromstring(xml_bytes)
    assert root.tag == "score-partwise"
    technical = _technical_pairs(xml_bytes)
    assert technical == [
        ("1", "0"),
        ("2", "0"),
        ("3", "1"),
        ("4", "2"),
        ("5", "2"),
        ("6", "0"),
    ]
    # All six notes of the event sit in one measure as a chord.
    measures = root.findall(".//measure")
    assert len(measures) == 1
    chord_notes = [n for n in root.iter("note") if n.find("chord") is not None]
    assert len(chord_notes) == 5  # first note plain, five <chord/> followers
    # The tab staff and its tuning are explicit.
    assert root.findtext(".//clef/sign") == "TAB"
    tunings = [
        (t.get("line"), t.findtext("tuning-step"), t.findtext("tuning-octave"))
        for t in root.iter("staff-tuning")
    ]
    assert tunings == [
        ("1", "E", "2"),
        ("2", "A", "2"),
        ("3", "D", "3"),
        ("4", "G", "3"),
        ("5", "B", "3"),
        ("6", "E", "4"),
    ]


def test_f_major_locked_positions_carry_into_the_xml():
    document = arrange(
        melody_midi([(p, 0, 1920) for p in F_MAJOR]),
        filename="fmajor.mid",
        overrides_text=F_MAJOR_LOCKS,
    )
    technical = _technical_pairs(arrangement_json_to_musicxml(document))
    assert technical == [
        ("1", "1"),
        ("2", "1"),
        ("3", "2"),
        ("4", "3"),
        ("5", "3"),
        ("6", "1"),
    ]
    # Fingers are annotated where the allocator knows them.
    fingerings = [
        t.findtext("fingering")
        for t in ET.fromstring(arrangement_json_to_musicxml(document)).iter(
            "technical"
        )
    ]
    assert all(f is not None for f in fingerings)


def test_overlapping_durations_use_voices_not_sequences():
    """A long bass note rings into the next melody note: both keep their
    full durations, in different MusicXML voices."""
    document = arrange(
        melody_midi([(40, 0, 4800), (67, 2400, 480)]), filename="s.mid"
    )
    xml_bytes = arrangement_json_to_musicxml(document)
    root = ET.fromstring(xml_bytes)
    sounding = [n for n in root.iter("note") if n.find("rest") is None]
    bass_notes = [n for n in sounding if n.find(".//pitch/octave").text == "2"]
    melody_notes = [n for n in sounding if n.find(".//pitch/octave").text == "4"]
    assert bass_notes and melody_notes
    # Different voices, and the bass is tied across the barline rather than
    # shortened or turned into a sequence.
    assert bass_notes[0].findtext("voice") != melody_notes[0].findtext("voice")
    assert any(n.find("tie") is not None for n in bass_notes)
    assert any(e.tag == "backup" for e in root.iter())


def test_staggered_chord_members_get_separate_voices_and_keep_durations():
    """Two notes of ONE onset event with different durations must not share
    a <chord/>: chord members with different durations break the engraver's
    measure accounting (MuseScore crash). Each keeps its exact duration."""
    document = arrange(
        melody_midi([(60, 0, 480), (64, 0, 240)]), filename="s.mid"
    )
    root = ET.fromstring(arrangement_json_to_musicxml(document))
    sounding = [n for n in root.iter("note") if n.find("rest") is None]
    long_note = next(n for n in sounding if n.findtext("duration") == "480")
    short_note = next(n for n in sounding if n.findtext("duration") == "240")
    # Same onset, different duration → different voices, no <chord/> bond.
    assert long_note.find("chord") is None
    assert short_note.find("chord") is None
    assert long_note.findtext("voice") != short_note.findtext("voice")


def _measure_voice_balance(root, ticks_per_beat: int):
    """Every voice of every measure must sum to exactly the measure length:
    chord members advance the cursor once, backup rewinds, rests fill.

    Returns a list of (measure_number, voice, written) triples."""
    balances = []
    for measure in root.iter("measure"):
        number = measure.get("number")
        # Measure length = expected sum from the meter (recompute from the
        # first measure's attributes: divisions == ticks_per_beat and 4/4 in
        # all fixtures here, or read explicit attributes).
        cursor = 0
        voice_written: dict[str, int] = {}
        current_voice = None
        for element in measure:
            if element.tag == "note":
                duration = int(element.findtext("duration", "0"))
                current_voice = element.findtext("voice") or "1"
                if element.find("chord") is not None:
                    continue  # shares the previous note's onset
                cursor += duration
                voice_written[current_voice] = voice_written.get(current_voice, 0) + duration
            elif element.tag == "backup":
                step = int(element.text or "0")
                cursor -= step
                voice_written.clear()
            elif element.tag == "forward":
                cursor += int(element.text or "0")
        for voice, written in voice_written.items():
            balances.append((number, voice, written))
        balances.append((number, "cursor", cursor))
    return balances


def test_every_measure_balances_exactly_per_voice():
    """Regression for the MuseScore 'incomplete measure' storm: the written
    durations of every voice in every measure must add up to the measure
    length (4/4, divisions 480 → 1920)."""
    document = arrange(
        melody_midi(
            [
                (60, 0, 480),
                (64, 0, 240),  # staggered chord member
                (67, 480, 460),  # unquantized-ish duration
                (71, 1000, 2600),  # crosses two barlines
                (72, 4000, 800),
            ]
        ),
        filename="s.mid",
    )
    root = ET.fromstring(arrangement_json_to_musicxml(document))
    balances = _measure_voice_balance(root, 480)
    assert balances
    for number, voice, written in balances:
        if voice == "cursor":
            continue
        assert written == 1920, f"measure {number} voice {voice}: {written}"


def test_every_note_carries_an_explicit_type():
    """MuseScore crashes importing notes without <type> whose duration has
    no dyadic form (unquantized MIDI) — every note and rest must carry one."""
    document = arrange(
        melody_midi([(60, 0, 347), (64, 347, 123), (67, 1000, 640)]),
        filename="s.mid",
    )
    root = ET.fromstring(arrangement_json_to_musicxml(document))
    notes = list(root.iter("note"))
    assert notes
    for note in notes:
        assert note.findtext("type"), "note without <type>"
        assert note.findtext("type") in {
            "breve", "whole", "half", "quarter",
            "eighth", "16th", "32nd", "64th", "128th",
        }


def test_dotted_types_are_never_emitted():
    """MuseScore crashes on dotted types whose dotted value disagrees with
    the actual duration (unquantized input) — types are plain dyadic."""
    document = arrange(melody_midi([(60, 0, 58), (64, 58, 700)]), filename="s.mid")
    root = ET.fromstring(arrangement_json_to_musicxml(document))
    for note in root.iter("note"):
        assert note.find("dot") is None


def test_output_is_deterministic_and_parses():
    document = arrange(
        melody_midi([(p, 0, 480) for p in (60, 64, 67)]), filename="s.mid"
    )
    first = arrangement_json_to_musicxml(document)
    second = arrangement_json_to_musicxml(document)
    assert first == second
    ET.fromstring(first)


def test_duration_values_are_source_ticks():
    document = arrange(
        melody_midi([(64, 0, 123), (67, 480, 999)]), filename="s.mid"
    )
    root = ET.fromstring(arrangement_json_to_musicxml(document))
    durations = sorted(
        int(n.findtext("duration"))
        for n in root.iter("note")
        if n.find("rest") is None
    )
    assert durations == [123, 999]  # divisions == ticks_per_beat == 480


def test_invalid_documents_are_rejected():
    with pytest.raises(UnsupportedArrangementError):
        arrangement_json_to_musicxml({"schema_version": 9})
    with pytest.raises(InvalidArrangementError):
        arrangement_json_to_musicxml("not a dict")


def test_legacy_v2_document_is_supported():
    """Documented compatibility: v2 mono documents can be exported too."""
    document = {
        "schema_version": 2,
        "source": {"filename": "s.mid", "ticks_per_beat": 480, "program": 24},
        "instrument": {
            "open_pitches": [64, 59, 55, 50, 45, 40],
            "string_numbering": "1_is_highest",
        },
        "notes": [
            {
                "id": "track:0/channel:0/note:1",
                "pitch": 64,
                "string": 1,
                "fret": 0,
                "finger": 0,
                "onset_ticks": 0,
                "offset_ticks": 480,
                "velocity": 100,
            }
        ],
    }
    root = ET.fromstring(arrangement_json_to_musicxml(document))
    technical = root.find(".//technical")
    assert technical.findtext("string") == "1"
    assert technical.findtext("fret") == "0"


# ---------------------------------------------------------------------------
# Integration with MuseScore (skipped when it is not installed)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not musescore_available(), reason="MuseScore 4 not installed")
class TestMuseScoreRoundTrip:
    def _roundtrip_technical(self, xml_bytes: bytes):
        import subprocess
        import tempfile
        from pathlib import Path

        binary = musescore_binary()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.musicxml"
            src.write_bytes(xml_bytes)
            out = Path(tmp) / "out.musicxml"
            proc = subprocess.run(
                [binary, "-o", str(out), str(src)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            assert out.is_file(), proc.stderr
            root = ET.parse(out).getroot()
        return sorted(
            (t.findtext("string"), t.findtext("fret")) for t in root.iter("technical")
        )

    def test_musescore_preserves_e_major_positions(self):
        document = arrange(
            melody_midi([(p, 0, 1920) for p in E_MAJOR]),
            filename="emajor.mid",
            overrides_text=E_MAJOR_LOCKS,
        )
        xml_bytes = arrangement_json_to_musicxml(document)
        assert self._roundtrip_technical(xml_bytes) == [
            ("1", "0"),
            ("2", "0"),
            ("3", "1"),
            ("4", "2"),
            ("5", "2"),
            ("6", "0"),
        ]

    def test_musescore_preserves_a_locked_dyad(self):
        document = arrange(
            melody_midi([(55, 0, 960), (60, 0, 960)]),
            filename="s.mid",
            overrides_text=_locks(
                [
                    {"note_id": "track:0/channel:0/note:1", "string": 4, "fret": 5},
                    {"note_id": "track:0/channel:0/note:2", "string": 3, "fret": 5},
                ]
            ),
        )
        xml_bytes = arrangement_json_to_musicxml(document)
        assert self._roundtrip_technical(xml_bytes) == [("3", "5"), ("4", "5")]