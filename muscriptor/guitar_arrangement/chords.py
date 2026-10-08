"""Chord shape generation for polyphonic onset events (v3).

For one `NoteEvent` this module produces every playable `ChordFingeringState`:
each note of the event is assigned a distinct string whose open pitch plus
fret sounds exactly the note's original pitch, then hand positions and finger
annotations (with barres) are attached. Nothing is ever dropped, transposed
or arpeggiated — if no full assignment exists, the failure is a structured
error, not a reduced chord.

Pure function module: no files, no network, no FastAPI.
"""

from typing import Iterator

from .errors import (
    IncompatibleChordLocksError,
    TooManyChordNotesError,
    UnplayableChordError,
)
from .fretboard import possible_positions
from .models import (
    BarreState,
    ChordFingeringState,
    ChordNoteState,
    FretPosition,
    GuitarTuning,
    NoteEvent,
    SolverConfig,
)

# Upper bound on finger-annotation variants inspected per (shape, position);
# the raw space is ≤4^6 but the cap makes the worst case provably bounded.
_MAX_FINGER_VARIANTS = 16


def generate_chord_shapes(
    event: NoteEvent,
    tuning: GuitarTuning,
    config: SolverConfig,
    locks: dict[str, FretPosition] | None = None,
) -> tuple[ChordFingeringState, ...]:
    """Every playable fingering state for one onset event, canonically sorted.

    Locks pin their note to the exact string/fret (the pitch invariant is
    validated upstream, and re-checked here defensively). Raises
    `TooManyChordNotesError`, `UnplayableChordError` or
    `IncompatibleChordLocksError` — never silently drops a note.
    """
    locks = locks or {}
    notes = event.notes
    if len(notes) > tuning.string_count:
        raise TooManyChordNotesError(
            f"{len(notes)} notes start at tick {event.onset_ticks} but a "
            f"{tuning.string_count}-string guitar has only "
            f"{tuning.string_count} strings; nothing is dropped — reduce the "
            "event (melody top/bottom) or fix the input",
            onset_ticks=event.onset_ticks,
            note_ids=list(event.note_ids),
            pitches=list(event.pitches),
            available_strings=tuning.string_count,
        )

    per_note_positions: list[tuple[FretPosition, ...]] = []
    for note in notes:
        locked = locks.get(note.id)
        if locked is not None:
            sounded = tuning.open_pitch(locked.string) + locked.fret
            if sounded != note.pitch:  # defensive; the pipeline validates too
                raise IncompatibleChordLocksError(
                    f"lock for {note.id!r} would change the pitch: string "
                    f"{locked.string} fret {locked.fret} sounds MIDI {sounded}, "
                    f"the note is pitch {note.pitch}",
                    onset_ticks=event.onset_ticks,
                    note_ids=[note.id],
                    strings=[locked.string],
                )
            per_note_positions.append((locked,))
            continue
        try:
            per_note_positions.append(
                possible_positions(note.pitch, tuning, config.max_fret)
            )
        except UnplayableChordError:  # pragma: no cover - defensive
            raise
        except Exception as e:
            raise UnplayableChordError(
                str(e),
                onset_ticks=event.onset_ticks,
                note_ids=list(event.note_ids),
                pitches=list(event.pitches),
                available_strings=tuning.string_count,
                reason=f"pitch {note.pitch} has no playable position",
            ) from e

    shapes: list[ChordFingeringState] = []
    for assignment in _string_assignments(
        event, per_note_positions, tuning, config, locks
    ):
        shapes.extend(_state_variants(event, assignment, config))
    shapes.sort(key=lambda s: s.sort_key())
    unique: list[ChordFingeringState] = []
    seen: set[tuple] = set()
    for shape in shapes:
        key = (
            shape.hand_position,
            tuple(
                (n.note_id, n.position.string, n.position.fret, n.finger)
                for n in shape.notes
            ),
            tuple((b.finger, b.fret, b.from_string, b.to_string) for b in shape.barres),
        )
        if key not in seen:
            seen.add(key)
            unique.append(shape)
    return tuple(unique)


