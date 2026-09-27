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
class AssignedNote:
    """A note together with the solver's (or the user's) chosen position."""

    note: MidiNote
    position: FretPosition
    legal_positions: tuple[FretPosition, ...]
    locked: bool = False


@dataclass(frozen=True)
class Phrase:
    """A maximal run of notes optimized independently of the other phrases."""

    index: int
    notes: tuple[MidiNote, ...]


@dataclass(frozen=True)
class SolverConfig:
    """Cost weights of the dynamic-programming solver.

    Transition penalties must dominate the high-fret penalty, otherwise the
    solver degenerates into per-note greedy low-fret picking.
    """

    max_fret: int = 24
    phrase_gap_beats: float = 1.0
    # |Δfret| between neighbours.
    fret_movement_weight: float = 1.0
    # |Δstring| between neighbours.
    string_movement_weight: float = 0.5
    # |Δfret| + |Δstring| beyond this counts as a hand jump and costs extra
    # per extra semitone/step of movement.
    large_position_change_threshold: int = 3
    large_position_change_weight: float = 2.0
    # Frets above this cost a little each; weak on purpose.
    high_fret_start: int = 12
    high_fret_weight: float = 0.02


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
