"""Ergonomic dynamic-programming solver for one monophonic guitar line (v2).

For each note the states are `FingeringState`s: string + fret + hand
position + finger. The best path through a phrase is found by dynamic
programming — never by per-note greedy picking. Because the state carries the
*hand position*, the solver can tell "four neighbouring frets under four
fingers" (free) from "crawling thirteen frets up one string" (several hand
shifts), and it may move early notes of a phrase to a distant hand position
if that avoids a shift later.

Cost of a transition (all weights in `SolverConfig`):

    hand_shift = |next.hand_position - previous.hand_position|
    position_change_cost = 0
        if hand_shift == 0
        else (position_change_base + position_change_per_fret * hand_shift)
               * multiplier
    multiplier = open_string_shift_discount  if the previous note is open
                 rest_gap_discount           if gap_beats >= rest_gap_beats
                 min of both                 if both apply
                 1.0                         otherwise
    string_crossing_cost = string_crossing_weight * |next.string - previous.string|
    finger_cost = finger_repeat_weight  if the same (non-open) finger is used
                                          again while the fret changes, else 0
    region_cost = high_position_weight * max(0, next.hand_position - high_position_start)

Ties are broken deterministically by comparing (cost, hand-position travel,
string travel) lexicographically; candidates are iterated in their sorted
order, so on a full tie the smaller (hand_position, finger) wins. Reruns on
the same input produce byte-identical output.
"""

from dataclasses import dataclass

from .chords import generate_chord_shapes
from .errors import UnplayableNoteError
from .fretboard import possible_fingerings, possible_positions
from .models import (
    AssignedEvent,
    AssignedNote,
    ChordFingeringState,
    FingeringState,
    NoteEvent,
    Phrase,
    PhraseSolution,
    SolverConfig,
)
from .models import ArrangementSolution


@dataclass(frozen=True)
class _Cell:
    """Best known way to reach one fingering state of one note."""

    cost: float
    hand_travel: int
    string_travel: int
    previous: int  # state index at the previous note; -1 at note 0

    def key(self) -> tuple[float, int, int]:
        return (self.cost, self.hand_travel, self.string_travel)


def position_region_cost(state: FingeringState, config: SolverConfig) -> float:
    """Weak per-note penalty for playing far up the neck.

    Anchored to the hand position, not the note's fret: a fret-13 note under
    finger 4 in position 10 is normal playing, not "high".
    """
    if state.hand_position > config.high_position_start:
        return config.high_position_weight * (
            state.hand_position - config.high_position_start
        )
    return 0.0


def transition_cost(
    previous: FingeringState,
    following: FingeringState,
    gap_beats: float,
    config: SolverConfig,
) -> float:
    """Cost of moving from one left-hand state to the next.

    `gap_beats` is the silence between the two notes (0 for legato), used for
    the rest discount — a hand shift during a pause is cheaper. The open-
    string discount applies when the *previous* note is open: the hand is
    free while it rings. Both discounts multiply the position-change part
    only, and neither makes a shift free.
    """
    hand_shift = abs(following.hand_position - previous.hand_position)
    cost = 0.0
    if hand_shift:
        multiplier = 1.0
        if previous.finger == 0:
            multiplier = min(multiplier, config.open_string_shift_discount)
        if gap_beats >= config.rest_gap_beats:
            multiplier = min(multiplier, config.rest_gap_discount)
        cost += (
            config.position_change_base
            + config.position_change_per_fret * hand_shift
        ) * multiplier
    cost += config.string_crossing_weight * abs(
        following.position.string - previous.position.string
    )
    if (
        previous.finger == following.finger
        and following.finger != 0
        and following.position.fret != previous.position.fret
    ):
        cost += config.finger_repeat_weight
    return cost