def _string_assignments(
    event: NoteEvent,
    per_note_positions: list[tuple[FretPosition, ...]],
    tuning: GuitarTuning,
    config: SolverConfig,
    locks: dict[str, FretPosition],
) -> list[tuple[FretPosition, ...]]:
    """Every injective note→string assignment with an acceptable fret span.

    Backtracking over the notes in event order (pitch descending, note id);
    the running closed-fret span prunes branches that already exceed
    `max_chord_fret_span`. With locks involved, failure raises
    `IncompatibleChordLocksError`; without them, `UnplayableChordError`.
    """
    locked_ids = {n.id for n in event.notes if n.id in locks}
    results: list[tuple[FretPosition, ...]] = []
    chosen: list[FretPosition] = []
    used_strings: set[int] = set()

    # The running span starts from LOCKED positions only (they are fixed);
    # every other note's span contribution is accounted during backtracking.
    initial_frets = [
        positions[0].fret
        for positions, note in zip(per_note_positions, event.notes)
        if note.id in locked_ids and positions[0].fret > 0
    ]
    initial_lo = min(initial_frets) if initial_frets else None
    initial_hi = max(initial_frets) if initial_frets else None

    def backtrack(index: int, lo: int | None, hi: int | None) -> None:
        if index == len(per_note_positions):
            results.append(tuple(chosen))
            return
        for position in per_note_positions[index]:
            if position.string in used_strings:
                continue
            nlo, nhi = lo, hi
            if position.fret > 0:
                nlo = position.fret if lo is None else min(lo, position.fret)
                nhi = position.fret if hi is None else max(hi, position.fret)
                if nhi - nlo > config.max_chord_fret_span:
                    continue
            chosen.append(position)
            used_strings.add(position.string)
            backtrack(index + 1, nlo, nhi)
            used_strings.discard(position.string)
            chosen.pop()

    backtrack(0, initial_lo, initial_hi)
    if results:
        return results

    # No assignment: the error depends on whether locks were involved.
    if locked_ids:
        locked_here = [
            (n.id, per_note_positions[i][0].string)
            for i, n in enumerate(event.notes)
            if n.id in locked_ids
        ]
        raise IncompatibleChordLocksError(
            "the locks of this chord event cannot be combined: "
            + ", ".join(f"{nid!r} on string {s}" for nid, s in locked_here)
            + " leave no legal completion for the remaining notes",
            onset_ticks=event.onset_ticks,
            note_ids=[nid for nid, _ in locked_here],
            strings=[s for _, s in locked_here],
        )
    reason = "no assignment of distinct strings sounds every pitch"
    raise UnplayableChordError(
        f"no chord shape at tick {event.onset_ticks}: {reason} "
        f"(pitches {list(event.pitches)}, {tuning.string_count} strings, "
        f"max_fret={config.max_fret}, max_chord_fret_span="
        f"{config.max_chord_fret_span})",
        onset_ticks=event.onset_ticks,
        note_ids=list(event.note_ids),
        pitches=list(event.pitches),
        available_strings=tuning.string_count,
        reason=reason,
    )


def _state_variants(
    event: NoteEvent,
    assignment: tuple[FretPosition, ...],
    config: SolverConfig,
) -> list[ChordFingeringState]:
    """Fingering states for one string assignment: one per hand position,
    each with the best finger annotation the 4-finger window allows."""
    closed_frets = [p.fret for p in assignment if p.fret > 0]
    variants: list[ChordFingeringState] = []
    for hand_position in _hand_positions(closed_frets, config):
        fingers, complete = _best_finger_annotation(assignment, hand_position, config)
        barres = _barres_for(event, assignment, fingers)
        states = tuple(
            ChordNoteState(
                note_id=note.id,
                pitch=note.pitch,
                position=position,
                finger=finger,
            )
            for note, position, finger in zip(event.notes, assignment, fingers)
        )
        variants.append(
            ChordFingeringState(
                event_index=event.index,
                onset_ticks=event.onset_ticks,
                notes=states,
                hand_position=hand_position,
                barres=barres,
                shape_cost=_shape_cost(
                    assignment, hand_position, barres, complete, config
                ),
                finger_assignment_complete=complete,
            )
        )
    return variants


