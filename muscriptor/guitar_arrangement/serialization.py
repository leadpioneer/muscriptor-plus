"""Versioned JSON serialization for guitar arrangements.

The dict is built in a fixed key order and `to_json` never injects timestamps
or other dynamic values, so reruns on the same input serialize to byte-for-
byte identical JSON. No base64 MIDI is embedded — the output references the
source file by name only.
"""

import json
from dataclasses import asdict

from .errors import InvalidOverridesError
from .models import ArrangementSolution, FretPosition

SCHEMA_VERSION = 1
OVERRIDES_VERSION = 1


def solution_to_dict(solution: ArrangementSolution) -> dict:
    """The arrangement JSON document (schema_version 1)."""
    metrics_fret_travel = sum(p.fret_travel for p in solution.phrases)
    metrics_string_travel = sum(p.string_travel for p in solution.phrases)
    transitions_fret = [
        abs(b.position.fret - a.position.fret)
        for p in solution.phrases
        for a, b in zip(p.assigned, p.assigned[1:])
    ]
    transitions_string = [
        abs(b.position.string - a.position.string)
        for p in solution.phrases
        for a, b in zip(p.assigned, p.assigned[1:])
    ]
    locked_notes = sum(
        1 for p in solution.phrases for a in p.assigned if a.locked
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "filename": solution.source.filename,
            "ticks_per_beat": solution.source.ticks_per_beat,
            "track_index": solution.source.track_index,
            "track_name": solution.source.track_name,
            "channel": solution.source.channel,
            "program": solution.source.program,
        },
        "instrument": {
            "name": f"{solution.tuning.name}_guitar",
            "string_numbering": "1_is_highest",
            "open_pitches": list(solution.tuning.open_pitches),
            "max_fret": solution.config.max_fret,
        },
        "config": {**asdict(solution.config)},
        "phrases": [
            {
                "index": p.index,
                "start_tick": p.start_tick,
                "end_tick": p.end_tick,
                "cost": p.cost,
                "fret_travel": p.fret_travel,
                "string_travel": p.string_travel,
            }
            for p in solution.phrases
        ],
        "notes": [
            {
                "id": a.note.id,
                "phrase": p.index,
                "pitch": a.note.pitch,
                "onset_ticks": a.note.onset_ticks,
                "offset_ticks": a.note.offset_ticks,
                "velocity": a.note.velocity,
                "string": a.position.string,
                "fret": a.position.fret,
                "locked": a.locked,
                "legal_positions": [
                    {"string": pos.string, "fret": pos.fret}
                    for pos in a.legal_positions
                ],
            }
            for p in solution.phrases
            for a in p.assigned
        ],
        "metrics": {
            "note_count": sum(len(p.assigned) for p in solution.phrases),
            "phrase_count": len(solution.phrases),
            "total_cost": sum(p.cost for p in solution.phrases),
            "total_fret_travel": metrics_fret_travel,
            "total_string_travel": metrics_string_travel,
            "largest_fret_transition": max(transitions_fret, default=0),
            "largest_string_transition": max(transitions_string, default=0),
            "locked_notes": locked_notes,
        },
    }


def to_json(solution: ArrangementSolution) -> str:
    """Deterministic pretty-printed JSON text of an arrangement."""
    return json.dumps(solution_to_dict(solution), indent=2, ensure_ascii=False)


def parse_overrides(text: str) -> dict[str, FretPosition]:
    """Parse an overrides document: `{"version": 1, "locks": [...]}`.

    Only syntax and shape are validated here; whether a lock makes musical
    sense for the input is checked later, against the parsed notes.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError as e:
        raise InvalidOverridesError(f"overrides is not valid JSON: {e}") from e
    if not isinstance(document, dict):
        raise InvalidOverridesError("overrides must be a JSON object")
    version = document.get("version")
    if version != OVERRIDES_VERSION:
        raise InvalidOverridesError(
            f"unsupported overrides version {version!r} "
            f"(expected {OVERRIDES_VERSION})"
        )
    locks = document.get("locks")
    if not isinstance(locks, list):
        raise InvalidOverridesError("overrides.locks must be a list")
    positions: dict[str, FretPosition] = {}
    for entry in locks:
        if not isinstance(entry, dict):
            raise InvalidOverridesError("each lock must be a JSON object")
        note_id = entry.get("note_id")
        string = entry.get("string")
        fret = entry.get("fret")
        if not isinstance(note_id, str) or not note_id:
            raise InvalidOverridesError("each lock needs a non-empty note_id")
        if not _is_int(string) or not _is_int(fret):
            raise InvalidOverridesError(
                f"lock for {note_id!r} needs integer 'string' and 'fret'"
            )
        if string < 1:
            raise InvalidOverridesError(
                f"lock for {note_id!r}: string must be >= 1 (1 is highest)"
            )
        if fret < 0:
            raise InvalidOverridesError(
                f"lock for {note_id!r}: fret must be >= 0"
            )
        if note_id in positions:
            raise InvalidOverridesError(
                f"duplicate lock for note id {note_id!r}"
            )
        positions[note_id] = FretPosition(string=string, fret=fret)
    return positions


def _is_int(value) -> bool:
    # bool is an int subclass in Python; exclude it explicitly.
    return isinstance(value, int) and not isinstance(value, bool)
