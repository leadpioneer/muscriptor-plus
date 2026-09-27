"""Data model for the guitar fingering arranger.

All types are small frozen dataclasses; the solver and its callers never pass
unstructured dicts around. Everything here is pure: no files, no network, no
torch.

String numbering (used consistently across the module, the CLI and the JSON
output): **string 1 is the highest-sounding string**. For the standard
six-string guitar (see `fretboard.STANDARD_TUNING`) that is 1: E4 (MIDI 64),
2: B3 (59), 3: G3 (55), 4: D3 (50), 5: A2 (45), 6: E2 (40). `FretPosition.string`
is this user-facing number, never an array index; `GuitarTuning.open_pitches`
is indexed by `string - 1`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MidiNote:
    """One note as read from the source MIDI file.

    `id` is derived from the source track index, channel and the order of the
    note-on event within the source track — it never depends on solver output.
    `onset_ticks`/`offset_ticks` are absolute ticks in the source file's time
    base.
    """

    id: str
    track_index: int
    channel: int
    pitch: int
    onset_ticks: int
    offset_ticks: int
    velocity: int


@dataclass(frozen=True)
class FretPosition:
    """A playable spot: `string` is 1-based (1 = highest), `fret` 0-based."""

    string: int
    fret: int


@dataclass(frozen=True)
class GuitarTuning:
    """An instrument tuning; `open_pitches[i]` is the pitch of string `i + 1`."""

    name: str
    open_pitches: tuple[int, ...]

    @property
    def string_count(self) -> int:
        return len(self.open_pitches)

    def open_pitch(self, string: int) -> int:
        """Open pitch of a 1-based string number; raises for unknown strings."""
        if not 1 <= string <= self.string_count:
            raise IndexError(f"unknown string {string}: 1..{self.string_count}")
        return self.open_pitches[string - 1]

    @property
    def low_pitch(self) -> int:
        """Lowest playable pitch: the lowest open string."""
        return min(self.open_pitches)

    @property
    def high_pitch(self) -> int:
        """Highest playable pitch: lowest string + max fret (set per config)."""
        return max(self.open_pitches)


@dataclass(frozen=True)
class FingeringState:
    """A fully specified left-hand state for one note.

    `position` is where the note sounds; `hand_position` is the fret the
    index finger is at; `finger` is 0 for an open string, 1–4 for
    index/middle/ring/pinky. For a closed note the base relation is
    `finger == fret - hand_position + 1` with `1 <= finger <= 4` and
    `hand_position >= 1` — the first verifiable ergonomic approximation, not
    a complete model of a real hand.
    """

    position: FretPosition
    hand_position: int
    finger: int

    @property
    def is_open(self) -> bool:
        return self.finger == 0


@dataclass(frozen=True)
class AssignedNote:
    """A note together with the solver's (or the user's) chosen fingering."""

    note: MidiNote
    state: FingeringState
    legal_positions: tuple[FretPosition, ...]
    legal_fingerings: tuple[FingeringState, ...]
    locked: bool = False


@dataclass(frozen=True)
class Phrase:
    """A maximal run of notes optimized independently of the other phrases."""

    index: int
    notes: tuple[MidiNote, ...]


@dataclass(frozen=True)
class SolverConfig:
    """Cost weights of the ergonomic dynamic-programming solver (v2).

    The DP state is a `FingeringState` (string, fret, hand position, finger),
    so the cost models hand movement — not just fret deltas of the notes.
    Position-change penalties dominate string crossings; the high-position
    penalty is weak on purpose and must never force an uncomfortable route
    into first position.
    """

    max_fret: int = 24
    phrase_gap_beats: float = 1.0
    # Highest fret the index finger may sit at; None derives it from max_fret
    # (three frets of pinky reach above the last hand position).
    max_hand_position: int | None = None
    # A hand-position shift costs a fixed amount plus a per-fret amount, so
    # one shift of 2 frets is cheaper than two shifts of 1.
    position_change_base: float = 1.5
    position_change_per_fret: float = 0.75
    # Crossing strings in a stable position is much cheaper than moving the
    # hand along the neck.
    string_crossing_weight: float = 0.25
    # Weak penalty for repeating one finger while the fret changes (no model
    # of real finger technique — just avoid the obviously silly).
    finger_repeat_weight: float = 0.1
    # Shifting the hand while an open string rings is cheaper (the left hand
    # is free), but not free.
    open_string_shift_discount: float = 0.5
    # A rest inside a phrase makes a shift cheaper; measured in beats of the
    # source MIDI (never wall-clock). The discount is a factor, not zero.
    rest_gap_beats: float = 0.5
    rest_gap_discount: float = 0.5
    # Weak penalty for playing with the hand far up the neck; anchored to the
    # hand position, not to the note's fret.
    high_position_start: int = 9
    high_position_weight: float = 0.05

    @property
    def hand_position_limit(self) -> int:
        if self.max_hand_position is not None:
            return self.max_hand_position
        return max(1, self.max_fret - 3)


@dataclass(frozen=True)
class SourceInfo:
    """Which track/channel of which file the arrangement was built from."""

    filename: str
    ticks_per_beat: int
    track_index: int
    track_name: str | None
    channel: int
    program: int | None


@dataclass(frozen=True)
class PhraseSolution:
    """The solver's output for one phrase."""

    index: int
    start_tick: int
    end_tick: int
    cost: float
    assigned: tuple[AssignedNote, ...]
    fret_travel: int = 0
    string_travel: int = 0


@dataclass(frozen=True)
class ArrangementSolution:
    """Everything the JSON serializer needs, no more."""

    source: SourceInfo
    tuning: GuitarTuning
    config: SolverConfig
    phrases: tuple[PhraseSolution, ...]
