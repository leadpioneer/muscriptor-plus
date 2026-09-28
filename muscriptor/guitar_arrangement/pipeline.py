"""End-to-end arrangement pipeline: MIDI bytes → arrangement dict.

The single entry point shared by the CLI and the HTTP endpoint. Reads nothing
from disk itself (bytes in, dict out) and knows nothing about FastAPI or
Typer, so the whole flow stays testable without either.
"""

import dataclasses

from .errors import InvalidMelodyPolicyError, InvalidOverridesError
from .events import analyze_polyphony, group_into_events
from .fretboard import resolve_tuning
from .melody import reduce_to_melody
from .midi_input import parse_midi, select_notes
from .models import ArrangementSolution, FretPosition, SolverConfig, SourceInfo
from .phrases import split_event_phrases
from .serialization import parse_overrides, solution_to_dict
from .solver import solve_event_phrases


def arrange(
    midi_data: bytes,
    *,
    filename: str,
    track: int | None = None,
    channel: int | None = None,
    tuning_name: str = "standard",
    max_fret: int = 24,
    phrase_gap_beats: float = 1.0,
    melody_policy: str = "off",
    overrides_text: str | None = None,
    config: SolverConfig | None = None,
) -> dict:
    """Arrange and serialize in one call (the HTTP endpoint's entry point)."""
    return solution_to_dict(
        arrange_solution(
            midi_data,
            filename=filename,
            track=track,
            channel=channel,
            tuning_name=tuning_name,
            max_fret=max_fret,
            phrase_gap_beats=phrase_gap_beats,
            melody_policy=melody_policy,
            overrides_text=overrides_text,
            config=config,
        )
    )


def arrange_solution(
    midi_data: bytes,
    *,
    filename: str,
    track: int | None = None,
    channel: int | None = None,
    tuning_name: str = "standard",
    max_fret: int = 24,
    phrase_gap_beats: float = 1.0,
    melody_policy: str = "off",
    overrides_text: str | None = None,
    config: SolverConfig | None = None,
) -> ArrangementSolution:
    """Parse, select, reduce, group, phrase, lock and solve.

    Since v3 the solver works on onset events (1–6 simultaneous notes); the
    default melody policy `off` keeps every note and no longer rejects
    polyphonic onsets — that is the whole point of the chord solver. `top`/
    `bottom` remain explicit monophonic reductions. Returns the full solution
    object (the CLI needs phrase internals for `--explain`); serialization
    happens on top. Raises a `GuitarArrangementError` subclass for every
    unsupported or contradictory input — nothing is ever handled by a silent
    fallback.
    """
    if melody_policy not in ("off", "top", "bottom"):
        raise InvalidMelodyPolicyError(
            f"unknown melody policy {melody_policy!r} "
            "(expected off, top or bottom)"
        )
    if config is None:
        config = SolverConfig(
            max_fret=max_fret, phrase_gap_beats=phrase_gap_beats
        )
    tuning = resolve_tuning(tuning_name)
    parsed = parse_midi(midi_data)
    selected = select_notes(parsed, track=track, channel=channel)
    reduction = None
    notes = selected.notes
    if melody_policy != "off":
        notes, reduction = reduce_to_melody(notes, melody_policy)
    events = group_into_events(notes)
    polyphony = analyze_polyphony(events)
    event_phrases = split_event_phrases(
        events, parsed.ticks_per_beat, config.phrase_gap_beats
    )
    locked = (
        _validate_locks(notes, overrides_text, tuning, config)
        if overrides_text
        else {}
    )
    return ArrangementSolution(
        source=SourceInfo(
            filename=filename,
            ticks_per_beat=parsed.ticks_per_beat,
            track_index=selected.track_index,
            track_name=selected.name,
            channel=selected.channel,
            program=selected.program,
            tempo_events=parsed.tempo_events,
            time_signature_events=parsed.time_signature_events,
        ),
        tuning=tuning,
        config=config,
        phrases=solve_event_phrases(
            event_phrases, tuning, config, parsed.ticks_per_beat, locked
        ),
        polyphony=polyphony,
        melody_reduction=reduction,
    )


def _validate_locks(
    notes: tuple, overrides_text: str, tuning, config: SolverConfig
) -> dict[str, FretPosition]:
    """Check every lock against the actual notes before solving.

    A lock may only pin a position that produces the note's original pitch —
    a lock that would change the pitch is an error, never a transposition.
    """
    from .serialization import parse_overrides

    locks = parse_overrides(overrides_text)
    by_id = {note.id: note for note in notes}
    for note_id, position in locks.items():
        note = by_id.get(note_id)
        if note is None:
            known = ", ".join(sorted(by_id)[:5])
            raise InvalidOverridesError(
                f"lock references unknown note id {note_id!r} "
                f"(some known ids: {known}…)"
            )
        if position.string > tuning.string_count:
            raise InvalidOverridesError(
                f"lock for {note_id!r}: string {position.string} does not "
                f"exist ({tuning.string_count}-string tuning)"
            )
        if position.fret > config.max_fret:
            raise InvalidOverridesError(
                f"lock for {note_id!r}: fret {position.fret} exceeds "
                f"max_fret={config.max_fret}"
            )
        sounded = tuning.open_pitch(position.string) + position.fret
        if sounded != note.pitch:
            raise InvalidOverridesError(
                f"lock for {note_id!r} would change the pitch: string "
                f"{position.string} fret {position.fret} sounds MIDI "
                f"{sounded}, but the note is pitch {note.pitch}; pitches are "
                "never transposed"
            )
    return locks
