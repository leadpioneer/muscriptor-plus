"""End-to-end arrangement pipeline: MIDI bytes → arrangement dict.

The single entry point shared by the CLI and the HTTP endpoint. Reads nothing
from disk itself (bytes in, dict out) and knows nothing about FastAPI or
Typer, so the whole flow stays testable without either.
"""

from .chords import choose_playable_subset
from .errors import (
    InvalidMelodyPolicyError,
    InvalidOverridesError,
    UnplayableNoteError,
)
from .events import analyze_polyphony, group_into_events
from .fretboard import resolve_tuning
from .harmony import detect_chord_labels
from .melody import reduce_to_melody
from .midi_input import parse_midi, select_notes
from .models import (
    ArrangementSolution,
    ChordReduction,
    DroppedNote,
    FretPosition,
    GuitarTuning,
    NoteEvent,
    SolverConfig,
    SourceInfo,
)
from .normalize import normalize_to_tuning
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
    normalize: bool = True,
    chord_overflow: str = "reduce",
    detect_chords: bool = True,
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
            normalize=normalize,
            chord_overflow=chord_overflow,
            detect_chords=detect_chords,
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
    normalize: bool = True,
    chord_overflow: str = "reduce",
    detect_chords: bool = True,
    config: SolverConfig | None = None,
) -> ArrangementSolution:
    """Parse, select, normalize, reduce, group, phrase, lock and solve.

    Since v3 the solver works on onset events (1–6 simultaneous notes); the
    default melody policy `off` keeps every note and does not reject
    polyphonic onsets — that is the whole point of the chord solver. `top`/
    `bottom` remain explicit monophonic reductions. Returns the full solution
    object (the CLI needs phrase internals for `--explain`); serialization
    happens on top. Raises a `GuitarArrangementError` subclass for every
    unsupported or contradictory input — nothing is ever handled by a silent
    fallback.

    `normalize` (default on) fits the part to the target tuning first: the
    whole part may be transposed and out-of-range octave duplicates removed,
    both reported in the document's `normalization` block. `chord_overflow`
    selects what to do with onsets that cannot be played in full (more notes
    than strings, or no mutually compatible fingering): `reduce` (default)
    keeps the best playable subset and reports it in `chord_reductions`,
    `error` leaves the event to the solver's structured failure.
    `detect_chords` (default on) runs jazz chord-symbol detection over the
    finished timeline and records the labels in the `chords` block.
    """
    if melody_policy not in ("off", "top", "bottom"):
        raise InvalidMelodyPolicyError(
            f"unknown melody policy {melody_policy!r} (expected off, top or bottom)"
        )
    if config is None:
        config = SolverConfig(max_fret=max_fret, phrase_gap_beats=phrase_gap_beats)
    tuning = resolve_tuning(tuning_name)
    parsed = parse_midi(midi_data)
    selected = select_notes(parsed, track=track, channel=channel)
    reduction = None
    notes = selected.notes
    if melody_policy != "off":
        notes, reduction = reduce_to_melody(notes, melody_policy)
    normalization = None
    if normalize:
        notes, normalization = normalize_to_tuning(notes, tuning, config)
    # Range first: a note outside the fretboard stays a plain error (or is
    # dealt with by normalization above) — the chord repair below must never
    # drop it as if the event were merely unplayable.
    _validate_fretboard_range(notes, tuning, config)
    events = group_into_events(notes)
    chord_reductions: tuple[ChordReduction, ...] = ()
    if chord_overflow == "reduce":
        events, chord_reductions = _repair_chord_events(events, tuning, config)
        notes = tuple(note for event in events for note in event.notes)
    chords = ()
    if detect_chords:
        chords = detect_chord_labels(
            notes, parsed.ticks_per_beat, parsed.time_signature_events
        )
    polyphony = analyze_polyphony(events)
    event_phrases = split_event_phrases(
        events, parsed.ticks_per_beat, config.phrase_gap_beats
    )
    locked = (
        _validate_locks(notes, overrides_text, tuning, config) if overrides_text else {}
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
        normalization=normalization,
        chord_reductions=chord_reductions,
        chords=chords,
    )


