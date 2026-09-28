"""Fingering-preserving MusicXML export for guitar arrangements.

Unlike MIDI (which carries only pitches and timings), MusicXML records the
chosen string/fret of every note:

    <notations><technical><string>1</string><fret>0</fret></technical></notations>

so an engraver (MuseScore) can render the exact tab the arranger chose —
user locks included — instead of re-guessing a tab from pitches.

Design decisions (documented, deterministic):
- `divisions` == the source `ticks_per_beat`, so `<duration>` values are the
  original ticks verbatim; nothing is requantized.
- Simultaneous-onset notes form a chord unit (first note plain, the rest
  carry `<chord/>`). Units are colored into MusicXML voices with a greedy
  interval graph coloring — asynchronously overlapping notes (ringing bass
  into the next chord) get separate voices and keep their full durations.
  Nothing is shortened into a sequence.
- Units crossing a barline are split into tied segments; onset/offset ticks
  are preserved by construction.
- Measures come from the document's time-signature map; tempo changes are
  written as `<sound tempo="…">` directions.
- The part is a 6-line tablature staff with explicit `staff-tuning`.
- Standard `xml.etree.ElementTree` only; output is byte-stable.

Legacy schema-v2 documents (no events/tempo maps) are exported too: chords
are derived from shared onsets, and no tempo/meter is invented beyond the
marked defaults.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .errors import InvalidArrangementError, UnsupportedArrangementError

SUPPORTED_SCHEMA_VERSIONS = (2, 3)
PITCH_STEPS = ("C", "D", "E", "F", "G", "A", "B")


def _pitch_to_step_alter_octave(pitch: int) -> tuple[str, int, int]:
    """MIDI pitch → (step, alter, octave) with sharps (C4 = MIDI 60)."""
    octave = pitch // 12 - 1
    index = pitch % 12
    # Chromatic letters: C C# D D# E F F# G G# A A# B
    letters = "CCDDEFFGGAAB"
    step = letters[index]
    alter = 1 if letters[index - 1] == step and index != 0 else 0
    return step, alter, octave


# Note-type names by their length in quarter notes (divisions units / tpb).
# "breve" and "whole" are deliberately absent: a whole rest means "full
# measure" to engravers, and MuseScore crashes when its duration disagrees
# with the measure (unquantized input fills a measure partially). Long
# notes/rests simply get a "half" shape while <duration> stays verbatim.
_TYPE_NAMES = (
    ("half", 2.0),
    ("quarter", 1.0),
    ("eighth", 0.5),
    ("16th", 0.25),
    ("32nd", 0.125),
    ("64th", 0.0625),
    ("128th", 0.03125),
)


def _note_type(duration: int, divisions: int) -> tuple[str, int]:
    """Nearest notated type (name, dot count) for a duration in ticks.

    Real transcription output is unquantized (347-tick notes), and MuseScore
    crashes importing a note without `<type>` whose duration has no dyadic
    form. Empirically it also crashes on dotted types whose dotted value
    does not match the actual duration, so dots are never emitted: the type
    is the nearest plain dyadic shape, while the written `<duration>` stays
    verbatim.
    """
    quarters = duration / divisions
    best: tuple[str, int] | None = None
    best_error = float("inf")
    for name, base in _TYPE_NAMES:
        error = abs(base - quarters)
        if error < best_error - 1e-9:
            best_error = error
            best = (name, 0)
    assert best is not None
    return best


@dataclass(frozen=True)
class _Unit:
    """One chord unit: notes sharing an onset AND offset, in one voice."""

    onset: int
    offset: int  # == every member's offset (members are duration-equal)
    notes: tuple[dict, ...]  # event order (pitch descending, then id)
    voice: int


def parse_document(document) -> tuple[dict, list[dict]]:
    """Validate and return (document, notes sorted by (onset, -pitch, id))."""
    if not isinstance(document, dict):
        raise InvalidArrangementError("arrangement document must be a JSON object")
    if document.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedArrangementError(
            f"unsupported arrangement schema_version "
            f"{document.get('schema_version')!r}, expected one of "
            f"{SUPPORTED_SCHEMA_VERSIONS}"
        )
    source = document.get("source")
    if not isinstance(source, dict):
        raise InvalidArrangementError("arrangement document has no source")
    notes = document.get("notes")
    if not isinstance(notes, list) or not notes:
        raise InvalidArrangementError("arrangement document has no notes")
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            raise InvalidArrangementError(f"note #{index} is not an object")
        for key in ("pitch", "onset_ticks", "offset_ticks", "velocity"):
            value = note.get(key)
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidArrangementError(
                    f"note #{index}: {key!r} must be an integer"
                )
        if not isinstance(note.get("string"), int) or not isinstance(
            note.get("fret"), int
        ):
            raise InvalidArrangementError(
                f"note #{index}: string/fret are required for MusicXML"
            )
    ordered = sorted(
        notes, key=lambda n: (n["onset_ticks"], -n["pitch"], n.get("id", ""))
    )
    return document, ordered


def _color_units(notes: list[dict]) -> list[_Unit]:
    """Group notes into chord units, color units into voices.

    A unit is a group of notes sharing the SAME onset AND offset — every
    member of one `<chord/>` therefore has an identical duration, which is
    what engravers require for their measure accounting. Members of one
    onset event with different durations land in different units; since
    those units overlap, the coloring assigns them different voices and
    every note keeps its exact duration.
    """
    by_key: dict[tuple[int, int], list[dict]] = {}
    for note in notes:
        by_key.setdefault(
            (note["onset_ticks"], note["offset_ticks"]), []
        ).append(note)
    units: list[_Unit] = []
    voice_ends: list[int] = []  # voice v (index v-1) is busy until this tick
    for onset, offset in sorted(by_key):
        members = by_key[(onset, offset)]
        voice = next(
            (v for v, end in enumerate(voice_ends) if end <= onset),
            None,
        )
        if voice is None:
            voice_ends.append(offset)
            voice = len(voice_ends) - 1
        else:
            voice_ends[voice] = offset
        units.append(
            _Unit(
                onset=onset,
                offset=offset,
                notes=tuple(members),
                voice=voice + 1,
            )
        )
    return units


def _measure_boundaries(source: dict, ticks_per_beat: int, total_ticks: int):
    """Measure (start, numerator, denominator, length) tuples from the meter
    map. The LAST measure is padded to a full bar so every measure balances
    (MuseScore flags short final measures as incomplete)."""
    signatures = sorted(
        source.get("time_signature_events") or [],
        key=lambda e: e.get("tick", 0),
    )
    if not signatures or signatures[0].get("tick", 0) > 0:
        signatures = [
            {"tick": 0, "numerator": 4, "denominator": 4},
            *signatures,
        ]
    boundaries = []
    current = 0
    signature_index = 0
    while current < total_ticks:
        while (
            signature_index + 1 < len(signatures)
            and signatures[signature_index + 1].get("tick", 0) <= current
        ):
            signature_index += 1
        signature = signatures[signature_index]
        numerator = signature.get("numerator", 4)
        denominator = signature.get("denominator", 4)
        bar_ticks = max(1, int(round(numerator * 4 / denominator * ticks_per_beat)))
        boundaries.append((current, numerator, denominator, bar_ticks))
        current += bar_ticks
    return boundaries


def _add_note(
    parent,
    member,
    duration,
    voice,
    chord,
    tie_start,
    tie_stop,
    divisions,
):
    note = ET.SubElement(parent, "note")
    if chord:
        ET.SubElement(note, "chord")
    pitch = ET.SubElement(note, "pitch")
    step, alter, octave = _pitch_to_step_alter_octave(member["pitch"])
    ET.SubElement(pitch, "step").text = step
    if alter:
        ET.SubElement(pitch, "alter").text = str(alter)
    ET.SubElement(pitch, "octave").text = str(octave)
    ET.SubElement(note, "duration").text = str(duration)
    if tie_start:
        ET.SubElement(note, "tie", {"type": "start"})
    if tie_stop:
        ET.SubElement(note, "tie", {"type": "stop"})
    ET.SubElement(note, "voice").text = str(voice)
    # An explicit <type> is mandatory in practice: MuseScore crashes on
    # notes whose duration has no dyadic form (unquantized MIDI) when it
    # has to guess. The duration itself stays verbatim.
    type_name, dots = _note_type(duration, divisions)
    ET.SubElement(note, "type").text = type_name
    for _ in range(dots):
        ET.SubElement(note, "dot")
    notations = ET.SubElement(note, "notations")
    if tie_start:
        ET.SubElement(notations, "tied", {"type": "start"})
    if tie_stop:
        ET.SubElement(notations, "tied", {"type": "stop"})
    technical = ET.SubElement(notations, "technical")
    if member.get("finger") is not None:
        ET.SubElement(technical, "fingering").text = str(member["finger"])
    ET.SubElement(technical, "string").text = str(member["string"])
    ET.SubElement(technical, "fret").text = str(member["fret"])


def _add_rest(parent, duration, voice, divisions, full_measure=False):
    note = ET.SubElement(parent, "note")
    rest = ET.SubElement(note, "rest")
    if full_measure:
        # A full-measure rest: the engraver fills the bar itself; no <type>.
        rest.set("measure", "yes")
        ET.SubElement(note, "duration").text = str(duration)
        ET.SubElement(note, "voice").text = str(voice)
        return
    ET.SubElement(note, "duration").text = str(duration)
    ET.SubElement(note, "voice").text = str(voice)
    type_name, dots = _note_type(duration, divisions)
    ET.SubElement(note, "type").text = type_name
    for _ in range(dots):
        ET.SubElement(note, "dot")


def _add_measure_content(
    measure,
    measure_number,
    measure_start,
    measure_end,
    numerator,
    denominator,
    previous_meter,
    units,
    tempos,
    ticks_per_beat,
    open_pitches,
):
    """Attributes, tempo directions and all voices of one measure."""
    needs_attributes = measure_number == 1
    if (numerator, denominator) != previous_meter:
        needs_attributes = True
    if needs_attributes:
        attributes = ET.SubElement(measure, "attributes")
        if measure_number == 1:
            ET.SubElement(attributes, "divisions").text = str(ticks_per_beat)
            key = ET.SubElement(attributes, "key")
            ET.SubElement(key, "fifths").text = "0"
        time = ET.SubElement(attributes, "time")
        ET.SubElement(time, "beats").text = str(numerator)
        ET.SubElement(time, "beat-type").text = str(denominator)
        if measure_number == 1:
            clef = ET.SubElement(attributes, "clef")
            ET.SubElement(clef, "sign").text = "TAB"
            ET.SubElement(clef, "line").text = "5"
            staff_details = ET.SubElement(attributes, "staff-details")
            ET.SubElement(staff_details, "staff-lines").text = str(
                len(open_pitches) or 6
            )
            # MusicXML staff-tuning line 1 is the LOWEST line, i.e. the
            # lowest-sounding string — reverse of our 1-is-highest numbering.
            for line, open_pitch in enumerate(reversed(open_pitches), start=1):
                step, alter, octave = _pitch_to_step_alter_octave(open_pitch)
                tuning = ET.SubElement(
                    staff_details, "staff-tuning", {"line": str(line)}
                )
                ET.SubElement(tuning, "tuning-step").text = step
                if alter:
                    ET.SubElement(tuning, "tuning-alter").text = str(alter)
                ET.SubElement(tuning, "tuning-octave").text = str(octave)

    last_tempo_emitted: tuple[int, int] | None = None
    for tempo in tempos:
        tick = tempo.get("tick", 0)
        if not measure_start <= tick < measure_end:
            continue
        if tempo.get("is_default"):
            continue
        # The same (tick, tempo) pair can appear twice in a source file —
        # one direction is enough.
        key = (tick, tempo["tempo"])
        if key == last_tempo_emitted:
            continue
        last_tempo_emitted = key
        bpm = round(60_000_000 / tempo["tempo"], 2)
        direction = ET.SubElement(measure, "direction", {"placement": "above"})
        direction_type = ET.SubElement(direction, "direction-type")
        metronome = ET.SubElement(direction_type, "metronome")
        ET.SubElement(metronome, "beat-unit").text = "quarter"
        ET.SubElement(metronome, "per-minute").text = str(bpm)
        ET.SubElement(direction, "sound", {"tempo": str(bpm)})

    measure_units = [
        unit
        for unit in units
        if unit.onset < measure_end and unit.offset > measure_start
    ]
    voices = sorted({unit.voice for unit in measure_units})
    # MusicXML measure cursor: notes advance it by their duration ONCE per
    # chord (chord members share the onset), backup rewinds it. The cursor
    # is tracked explicitly here — never summed from the DOM — so the
    # written durations add up to exactly one measure per voice.
    previous_written = 0
    for voice_index, voice in enumerate(voices):
        if voice_index > 0 and previous_written > 0:
            ET.SubElement(measure, "backup").text = str(previous_written)
        cursor = measure_start
        for unit in sorted(
            (u for u in measure_units if u.voice == voice),
            key=lambda u: u.onset,
        ):
            segment_onset = max(unit.onset, measure_start)
            members = [
                m
                for m in unit.notes
                if m["offset_ticks"] > measure_start
                # Segment must be inside this measure:
                and min(m["offset_ticks"], measure_end) > segment_onset
            ]
            if not members:
                continue
            if segment_onset > cursor:
                _add_rest(
                    measure,
                    segment_onset - cursor,
                    voice,
                    ticks_per_beat,
                    full_measure=(
                        cursor == measure_start and segment_onset == measure_end
                    ),
                )
                cursor = segment_onset
            # Every member of one unit shares onset and offset, so every
            # chord member gets the same duration and the chord advances
            # the cursor exactly once.
            duration = min(members[0]["offset_ticks"], measure_end) - segment_onset
            for member_index, member in enumerate(members):
                _add_note(
                    measure,
                    member,
                    duration,
                    voice,
                    chord=member_index > 0,
                    tie_start=member["offset_ticks"] > measure_end,
                    tie_stop=unit.onset < measure_start,
                    divisions=ticks_per_beat,
                )
            cursor = max(cursor, segment_onset + duration)
        if cursor < measure_end:
            _add_rest(
                measure,
                measure_end - cursor,
                voice,
                ticks_per_beat,
                full_measure=(cursor == measure_start),
            )
            cursor = measure_end
        previous_written = cursor - measure_start


def arrangement_json_to_musicxml(document) -> bytes:
    """Serialize a schema-v2/v3 arrangement into fingering-preserving
    MusicXML (bytes, UTF-8, deterministic)."""
    document, notes = parse_document(document)
    source = document["source"]
    ticks_per_beat = source.get("ticks_per_beat")
    if not isinstance(ticks_per_beat, int) or ticks_per_beat <= 0:
        raise InvalidArrangementError("'ticks_per_beat' must be a positive integer")
    open_pitches = (document.get("instrument") or {}).get("open_pitches") or []
    total_ticks = max(note["offset_ticks"] for note in notes)
    units = _color_units(notes)
    boundaries = _measure_boundaries(source, ticks_per_beat, total_ticks)
    tempos = sorted(source.get("tempo_events") or [], key=lambda e: e.get("tick", 0))

    root = ET.Element("score-partwise", {"version": "4.0"})
    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", {"id": "P1"})
    ET.SubElement(score_part, "part-name").text = "Guitar"
    part = ET.SubElement(root, "part", {"id": "P1"})

    for measure_number, (measure_start, numerator, denominator, bar_ticks) in enumerate(
        boundaries, start=1
    ):
        measure_end = (
            boundaries[measure_number][0]
            if measure_number < len(boundaries)
            else measure_start + bar_ticks
        )
        previous_meter = (
            boundaries[measure_number - 2][1:3] if measure_number >= 2 else None
        )
        measure = ET.SubElement(part, "measure", {"number": str(measure_number)})
        _add_measure_content(
            measure,
            measure_number,
            measure_start,
            measure_end,
            numerator,
            denominator,
            previous_meter,
            units,
            tempos,
            ticks_per_beat,
            open_pitches,
        )

    ET.indent(root, space="  ")
    return ET.tostring(root, xml_declaration=True, encoding="UTF-8")