def solve_phrase(
    notes: tuple,
    candidates: tuple[tuple[FingeringState, ...], ...],
    config: SolverConfig,
    ticks_per_beat: int,
    locked_ids: frozenset[str] = frozenset(),
) -> PhraseSolution:
    """Find the globally cheapest fingering for one phrase.

    `candidates[i]` are the `FingeringState`s allowed for `notes[i]` (for
    tests the candidates may be synthetic and unrelated to any real tuning).
    Empty candidate lists raise `UnplayableNoteError`.
    """
    if len(notes) != len(candidates):
        raise ValueError("candidates must align with notes")
    for note, options in zip(notes, candidates):
        if not options:
            raise UnplayableNoteError(
                f"note {note.id} (pitch {note.pitch}) has no playable position",
                pitch=note.pitch,
                low_pitch=0,
                high_pitch=0,
            )

    # Silence between consecutive notes (0 for legato/overlap), in beats —
    # the rest discount input of transition_cost.
    gaps = [0.0]
    for previous_note, note in zip(notes, notes[1:]):
        gap_ticks = max(0, note.onset_ticks - previous_note.offset_ticks)
        gaps.append(gap_ticks / ticks_per_beat)

    # dp[i][k]: best known way to play note i at candidates[i][k].
    dp: list[list[_Cell]] = [
        [
            _Cell(
                cost=position_region_cost(state, config),
                hand_travel=0,
                string_travel=0,
                previous=-1,
            )
            for state in candidates[0]
        ]
    ]
    for i in range(1, len(notes)):
        previous_states = candidates[i - 1]
        previous_cells = dp[i - 1]
        gap_beats = gaps[i]
        row: list[_Cell] = []
        for state in candidates[i]:
            best: _Cell | None = None
            base_cost = position_region_cost(state, config)
            for j, previous_state in enumerate(previous_states):
                cell = previous_cells[j]
                replacement = _Cell(
                    cost=cell.cost
                    + transition_cost(previous_state, state, gap_beats, config)
                    + base_cost,
                    hand_travel=cell.hand_travel
                    + abs(state.hand_position - previous_state.hand_position),
                    string_travel=cell.string_travel
                    + abs(state.position.string - previous_state.position.string),
                    previous=j,
                )
                if best is None or replacement.key() < best.key():
                    best = replacement
            row.append(best)
        dp.append(row)
    return _backtrack(notes, candidates, dp, locked_ids)



def _backtrack(
    notes: tuple,
    candidates: tuple[tuple[FingeringState, ...], ...],
    dp: list[list[_Cell]],
    locked_ids: frozenset[str],
) -> PhraseSolution:
    """Pick the best final cell and reconstruct the chosen path."""
    last_cells = dp[-1]
    # Deterministic finish: min key; on a full tie the smaller candidate
    # index wins (candidates arrive sorted → smaller (hand_position, finger)).
    best_k = 0
    for k in range(1, len(last_cells)):
        if last_cells[k].key() < last_cells[best_k].key():
            best_k = k
    chosen = [best_k]
    for i in range(len(notes) - 1, 0, -1):
        chosen.append(dp[i][chosen[-1]].previous)
    chosen.reverse()

    assigned = tuple(
        AssignedNote(
            note=note,
            state=candidates[i][chosen[i]],
            legal_positions=sorted(
                {s.position for s in candidates[i]},
                key=lambda p: (p.fret, p.string),
            ),
            legal_fingerings=candidates[i],
            locked=note.id in locked_ids,
        )
        for i, note in enumerate(notes)
    )
    states = [a.state for a in assigned]
    return PhraseSolution(
        index=0,  # renumbered by solve_phrases
        start_tick=min(n.onset_ticks for n in notes),
        end_tick=max(n.offset_ticks for n in notes),
        cost=last_cells[best_k].cost,
        assigned=assigned,
        fret_travel=sum(
            abs(b.position.fret - a.position.fret)
            for a, b in zip(states, states[1:])
        ),
        string_travel=sum(
            abs(b.position.string - a.position.string)
            for a, b in zip(states, states[1:])
        ),
    )


