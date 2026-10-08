"""Versioned JSON serialization for guitar arrangements (schema v3).

The dict is built in a fixed key order and `to_json` never injects timestamps
or other dynamic values, so reruns on the same input serialize to byte-for-
byte identical JSON. No base64 MIDI is embedded — the output references the
source file by name only.

Schema v3 keeps the flat `notes` list (so locks and the existing UI stay
simple) and adds:
- `polyphony_analysis` — a deterministic description of the input;
- `events` — one entry per onset tick, the v3 solver's chord unit, with the
  chosen hand position, barres, shape cost and candidate counts;
- `source.tempo_events` / `source.time_signature_events` — the global meta
  maps (with `is_default` flags for synthesized fallbacks);
- `note.event_id` linking every note to its event;
- `note.finger` may be `null` when the finger annotation is incomplete.

The arranger always emits schema v3; converters accept v2 for legacy
monophonic documents (documented compatibility decision).
"""

import dataclasses
import json

from .errors import InvalidOverridesError
from .models import ArrangementSolution, FretPosition

SCHEMA_VERSION = 3
OVERRIDES_VERSION = 1


def _dropped_note_to_dict(dropped) -> dict:
    return {
        "note_id": dropped.note_id,
        "pitch": dropped.pitch,
        "onset_ticks": dropped.onset_ticks,
        "reason": dropped.reason,
    }


def _normalization_to_dict(normalization) -> dict:
    return {
        "target_tuning": normalization.target_tuning,
        "transposition_semitones": normalization.transposition_semitones,
        "source_low_pitch": normalization.source_low_pitch,
        "source_high_pitch": normalization.source_high_pitch,
        "dropped": [_dropped_note_to_dict(d) for d in normalization.dropped],
    }


def _event_to_dict(assigned_event, phrase_index: int) -> dict:
    """One onset event of the v3 document."""
    state = assigned_event.state
    event = assigned_event.event
    return {
        "id": f"event:{event.index}",
        "index": event.index,
        "phrase": phrase_index,
        "onset_ticks": state.onset_ticks,
        "note_ids": [note.id for note in event.notes],
        "hand_position": state.hand_position,
        "barres": [
            {
                "finger": barre.finger,
                "fret": barre.fret,
                "from_string": barre.from_string,
                "to_string": barre.to_string,
                "note_ids": list(barre.note_ids),
            }
            for barre in state.barres
        ],
        "shape_cost": round(state.shape_cost, 6),
        "finger_assignment_complete": state.finger_assignment_complete,
        "generated_candidates": assigned_event.generated_candidates,
        "pruned_candidates": assigned_event.pruned_candidates,
        # Honest about the search: when candidates were pruned, the optimum
        # is proven only among the retained ones.
        "optimal_within": "retained_candidates"
        if assigned_event.pruned_candidates
        else "all_candidates",
    }


