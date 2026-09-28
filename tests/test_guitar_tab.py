"""Tests for the ASCII tabulature renderer (tab.py)."""

import pytest

from muscriptor.guitar_arrangement import InvalidArrangementError, arrangement_json_to_tab

BASE = {
    "schema_version": 2,
    "source": {"filename": "s.mid", "ticks_per_beat": 480, "program": 24},
    "instrument": {
        "open_pitches": [64, 59, 55, 50, 45, 40],
        "string_numbering": "1_is_highest",
    },
    "notes": [
        {"pitch": 64, "string": 1, "fret": 0, "onset_ticks": 0, "offset_ticks": 480},
        {"pitch": 67, "string": 1, "fret": 3, "onset_ticks": 480, "offset_ticks": 960},
        {"pitch": 43, "string": 5, "fret": 10, "onset_ticks": 960, "offset_ticks": 1920},
    ],
}


def test_string_1_is_on_top_and_frets_are_in_grid_cells():
    tab = arrangement_json_to_tab(BASE)
    lines = tab.splitlines()
    assert len(lines) == 6
    assert lines[0].startswith("E4 ")
    assert lines[5].startswith("E2 ")
    # Frets land in the right string lines.
    assert "0" in lines[0].split("|")[1]
    assert "3" in lines[0]
    assert "10" in lines[4]
    # Bar line every 4 beats (1920 ticks) — grid position 16 is a new bar.
    for line in lines:
        assert "|-" in line


def test_output_is_deterministic():
    assert arrangement_json_to_tab(BASE) == arrangement_json_to_tab(BASE)


def test_e_major_renders_as_a_vertical_chord():
    """Golden test: all six notes of one onset share one time column."""
    from muscriptor.guitar_arrangement import arrange
    from .midi_build import melody_midi

    document = arrange(
        melody_midi([(p, 0, 1920) for p in (40, 47, 52, 56, 59, 64)]),
        filename="emajor.mid",
    )
    tab = arrangement_json_to_tab(document)
    lines = tab.splitlines()
    assert len(lines) == 6
    # String 6 (bottom line) fret 0, string 5 fret 2, string 4 fret 2,
    # string 3 fret 1, strings 2 and 1 fret 0 — one vertical stack.
    expected = {6: "0", 5: "2", 4: "2", 3: "1", 2: "0", 1: "0"}
    for number, fret in expected.items():
        line = lines[number - 1]
        # The fret label sits in the first grid column (right after the bar).
        cell = line.split("|")[1]
        assert fret in cell, f"string {number}: {cell!r}"
    # The chord occupies a single column: no other fret label anywhere.
    for number, fret in expected.items():
        body = lines[number - 1].split("|", 1)[1]
        assert body.count(fret) >= 1


def test_tenth_fret_occupies_two_characters():
    tab = arrangement_json_to_tab(BASE)
    assert "-10" in tab  # two-digit fret inside the fixed-width cell


def test_invalid_documents_are_rejected():
    with pytest.raises(InvalidArrangementError):
        arrangement_json_to_tab({"schema_version": 1})
    with pytest.raises(InvalidArrangementError):
        arrangement_json_to_tab({**BASE, "notes": []})
    bad_string = {
        **BASE,
        "notes": [{**BASE["notes"][0], "string": 9}],
    }
    with pytest.raises(InvalidArrangementError):
        arrangement_json_to_tab(bad_string)