def _hand_positions(closed_frets: list[int], config: SolverConfig) -> list[int]:
    """Hand positions where every closed note fits the 4-finger window.

    Strict v2 relation: finger = fret − hand_position + 1, so a closed fret f
    requires hand_position ∈ [f−3, f]. Open strings never constrain the hand.
    If the shape's closed span exceeds the window (or sits above the hand
    limit), the shape is kept anyway with the hand at the lowest closed fret —
    the finger annotation then honestly reports itself incomplete instead of
    the shape being discarded.
    """
    limit = config.hand_position_limit
    if not closed_frets:
        return list(range(1, limit + 1))
    lo, hi = min(closed_frets), max(closed_frets)
    first = max(1, hi - 3)
    last = min(limit, lo)
    if first <= last:
        return list(range(first, last + 1))
    return [min(limit, lo)]


def _finger_annotations(
    assignment: tuple[FretPosition, ...], hand_position: int
) -> Iterator[tuple[tuple[int | None, ...], bool]]:
    """Small bounded backtracking over finger labels for the closed notes.

    Rules: open strings are finger 0; one finger never sits on two different
    frets; several strings may share one finger only at the same fret (a
    barre). The strict v2 label (finger = fret − hand_position + 1) is tried
    first, other free fingers after — deterministic order.
    """
    fingers: list[int | None] = [0] * len(assignment)
    finger_fret: dict[int, int] = {}
    closed = [i for i, p in enumerate(assignment) if p.fret > 0]

    def backtrack(index: int):
        if index == len(closed):
            yield tuple(fingers), True
            return
        fret = assignment[closed[index]].fret
        strict = fret - hand_position + 1
        candidates: list[int] = []
        if 1 <= strict <= 4:
            candidates.append(strict)
        candidates.extend(f for f in (1, 2, 3, 4) if f not in candidates)
        for finger in candidates:
            if finger in finger_fret and finger_fret[finger] != fret:
                continue
            previous = finger_fret.get(finger)
            fingers[closed[index]] = finger
            finger_fret[finger] = fret
            yield from backtrack(index + 1)
            if previous is None:
                del finger_fret[finger]
            else:
                finger_fret[finger] = previous
            fingers[closed[index]] = 0

    found = False
    for annotation in backtrack(0):
        found = True
        yield annotation
    if not found:
        # No finger labelling exists at all (e.g. a stretch beyond the
        # window): keep the shape with everything unlabelled.
        yield (None,) * len(assignment), False