def solve_phrases(
    phrases: tuple[Phrase, ...],
    tuning,
    config: SolverConfig,
    ticks_per_beat: int,
    locked_positions: dict | None = None,
) -> tuple[PhraseSolution, ...]:
    """Generate candidate fingerings for every note (honouring locks) and
    solve each phrase independently."""
    locked_positions = locked_positions or {}
    locked_ids = frozenset(locked_positions)
    solutions = []
    for phrase in phrases:
        candidates = tuple(
            (
                possible_fingerings(locked_positions[note.id], config)
                if note.id in locked_positions
                else tuple(
                    state
                    for position in possible_positions(
                        note.pitch, tuning, config.max_fret
                    )
                    for state in possible_fingerings(position, config)
                )
            )
            for note in phrase.notes
        )
        solution = solve_phrase(
            phrase.notes, candidates, config, ticks_per_beat, locked_ids
        )
        solutions.append(
            PhraseSolution(
                index=phrase.index,
                start_tick=solution.start_tick,
                end_tick=solution.end_tick,
                cost=solution.cost,
                assigned=solution.assigned,
                fret_travel=solution.fret_travel,
                string_travel=solution.string_travel,
            )
        )
    return tuple(solutions)


def explain_lines(solution: ArrangementSolution) -> list[str]:
    """Per-phrase ergonomic summary lines for the CLI's --explain output."""
    lines = []
    for phrase in solution.phrases:
        states = [a.state for a in phrase.assigned]
        shifts = [
            abs(b.hand_position - a.hand_position)
            for a, b in zip(states, states[1:])
        ]
        changes = sum(1 for shift in shifts if shift)
        pitches = [a.note.pitch for a in phrase.assigned]
        frets = [a.state.position.fret for a in phrase.assigned]
        hand_positions = sorted({s.hand_position for s in states})
        open_count = sum(1 for s in states if s.is_open)
        lines.append(
            f"phrase {phrase.index}: notes {len(phrase.assigned)}, "
            f"pitch {min(pitches)}–{max(pitches)}, "
            f"fret {min(frets)}–{max(frets)}, "
            f"hand positions {hand_positions}, "
            f"position changes {changes} "
            f"(largest shift {max(shifts, default=0)}), "
            f"open strings {open_count}, "
            f"cost {phrase.cost:.2f}"
        )
    return lines


# ---------------------------------------------------------------------------
# v3: chord (onset event) DP
# ---------------------------------------------------------------------------


def _string_centre(state: ChordFingeringState) -> float:
    strings = [n.position.string for n in state.notes]
    return sum(strings) / len(strings)


def chord_transition_cost(
    previous: ChordFingeringState,
    following: ChordFingeringState,
    gap_beats: float,
    config: SolverConfig,
) -> float:
    """Cost of moving the left hand from one chord shape to the next.

    Singleton→singleton transitions use the v2 formula verbatim, so a
    monophonic line is costed exactly as before. Chords are compared through
    hand position and the used-string centre — never through per-note fret
    deltas, since two shapes have no natural note-to-note correspondence.
    """
    if len(previous.notes) == 1 and len(following.notes) == 1:
        previous_note = previous.notes[0]
        following_note = following.notes[0]
        return transition_cost(
            FingeringState(
                position=previous_note.position,
                hand_position=previous.hand_position,
                finger=previous_note.finger if previous_note.finger else 0,
            ),
            FingeringState(
                position=following_note.position,
                hand_position=following.hand_position,
                finger=following_note.finger if following_note.finger else 0,
            ),
            gap_beats,
            config,
        )
    hand_shift = abs(following.hand_position - previous.hand_position)
    cost = 0.0
    if hand_shift:
        multiplier = 1.0
        if previous.has_open_string:
            multiplier = min(multiplier, config.open_string_shift_discount)
        if gap_beats >= config.rest_gap_beats:
            multiplier = min(multiplier, config.rest_gap_discount)
        cost += (
            config.position_change_base
            + config.position_change_per_fret * hand_shift
        ) * multiplier
    cost += config.string_movement_weight * abs(
        _string_centre(following) - _string_centre(previous)
    )
    return cost


