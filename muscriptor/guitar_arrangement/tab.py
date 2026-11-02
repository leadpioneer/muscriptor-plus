"""Arrangement JSON → ASCII tabulature.

A diagnostic text tab for the arranged line: six string lines with the
user-facing numbering (string 1, the highest, on top), one 16th-note column
per grid position, the fret number printed at the note's onset and dashes
elsewhere. Bar lines fall every 4 beats — the document carries no tempo or
meter map, so a constant 4/4 grid at the source's ticks_per_beat is the only
honest approximation (documented, deterministic output).

This is a readable sanity check, not engraved notation: for score-quality
tab PDFs feed the converted MIDI to the existing sheets pipeline (MuseScore).
"""

from .errors import InvalidArrangementError

BEATS_PER_BAR = 4
STEPS_PER_BEAT = 4
PITCH_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Upper bound on the tab grid's width (one column per 16th note). A document
# with a bogus huge offset_ticks would otherwise allocate a grid with millions
# of columns; 100k columns is ~3.5 hours of 16ths at 120 BPM — far beyond any
# real arrangement, but bounded.
_MAX_TAB_STEPS = 100_000


def _pitch_name(pitch: int) -> str:
    return PITCH_NAMES[pitch % 12] + str(pitch // 12 - 1)


def _fret_label(fret: int) -> str:
    return str(fret) if fret >= 10 else f"-{fret}"


def arrangement_json_to_tab(document) -> str:
    """Render a schema-v2/v3 arrangement document as an ASCII tab text block."""
    if not isinstance(document, dict):
        raise InvalidArrangementError("arrangement document must be a JSON object")
    if document.get("schema_version") not in (2, 3):
        raise InvalidArrangementError(
            f"unsupported arrangement schema_version "
            f"{document.get('schema_version')!r}, expected 2 or 3"
        )
    source = document.get("source") or {}
    instrument = document.get("instrument") or {}
    notes = document.get("notes")
    if not isinstance(notes, list) or not notes:
        raise InvalidArrangementError("arrangement document has no notes")
    open_pitches = instrument.get("open_pitches")
    if (
        not isinstance(open_pitches, list)
        or not open_pitches
        or not all(
            isinstance(p, int) and not isinstance(p, bool) and 0 <= p <= 127
            for p in open_pitches
        )
    ):
        raise InvalidArrangementError(
            "arrangement document has no valid instrument strings"
        )
    tpb = source.get("ticks_per_beat")
    if not isinstance(tpb, int) or isinstance(tpb, bool) or tpb <= 0:
        raise InvalidArrangementError("'ticks_per_beat' must be a positive integer")

    step_ticks = tpb // STEPS_PER_BEAT
    if step_ticks == 0:
        raise InvalidArrangementError(
            f"ticks_per_beat {tpb} is too small for a 16th-note grid"
        )

    # Validate every note's mandatory int fields up front. offset_ticks was
    # previously read before any per-note validation, so a note missing it
    # surfaced as a KeyError (500) instead of a clean 400.
    offsets = []
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            raise InvalidArrangementError(f"note #{index} is not an object")
        offset = note.get("offset_ticks")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise InvalidArrangementError(
                f"note #{index}: 'offset_ticks' must be a non-negative integer"
            )
        offsets.append(offset)
    total_ticks = max(offsets)
    total_steps = total_ticks // step_ticks + 1
    if total_steps > _MAX_TAB_STEPS:
        raise InvalidArrangementError(
            f"arrangement is too long to render as tab: {total_steps} columns "
            f"exceeds the {_MAX_TAB_STEPS} column limit"
        )

    # grid[string][step] = fret label
    grid: dict[int, list[str]] = {
        s: ["--"] * total_steps for s in range(1, len(open_pitches) + 1)
    }
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            raise InvalidArrangementError(f"note #{index} is not an object")
        string = note.get("string")
        fret = note.get("fret")
        onset = note.get("onset_ticks")
        pitch = note.get("pitch")
        for name, value in (
            ("pitch", pitch),
            ("string", string),
            ("fret", fret),
            ("onset_ticks", onset),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidArrangementError(
                    f"note #{index}: {name!r} must be an integer"
                )
        if not 0 <= pitch <= 127:
            raise InvalidArrangementError(
                f"note #{index}: pitch {pitch} is outside 0..127"
            )
        if not 1 <= string <= len(open_pitches):
            raise InvalidArrangementError(
                f"note #{index}: string {string} is outside 1..{len(open_pitches)}"
            )
        if not 0 <= fret <= 99:
            raise InvalidArrangementError(
                f"note #{index}: fret {fret} does not fit the tab grid"
            )
        offset = offsets[index]
        if onset < 0 or onset > offset:
            raise InvalidArrangementError(
                f"note #{index}: onset_ticks {onset} is outside 0..{offset} "
                f"(its offset_ticks)"
            )
        step = onset // step_ticks
        grid[string][step] = _fret_label(fret)

    names = [_pitch_name(p) for p in open_pitches]
    name_width = max(len(n) for n in names)
    lines = []
    for string in range(1, len(open_pitches) + 1):
        cells: list[str] = []
        for step in range(total_steps):
            if step % (BEATS_PER_BAR * STEPS_PER_BEAT) == 0:
                cells.append("|-")
            cells.append(grid[string][step])
        prefix = f"{names[string - 1]:>{name_width}} "
        lines.append(prefix + "-".join(cells) + "-|")
    return "\n".join(lines)
