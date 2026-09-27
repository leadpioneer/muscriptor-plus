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

from .errors import UnplayableNoteError
from .fretboard import possible_fingerings, possible_positions
from .models import (
    AssignedNote,
    FingeringState,
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

