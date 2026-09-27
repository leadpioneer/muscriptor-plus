"""Versioned JSON serialization for guitar arrangements (schema v2).

The dict is built in a fixed key order and `to_json` never injects timestamps
or other dynamic values, so reruns on the same input serialize to byte-for-
byte identical JSON. No base64 MIDI is embedded — the output references the
source file by name only.

Schema v2 adds per-note `hand_position`/`finger` (the solver state is a full
left-hand fingering, not just a spot on the neck) and a `legal_fingerings`
list next to the v1 `legal_positions` (which keeps only string/fret). Fret
metrics stay for diagnostics but no longer stand in for hand movement.
"""

import json
from dataclasses import asdict

from .errors import InvalidOverridesError
from .models import ArrangementSolution, FingeringState, FretPosition

SCHEMA_VERSION = 2
OVERRIDES_VERSION = 1


def _hand_metrics(phrases):
    """Position changes, hand travel, largest shift, open-string count."""
    changes = travel = largest = open_count = 0
    for phrase in phrases:
        states = [a.state for a in phrase.assigned]
        for previous, following in zip(states, states[1:]):
            shift = abs(following.hand_position - previous.hand_position)
            if shift:
                changes += 1
                travel += shift
                largest = max(largest, shift)
            open_count += 1 if previous.is_open else 0
        open_count += 1 if states[-1].is_open else 0
    return changes, travel, largest, open_count


def solution_to_dict(solution: ArrangementSolution) -> dict:
    """The arrangement JSON document (schema_version 2)."""
    transitions_fret = [
        abs(b.state.position.fret - a.state.position.fret)
        for p in solution.phrases
        for a, b in zip(p.assigned, p.assigned[1:])
    ]
    transitions_string = [
        abs(b.state.position.string - a.state.position.string)
        for p in solution.phrases
        for a, b in zip(p.assigned, p.assigned[1:])
    ]
    position_changes, hand_travel, largest_shift, open_count = _hand_metrics(
        solution.phrases
    )
    finger_usage: dict[str, int] = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0}
    for phrase in solution.phrases:
        for assigned in phrase.assigned:
            finger_usage[str(assigned.state.finger)] += 1
    locked_notes = sum(
        1 for p in solution.phrases for a in p.assigned if a.locked
    )

    def state_to_dict(state: FingeringState) -> dict:
        return {
            "string": state.position.string,
            "fret": state.position.fret,
            "hand_position": state.hand_position,
            "finger": state.finger,
        }

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
            "max_hand_position": solution.config.hand_position_limit,
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
                "string": a.state.position.string,
                "fret": a.state.position.fret,
                "hand_position": a.state.hand_position,
                "finger": a.state.finger,
                "locked": a.locked,
                "legal_positions": [
                    {"string": pos.string, "fret": pos.fret}
                    for pos in a.legal_positions
                ],
                "legal_fingerings": [
                    state_to_dict(state) for state in a.legal_fingerings
                ],
            }
            for p in solution.phrases
            for a in p.assigned
        ],
        "metrics": {
            "note_count": sum(len(p.assigned) for p in solution.phrases),
            "phrase_count": len(solution.phrases),
            "total_cost": sum(p.cost for p in solution.phrases),
            "position_change_count": position_changes,
            "total_hand_position_travel": hand_travel,
            "largest_hand_position_shift": largest_shift,
            "open_string_count": open_count,
            "finger_usage": finger_usage,
            # Fret/string movement is a diagnostic: it is NOT hand movement.
            "total_fret_travel": sum(p.fret_travel for p in solution.phrases),
            "total_string_travel": sum(p.string_travel for p in solution.phrases),
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
