"""Dynamic-programming solver for one monophonic guitar line.

For each note the states are its legal `FretPosition`s. Within a phrase the
best path is found by dynamic programming — never by per-note greedy picking,
which is exactly what produces awkward tablature: the solver may place early
notes on non-minimal frets if that avoids a large jump later in the phrase.

Ties are broken deterministically by comparing (cost, fret travel, string
travel) lexicographically; candidates are iterated in their sorted order, so
on a full tie the smaller (fret, string) position wins. Reruns on the same
input therefore produce byte-identical output.
"""

from dataclasses import dataclass

from .errors import UnplayableNoteError
from .fretboard import possible_positions
from .models import (
    AssignedNote,
    FretPosition,
    Phrase,
    PhraseSolution,
    SolverConfig,
)


@dataclass(frozen=True)
class _Cell:
    """Best known way to reach one candidate of one note."""

    cost: float
    fret_travel: int
    string_travel: int
    previous: int  # candidate index at the previous note; -1 at note 0

    def key(self) -> tuple[float, int, int]:
        return (self.cost, self.fret_travel, self.string_travel)


def note_cost(position: FretPosition, config: SolverConfig) -> float:
    """Weak per-note penalty for unjustified high frets."""
    if position.fret > config.high_fret_start:
        return config.high_fret_weight * (position.fret - config.high_fret_start)
    return 0.0


def transition_cost(
    previous: FretPosition, following: FretPosition, config: SolverConfig
) -> float:
    """Cost of moving the hand between two neighbouring positions."""
    fret_delta = abs(following.fret - previous.fret)
    string_delta = abs(following.string - previous.string)
    cost = (
        config.fret_movement_weight * fret_delta
        + config.string_movement_weight * string_delta
    )
    change = fret_delta + string_delta
    if change > config.large_position_change_threshold:
        cost += config.large_position_change_weight * (
            change - config.large_position_change_threshold
        )
    return cost


def solve_phrase(
    notes: tuple,
    candidates: tuple[tuple[FretPosition, ...], ...],
    config: SolverConfig,
    locked_ids: frozenset[str] = frozenset(),
) -> PhraseSolution:
    """Find the globally cheapest fingering for one phrase.

    `candidates[i]` are the positions allowed for `notes[i]` (for tests the
    candidates may be synthetic and unrelated to any real tuning). Empty
    candidate lists raise `UnplayableNoteError`.
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

    # dp[i][k]: best known way to play note i at candidates[i][k].
    dp: list[list[_Cell]] = [
        [
            _Cell(
                cost=note_cost(position, config),
                fret_travel=0,
                string_travel=0,
                previous=-1,
            )
            for position in candidates[0]
        ]
    ]
    for i in range(1, len(notes)):
        previous_options = candidates[i - 1]
        previous_cells = dp[i - 1]
        row: list[_Cell] = []
        for position in candidates[i]:
            best: _Cell | None = None
            base_cost = note_cost(position, config)
            for j, previous_position in enumerate(previous_options):
                cell = previous_cells[j]
                replacement = _Cell(
                    cost=cell.cost
                    + transition_cost(previous_position, position, config)
                    + base_cost,
                    fret_travel=cell.fret_travel
                    + abs(position.fret - previous_position.fret),
                    string_travel=cell.string_travel
                    + abs(position.string - previous_position.string),
                    previous=j,
                )
                if best is None or replacement.key() < best.key():
                    best = replacement
            row.append(best)
        dp.append(row)
    return _backtrack(notes, candidates, dp, locked_ids)


def _backtrack(
    notes: tuple,
    candidates: tuple[tuple[FretPosition, ...], ...],
    dp: list[list[_Cell]],
    locked_ids: frozenset[str],
) -> PhraseSolution:
    """Pick the best final cell and reconstruct the chosen path."""
    last_cells = dp[-1]
    # Deterministic finish: min key; on a full tie the smaller candidate
    # index wins (candidates arrive sorted → smaller (fret, string)).
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
            position=candidates[i][chosen[i]],
            legal_positions=candidates[i],
            locked=note.id in locked_ids,
        )
        for i, note in enumerate(notes)
    )
    positions = [a.position for a in assigned]
    return PhraseSolution(
        index=0,  # renumbered by solve_phrases
        start_tick=min(n.onset_ticks for n in notes),
        end_tick=max(n.offset_ticks for n in notes),
        cost=last_cells[best_k].cost,
        assigned=assigned,
        fret_travel=sum(
            abs(b.fret - a.fret) for a, b in zip(positions, positions[1:])
        ),
        string_travel=sum(
            abs(b.string - a.string) for a, b in zip(positions, positions[1:])
        ),
    )


def solve_phrases(
    phrases: tuple[Phrase, ...],
    tuning,
    config: SolverConfig,
    locked_positions: dict[str, FretPosition] | None = None,
) -> tuple[PhraseSolution, ...]:
    """Generate candidates for every note (honouring locks) and solve each
    phrase independently."""
    locked_positions = locked_positions or {}
    locked_ids = frozenset(locked_positions)
    solutions = []
    for phrase in phrases:
        candidates = tuple(
            (
                (locked_positions[note.id],)
                if note.id in locked_positions
                else possible_positions(note.pitch, tuning, config.max_fret)
            )
            for note in phrase.notes
        )
        solution = solve_phrase(phrase.notes, candidates, config, locked_ids)
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