def _best_finger_annotation(
    assignment: tuple[FretPosition, ...],
    hand_position: int,
    config: SolverConfig,
) -> tuple[tuple[int | None, ...], bool]:
    """The best finger annotation for one (shape, hand position).

    Preference: every note labelled, then fewer/narrower barres, then the
    lexicographically smallest finger tuple. An annotation placing one finger
    across a string occupied at a different fret is physically impossible and
    discarded; if every variant fails that check, the notes are left
    unlabelled (`finger=None`) instead of the shape being dropped.
    """

    def barre_stats(fingers) -> tuple[int, int]:
        by_finger: dict[int, list[int]] = {}
        for position, finger in zip(assignment, fingers):
            if finger:
                by_finger.setdefault(finger, []).append(position.string)
        count = width = 0
        for strings in by_finger.values():
            if len(strings) > 1:
                count += 1
                width += max(strings) - min(strings) + 1
        return count, width

    def consistent(fingers) -> bool:
        by_finger: dict[int, list[tuple[int, int]]] = {}
        for position, finger in zip(assignment, fingers):
            if finger:
                by_finger.setdefault(finger, []).append(
                    (position.string, position.fret)
                )
        for spots in by_finger.values():
            if len(spots) < 2:
                continue
            strings = [s for s, _ in spots]
            lo, hi = min(strings), max(strings)
            fret = spots[0][1]
            # A note between the barre's strings at a LOWER fret (or an open
            # string) would sit under the finger — impossible. Higher frets
            # are fine: other fingers press behind the barre.
            if any(
                lo < p.string < hi and (p.fret == 0 or p.fret < fret)
                for p in assignment
            ):
                return False
        return True

    best_key: tuple | None = None
    best: tuple[tuple[int | None, ...], bool] | None = None
    variants = 0
    for fingers, complete in _finger_annotations(assignment, hand_position):
        variants += 1
        if not complete:
            candidate_key = (1, 0, 0)
            candidate = (fingers, False)
        elif consistent(fingers):
            count_barres, width = barre_stats(fingers)
            candidate_key = (0, count_barres, width)
            candidate = (fingers, True)
        else:
            continue
        if best_key is None or candidate_key < best_key:
            best_key = candidate_key
            best = candidate
        if best[1] and variants >= _MAX_FINGER_VARIANTS:
            break
    if best is None:
        # Every variant crossed a differently-fretted string: label nothing,
        # keep the shape, flag it honestly.
        return (None,) * len(assignment), False
    return best


def _barres_for(
    event: NoteEvent,
    assignment: tuple[FretPosition, ...],
    fingers: tuple[int | None, ...],
) -> tuple[BarreState, ...]:
    """Barre states: one finger across several strings at one fret.

    A barre is claimed only when no open string of the same event sounds
    between its outermost strings — a barre across a ringing open string is
    not something the annotation may claim.
    """
    open_strings = {p.string for p in assignment if p.fret == 0}
    by_finger: dict[int, list[tuple[int, int, str]]] = {}
    for note, position, finger in zip(event.notes, assignment, fingers):
        if finger:
            by_finger.setdefault(finger, []).append(
                (position.string, position.fret, note.id)
            )
    barres = []
    for finger in sorted(by_finger):
        spots = by_finger[finger]
        if len(spots) < 2:
            continue
        fret = spots[0][1]
        strings = [s for s, _, _ in spots]
        from_string, to_string = min(strings), max(strings)
        if any(from_string < s < to_string for s in open_strings):
            continue
        ids = tuple(note_id for _, _, note_id in sorted(spots))
        barres.append(
            BarreState(
                finger=finger,
                fret=fret,
                from_string=from_string,
                to_string=to_string,
                note_ids=ids,
            )
        )
    return tuple(barres)


def _shape_cost(
    assignment: tuple[FretPosition, ...],
    hand_position: int,
    barres: tuple[BarreState, ...],
    complete: bool,
    config: SolverConfig,
) -> float:
    """Intrinsic cost of one shape (independent of what came before).

    Fret span of the closed notes, barre width, weak high-position penalty,
    optional open-string penalty (0.0 by default — open strings are not a
    mistake) and the honest incomplete-annotation penalty.
    """
    closed_frets = [p.fret for p in assignment if p.fret > 0]
    span = (max(closed_frets) - min(closed_frets)) if closed_frets else 0
    open_count = sum(1 for p in assignment if p.fret == 0)
    cost = config.chord_span_weight * span
    cost += config.barre_weight * sum(b.to_string - b.from_string + 1 for b in barres)
    if hand_position > config.high_position_start:
        cost += config.high_position_weight * (
            hand_position - config.high_position_start
        )
    cost += config.open_string_weight * open_count
    if not complete:
        cost += config.incomplete_finger_weight
    return cost