@dataclass(frozen=True)
class _EventCell:
    """Best known way to reach one chord shape of one onset event."""

    cost: float
    hand_travel: int
    string_travel: float
    previous: int

    def key(self) -> tuple:
        return (self.cost, self.hand_travel, self.string_travel)


def solve_event_phrase(
    events: tuple[NoteEvent, ...],
    tuning,
    config: SolverConfig,
    ticks_per_beat: int,
    locked_positions: dict | None = None,
) -> PhraseSolution:
    """Globally cheapest sequence of chord shapes for one phrase of events.

    The DP states are full `ChordFingeringState`s of each event. Candidate
    caps prune deterministically (shapes arrive sorted by cost, then canonical
    key) and the generated/pruned counts are reported per event — an optimum
    is therefore claimed only among retained candidates.
    """
    locked_positions = locked_positions or {}
    locked_ids = frozenset(locked_positions)
    if not events:
        return PhraseSolution(
            index=0, start_tick=0, end_tick=0, cost=0.0, assigned=(), events=()
        )
    candidate_lists: list[tuple[ChordFingeringState, ...]] = []
    stats: list[tuple[int, int]] = []
    for event in events:
        shapes = generate_chord_shapes(event, tuning, config, locked_positions)
        generated = len(shapes)
        pruned = max(0, generated - config.max_chord_candidates)
        candidate_lists.append(shapes[: config.max_chord_candidates])
        stats.append((generated, pruned))

    # Silence between consecutive events, from the previous event's LAST
    # note offset — a long ringing bass note is not a rest.
    gaps = [0.0]
    for previous_event, event in zip(events, events[1:]):
        gap_ticks = max(0, event.onset_ticks - previous_event.last_offset_ticks)
        gaps.append(gap_ticks / ticks_per_beat)

    dp: list[list[_EventCell]] = [
        [
            _EventCell(
                cost=shape.shape_cost, hand_travel=0, string_travel=0.0, previous=-1
            )
            for shape in candidate_lists[0]
        ]
    ]
    for i in range(1, len(events)):
        previous_states = candidate_lists[i - 1]
        previous_cells = dp[i - 1]
        gap_beats = gaps[i]
        row: list[_EventCell] = []
        for shape in candidate_lists[i]:
            best: _EventCell | None = None
            for j, previous_shape in enumerate(previous_states):
                cell = previous_cells[j]
                replacement = _EventCell(
                    cost=cell.cost
                    + chord_transition_cost(
                        previous_shape, shape, gap_beats, config
                    )
                    + shape.shape_cost,
                    hand_travel=cell.hand_travel
                    + abs(shape.hand_position - previous_shape.hand_position),
                    string_travel=cell.string_travel
                    + abs(_string_centre(shape) - _string_centre(previous_shape)),
                    previous=j,
                )
                if best is None or replacement.key() < best.key():
                    best = replacement
            row.append(best)
        dp.append(row)

    # Deterministic finish: the smallest key wins; on a full tie the smaller
    # candidate index wins (candidates are canonically sorted).
    last_cells = dp[-1]
    best_k = 0
    for k in range(1, len(last_cells)):
        if last_cells[k].key() < last_cells[best_k].key():
            best_k = k
    chosen = [best_k]
    for i in range(len(events) - 1, 0, -1):
        chosen.append(dp[i][chosen[-1]].previous)
    chosen.reverse()

    assigned_events = tuple(
        AssignedEvent(
            event=event,
            state=candidate_lists[i][chosen[i]],
            generated_candidates=stats[i][0],
            pruned_candidates=stats[i][1],
        )
        for i, event in enumerate(events)
    )
    assigned_notes: list[AssignedNote] = []
    for i, event in enumerate(events):
        state = candidate_lists[i][chosen[i]]
        for note, chord_note in zip(event.notes, state.notes):
            positions = possible_positions(note.pitch, tuning, config.max_fret)
            assigned_notes.append(
                AssignedNote(
                    note=note,
                    state=FingeringState(
                        position=chord_note.position,
                        hand_position=state.hand_position,
                        finger=chord_note.finger if chord_note.finger else 0,
                    ),
                    legal_positions=positions,
                    legal_fingerings=tuple(
                        finger_state
                        for position in positions
                        for finger_state in possible_fingerings(position, config)
                    ),
                    locked=note.id in locked_ids,
                )
            )
    # Flat view: onset, then pitch descending, then id — the event order.
    assigned_notes.sort(
        key=lambda a: (a.note.onset_ticks, -a.note.pitch, a.note.id)
    )
    states = [a.state for a in assigned_notes]
    fret_travel = sum(
        abs(b.position.fret - a.position.fret)
        for a, b in zip(states, states[1:])
    )
    string_travel = sum(
        abs(b.position.string - a.position.string)
        for a, b in zip(states, states[1:])
    )
    return PhraseSolution(
        index=0,  # renumbered by solve_event_phrases
        start_tick=events[0].onset_ticks,
        end_tick=max(event.last_offset_ticks for event in events),
        cost=last_cells[best_k].cost,
        assigned=tuple(assigned_notes),
        events=assigned_events,
        fret_travel=fret_travel,
        string_travel=string_travel,
    )