def solution_to_dict(solution: ArrangementSolution) -> dict:
    """The arrangement JSON document (schema_version 3)."""
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
    position_changes = hand_travel = largest_shift = open_count = 0
    finger_usage: dict[str, int] = {
        "0": 0,
        "1": 0,
        "2": 0,
        "3": 0,
        "4": 0,
        "unknown": 0,
    }
    locked_notes = 0
    generated_total = 0
    pruned_total = 0
    for phrase in solution.phrases:
        states = [a.state for a in phrase.assigned]
        for previous, following in zip(states, states[1:]):
            shift = abs(following.hand_position - previous.hand_position)
            if shift:
                position_changes += 1
                hand_travel += shift
                largest_shift = max(largest_shift, shift)
            open_count += 1 if previous.is_open else 0
        if states:
            open_count += 1 if states[-1].is_open else 0
        for assigned_event in phrase.events:
            generated_total += assigned_event.generated_candidates
            pruned_total += assigned_event.pruned_candidates
            if not assigned_event.state.finger_assignment_complete:
                finger_usage["unknown"] += 1
        for assigned in phrase.assigned:
            if assigned.locked:
                locked_notes += 1
            finger = assigned.state.finger
            if finger is None:
                finger_usage["unknown"] += 1
            else:
                finger_usage[str(finger)] += 1

    def state_to_dict(state) -> dict:
        return {
            "string": state.position.string,
            "fret": state.position.fret,
            "hand_position": state.hand_position,
            "finger": state.finger,
        }

    def note_row(assigned, phrase_index: int, event_id: str) -> dict:
        return {
            "id": assigned.note.id,
            "event_id": event_id,
            "phrase": phrase_index,
            "pitch": assigned.note.pitch,
            "onset_ticks": assigned.note.onset_ticks,
            "offset_ticks": assigned.note.offset_ticks,
            "velocity": assigned.note.velocity,
            "string": assigned.state.position.string,
            "fret": assigned.state.position.fret,
            "hand_position": assigned.state.hand_position,
            "finger": assigned.state.finger,
            "locked": assigned.locked,
            "legal_positions": [
                {"string": pos.string, "fret": pos.fret}
                for pos in assigned.legal_positions
            ],
            "legal_fingerings": [
                state_to_dict(state) for state in assigned.legal_fingerings
            ],
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
            "tempo_events": [
                {
                    "tick": event.tick,
                    "tempo": event.tempo,
                    "is_default": event.is_default,
                }
                for event in solution.source.tempo_events
            ],
            "time_signature_events": [
                {
                    "tick": event.tick,
                    "numerator": event.numerator,
                    "denominator": event.denominator,
                    "clocks_per_click": event.clocks_per_click,
                    "notated_32nd_notes_per_beat": event.notated_32nd_notes_per_beat,
                    "is_default": event.is_default,
                }
                for event in solution.source.time_signature_events
            ],
        },
        "instrument": {
            "name": f"{solution.tuning.name}_guitar",
            "string_numbering": "1_is_highest",
            "open_pitches": list(solution.tuning.open_pitches),
            "max_fret": solution.config.max_fret,
            "max_hand_position": solution.config.hand_position_limit,
        },
        # How the part was fitted to the target tuning: a global
        # transposition and/or octave duplicates removed. `null` only when
        # normalization was explicitly disabled.
        "normalization": (
            _normalization_to_dict(solution.normalization)
            if solution.normalization is not None
            else None
        ),
        # Oversized onsets reduced to a playable subset (chord_overflow
        # "reduce"); empty when nothing was reduced.
        "chord_reductions": [
            {
                "onset_ticks": reduction.onset_ticks,
                "note_count": reduction.note_count,
                "dropped": [_dropped_note_to_dict(d) for d in reduction.dropped],
            }
            for reduction in solution.chord_reductions
        ],
        # Jazz chord symbols over the finished timeline (empty when detection
        # was disabled). Derived data: labels never change the notes.
        "chords": [
            {
                "tick": chord.tick,
                "label": chord.label,
                "root": chord.root,
                "kind": chord.kind,
                "bass": chord.bass,
            }
            for chord in solution.chords
        ],
        "polyphony_analysis": solution.polyphony.to_dict(),
        # What the melody reduction removed, when the caller chose a policy:
        # kept notes are untouched, this lists exactly what was dropped.
        "melody_reduction": (
            solution.melody_reduction.to_dict()
            if solution.melody_reduction is not None
            else {"policy": "off", "dropped_note_count": 0, "dropped": []}
        ),
        "config": {**dataclasses.asdict(solution.config)},
        "phrases": [
            {
                "index": p.index,
                "start_tick": p.start_tick,
                "end_tick": p.end_tick,
                "cost": round(p.cost, 6),
                "event_count": len(p.events),
                "fret_travel": p.fret_travel,
                "string_travel": p.string_travel,
            }
            for p in solution.phrases
        ],
        "events": [
            _event_to_dict(assigned_event, p.index)
            for p in solution.phrases
            for assigned_event in p.events
        ],
        "notes": [
            note_row(
                a,
                p.index,
                next(
                    f"event:{e.event.index}"
                    for e in p.events
                    if a.note in e.event.notes
                ),
            )
            for p in solution.phrases
            for a in p.assigned
        ],
        "metrics": {
            "note_count": sum(len(p.assigned) for p in solution.phrases),
            "phrase_count": len(solution.phrases),
            "event_count": sum(len(p.events) for p in solution.phrases),
            "total_cost": round(sum(p.cost for p in solution.phrases), 6),
            "position_change_count": position_changes,
            "total_hand_position_travel": hand_travel,
            "largest_hand_position_shift": largest_shift,
            "open_string_count": open_count,
            "finger_usage": finger_usage,
            # Candidate accounting: when pruned > 0, the optimum is proven
            # among the retained candidates only (never silently claimed
            # over discarded states).
            "generated_candidates": generated_total,
            "pruned_candidates": pruned_total,
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
            f"unsupported overrides version {version!r} (expected {OVERRIDES_VERSION})"
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
            raise InvalidOverridesError(f"lock for {note_id!r}: fret must be >= 0")
        if note_id in positions:
            raise InvalidOverridesError(f"duplicate lock for note id {note_id!r}")
        positions[note_id] = FretPosition(string=string, fret=fret)
    return positions


def _is_int(value) -> bool:
    # bool is an int subclass in Python; exclude it explicitly.
    return isinstance(value, int) and not isinstance(value, bool)
