"""Arrangement JSON → MIDI converter.

The arrangement document never changes pitch, onset, offset or velocity — the
fingering solver only chooses string/fret — so converting it back to a MIDI
file reproduces exactly what the pipeline did to the source track: the same
notes (all of them for schema v3, or minus the melody reduction's drops for
legacy v2 documents, whose `melody_reduction` block says what). The output is
a type-0 file with one note-bearing track on channel 0, carrying the source
program; byte-stable across runs (sorted events, no timestamps).

**MIDI is not the fingering storage format**: it carries pitches, timings and
velocities, but never the chosen string/fret — an engraved tab built from this
MIDI alone would be MuseScore's own guess, not the arrangement. Use the
MusicXML export (`muscriptor.guitar_arrangement.musicxml`) when the chosen
fingering must survive.

Tempo and time-signature maps are global meta events carried by the schema-v3
`source` block; they are written back verbatim. A legacy v2 document has no
maps, so none are invented — consumers pick their own tempo, as before.

Retrigger rule: when one note's offset coincides with the next note's onset
(same pitch, same tick), the note_off is written BEFORE the new note_on, so
the second note does not get swallowed by the first one's release.
"""

import io

import mido
from mido import MetaMessage, Message

from .errors import InvalidArrangementError, UnsupportedArrangementError

SUPPORTED_SCHEMA_VERSIONS = (2, 3)


def _require(document: dict, key: str):
    value = document.get(key)
    if value is None:
        raise InvalidArrangementError(f"arrangement document is missing {key!r}")
    return value


def _positive_int(value, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InvalidArrangementError(f"{what} must be a positive integer")
    return value


def parse_arrangement_document(document) -> dict:
    """Validate the bare minimum needed to rebuild notes from a document."""
    if not isinstance(document, dict):
        raise InvalidArrangementError("arrangement document must be a JSON object")
    if document.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedArrangementError(
            f"unsupported arrangement schema_version "
            f"{document.get('schema_version')!r}, expected one of "
            f"{SUPPORTED_SCHEMA_VERSIONS}"
        )
    source = _require(document, "source")
    if not isinstance(source, dict):
        raise InvalidArrangementError("arrangement 'source' must be an object")
    notes = _require(document, "notes")
    if not isinstance(notes, list) or not notes:
        raise InvalidArrangementError("arrangement document has no notes")
    return document


def _iter_note_events(notes: list):
    """Yield (sort_key, message) pairs, validating every note along the way.

    Sort keys: (tick, kind) with kind 0 for note_off and 1 for note_on —
    a retrigger (note_off and note_on at the same tick) writes the release
    first, so the re-struck note is not cut short.
    """
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            raise InvalidArrangementError(f"note #{index} is not an object")
        pitch = note.get("pitch")
        onset = note.get("onset_ticks")
        offset = note.get("offset_ticks")
        velocity = note.get("velocity")
        for name, value in (
            ("pitch", pitch),
            ("onset_ticks", onset),
            ("offset_ticks", offset),
            ("velocity", velocity),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise InvalidArrangementError(
                    f"note #{index}: {name!r} must be an integer"
                )
        if not 0 <= pitch <= 127:
            raise InvalidArrangementError(
                f"note #{index}: pitch {pitch} is outside 0..127"
            )
        if not 1 <= velocity <= 127:
            raise InvalidArrangementError(
                f"note #{index}: velocity {velocity} is outside 1..127"
            )
        if offset <= onset:
            raise InvalidArrangementError(
                f"note #{index}: offset_ticks {offset} is not after onset_ticks {onset}"
            )
        yield (onset, 1, Message("note_on", note=pitch, velocity=velocity, time=0))
        yield (offset, 0, Message("note_off", note=pitch, velocity=0, time=0))


def _meta_events(source: dict, schema_version: int):
    """Yield (sort_key, message) pairs for the global meta maps.

    Schema v3 carries them in `source`; a legacy v2 document has none and
    none are invented. Kinds keep them ahead of notes at tick 0.
    """
    if schema_version < 3:
        return
    for event in source.get("tempo_events") or []:
        yield (
            event.get("tick", 0),
            0,
            0,
            MetaMessage("set_tempo", tempo=event["tempo"], time=0),
        )
    for event in source.get("time_signature_events") or []:
        yield (
            event.get("tick", 0),
            0,
            1,
            MetaMessage(
                "time_signature",
                numerator=event["numerator"],
                denominator=event["denominator"],
                clocks_per_click=event.get("clocks_per_click", 24),
                notated_32nd_notes_per_beat=event.get("notated_32nd_notes_per_beat", 8),
                time=0,
            ),
        )


def arrangement_json_to_midi(document) -> bytes:
    """Serialize a schema-v2/v3 arrangement document back into a MIDI file."""
    document = parse_arrangement_document(document)
    source = document["source"]
    schema_version = document["schema_version"]
    ticks_per_beat = _positive_int(source.get("ticks_per_beat"), "ticks_per_beat")
    program = source.get("program")
    if program is not None and (
        not isinstance(program, int) or isinstance(program, bool)
    ):
        raise InvalidArrangementError("'program' must be an integer or null")
    track_name = source.get("track_name") or "guitar arrangement"

    midi = mido.MidiFile(type=0, ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(MetaMessage("track_name", name=str(track_name), time=0))
    if program is not None:
        track.append(Message("program_change", program=program, channel=0, time=0))

    events = sorted(_iter_note_events(document["notes"]), key=lambda e: (e[0], e[1]))
    meta_events = sorted(_meta_events(source, schema_version), key=lambda e: e[:3])
    merged = sorted(
        [(tick, kind, 2, message) for tick, kind, message in events]
        + list(meta_events),
        key=lambda e: (e[0], e[1], e[2]),
    )
    last = 0
    for absolute_tick, _, _, message in merged:
        message.time = absolute_tick - last
        last = absolute_tick
        track.append(message)
    track.append(MetaMessage("end_of_track", time=0))

    buf = io.BytesIO()
    midi.save(file=buf)
    return buf.getvalue()