def solve_event_phrases(
    event_phrases: tuple[tuple[NoteEvent, ...], ...],
    tuning,
    config: SolverConfig,
    ticks_per_beat: int,
    locked_positions: dict | None = None,
) -> tuple[PhraseSolution, ...]:
    """Solve every phrase of onset events independently."""
    solutions = []
    for index, events in enumerate(event_phrases):
        solution = solve_event_phrase(
            events, tuning, config, ticks_per_beat, locked_positions
        )
        solutions.append(
            PhraseSolution(
                index=index,
                start_tick=solution.start_tick,
                end_tick=solution.end_tick,
                cost=solution.cost,
                assigned=solution.assigned,
                events=solution.events,
                fret_travel=solution.fret_travel,
                string_travel=solution.string_travel,
            )
        )
    return tuple(solutions)


def _event_summary(assigned_event: AssignedEvent) -> str:
    state = assigned_event.state
    frets = sorted(state.closed_frets)
    span = f"fret {frets[0]}–{frets[-1]}" if frets else "open only"
    barres = (
        "; barres "
        + ", ".join(
            f"f{b.finger}@{b.fret} (strings {b.from_string}–{b.to_string})"
            for b in state.barres
        )
        if state.barres
        else ""
    )
    return (
        f"tick {state.onset_ticks}: {len(state.notes)} notes, "
        f"{span}, hand position {state.hand_position}{barres}"
    )


def explain_chord_lines(solution: ArrangementSolution) -> list[str]:
    """Per-phrase summaries for --explain, chord-aware (v3)."""
    analysis = solution.polyphony
    lines = [
        f"polyphony: {analysis.note_count} notes in "
        f"{analysis.onset_event_count} onset events, "
        f"{analysis.polyphonic_event_count} polyphonic, largest group "
        f"{analysis.largest_onset_group}, max active "
        f"{analysis.max_active_notes}, "
        f"strictly monophonic {str(analysis.strictly_monophonic).lower()}"
    ]
    for phrase in solution.phrases:
        lines.append(
            f"phrase {phrase.index}: events {len(phrase.events)}, "
            f"notes {len(phrase.assigned)}, cost {phrase.cost:.2f}"
        )
        for assigned_event in phrase.events:
            marker = (
                "chord" if len(assigned_event.event.notes) > 1 else "note "
            )
            lines.append(f"  {marker} {_event_summary(assigned_event)}")
    return lines