def _repair_chord_events(
    events: tuple[NoteEvent, ...], tuning: GuitarTuning, config: SolverConfig
) -> tuple[tuple[NoteEvent, ...], tuple[ChordReduction, ...]]:
    """Make every onset fully playable, or reduce it to its best subset.

    Two failure shapes are handled, both reported in `chord_reductions`:
    onsets with more notes than strings (`chord_overflow`) and onsets that
    fit the string count but have no mutually compatible fingering, e.g. a
    melody note stacked over a chord with no shared position
    (`unplayable_chord`). Events with no playable subset at all are left
    untouched: the solver then raises its structured error with the full
    event context instead of this stage pretending to know better.
    """
    repaired: list[NoteEvent] = []
    reports: list[ChordReduction] = []
    for event in events:
        subset = choose_playable_subset(event, tuning, config)
        if subset is None or len(subset) == len(event.notes):
            repaired.append(event)
            continue
        kept_ids = {note.id for note in subset}
        dropped = [note for note in event.notes if note.id not in kept_ids]
        reason = (
            "chord_overflow"
            if len(event.notes) > tuning.string_count
            else "unplayable_chord"
        )
        repaired.append(NoteEvent(event.index, event.onset_ticks, tuple(subset)))
        reports.append(
            ChordReduction(
                onset_ticks=event.onset_ticks,
                note_count=len(event.notes),
                dropped=tuple(
                    DroppedNote(note.id, note.pitch, note.onset_ticks, reason)
                    for note in dropped
                ),
            )
        )
    return tuple(repaired), tuple(reports)


def _validate_fretboard_range(notes: tuple, tuning, config: SolverConfig) -> None:
    """Refuse out-of-range notes once, with the full picture.

    Runs after normalization (and after any chord-overflow reduction), so
    whatever still lands here could not be fitted by any shift and has no
    in-range octave twin to make it redundant. Every offender is collected
    and reported in one error: the count, the distinct pitches and a sample
    of ticks. This check itself never transposes or drops anything.
    """
    if not notes:
        return
    low = tuning.low_pitch
    high = max(tuning.open_pitches) + config.max_fret
    offenders = [n for n in notes if n.pitch < low or n.pitch > high]
    if not offenders:
        return
    pitches = sorted({n.pitch for n in offenders})
    sample = ", ".join(
        f"pitch {n.pitch} at tick {n.onset_ticks}" for n in offenders[:5]
    )
    more = f" (and {len(offenders) - 5} more)" if len(offenders) > 5 else ""
    error = UnplayableNoteError(
        f"{len(offenders)} of {len(notes)} notes lie outside the fretboard: "
        f"the tuned strings cover MIDI {low}–{high} "
        f"(max_fret={config.max_fret}); offending pitches {pitches}; "
        f"first offenders: {sample}{more}. This check never transposes or "
        "drops anything itself: transpose the track manually "
        "(e.g. +12 semitones), extract the melody (top/bottom policy), or "
        "pick a part that fits the standard tuning",
        pitch=offenders[0].pitch,
        low_pitch=low,
        high_pitch=high,
    )
    # Extra structured context for API clients (the UI reads pitch/low/high
    # only; extra keys are additive and ignored by older clients).
    error.details.update(
        {"offender_count": len(offenders), "offender_pitches": pitches}
    )
    raise error


def _validate_locks(
    notes: tuple, overrides_text: str, tuning, config: SolverConfig
) -> dict[str, FretPosition]:
    """Check every lock against the actual notes before solving.

    A lock may only pin a position that produces the note's original pitch —
    a lock that would change the pitch is an error, never a transposition.
    """
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
