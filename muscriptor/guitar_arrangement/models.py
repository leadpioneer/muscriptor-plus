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

    # --- Chord (polyphonic onset event) weights and limits, v3 ---
    # Max fret distance between the highest and lowest closed note of one
    # shape; shapes needing a wider stretch are not generated at all.
    max_chord_fret_span: int = 3
    # Cap on retained ChordFingeringState candidates per event; pruning is
    # deterministic (lowest shape cost, then the canonical sort key) and the
    # generated/pruned counts are reported, so an optimum is never silently
    # claimed over discarded states.
    max_chord_candidates: int = 24
    # Cost of the closed-fret span (max fret minus min fret) inside one shape.
    chord_span_weight: float = 0.4
    # Cost per string covered by a barre.
    barre_weight: float = 0.3
    # Cost per open string in a shape; 0.0 by default — an open string is
    # never penalized as a mistake.
    open_string_weight: float = 0.0
    # Open strings are idiomatic while the hand sits near the nut: a solo
    # (non-overlapping) open-string note with the hand above this position
    # gets `open_string_far_penalty`. Chords, async overlaps and locked notes
    # are always exempt.
    open_string_free_position: int = 3
    open_string_far_penalty: float = 4.0
    # Transition cost of the string-area change between two chord shapes,
    # measured on the used-string centre (v2's |Δstring| only makes sense
    # between single notes).
    string_movement_weight: float = 0.2
    # Shape cost added when the finger annotation could not label every
    # closed note (small but clearly noticeable).
    incomplete_finger_weight: float = 1.0

    @property
    def hand_position_limit(self) -> int:
        if self.max_hand_position is not None:
            return self.max_hand_position
        return max(1, self.max_fret - 3)


@dataclass(frozen=True)
class TempoEvent:
    """A global `set_tempo` meta event: microseconds per beat.

    `is_default` marks the standard-MIDI fallback (500000 µs/beat) used when
    the file carries no tempo at all — consumers can tell source data from a
    synthesized default.
    """

    tick: int
    tempo: int
    is_default: bool = False


@dataclass(frozen=True)
class TimeSignatureEvent:
    """A global `time_signature` meta event."""

    tick: int
    numerator: int
    denominator: int
    clocks_per_click: int = 24
    notated_32nd_notes_per_beat: int = 8
    is_default: bool = False


@dataclass(frozen=True)
class SourceInfo:
    """Which track/channel of which file the arrangement was built from.

    The tempo and time-signature maps are global MIDI meta events (usually in
    track 0, often a conductor track that carries no notes); they are kept for
    the schema-v3 document and the MIDI export. Missing maps fall back to the
    standard MIDI defaults (500000 µs/beat, 4/4) marked `is_default=True` —
    a default is never silently passed off as source data.
    """

    filename: str
    ticks_per_beat: int
    track_index: int
    track_name: str | None
    channel: int
    program: int | None
    tempo_events: tuple[TempoEvent, ...] = ()
    time_signature_events: tuple[TimeSignatureEvent, ...] = ()


@dataclass(frozen=True)
class PhraseSolution:
    """The solver's output for one phrase.

    `assigned` keeps the flat per-note view (v2 consumers); `events` carries
    the v3 chord structure — one AssignedEvent per onset tick, including
    singleton events.
    """

    index: int
    start_tick: int
    end_tick: int
    cost: float
    assigned: tuple[AssignedNote, ...]
    events: "tuple[AssignedEvent, ...]" = ()
    fret_travel: int = 0
    string_travel: int = 0


@dataclass(frozen=True)
class MelodyReduction:
    """What a melody reduction did, for the arrangement JSON.

    Produced by `melody.reduce_to_melody` and attached to the solution when
    the caller chose a non-`off` melody policy.
    """

    policy: str
    dropped: tuple[MidiNote, ...]

    @property
    def dropped_note_count(self) -> int:
        return len(self.dropped)

    def to_dict(self) -> dict:
        return {
            "policy": self.policy,
            "dropped_note_count": self.dropped_note_count,
            "dropped": [
                {"tick": note.onset_ticks, "pitch": note.pitch}
                for note in self.dropped
            ],
        }


@dataclass(frozen=True)
class NoteEvent:
    """Every note that starts at one MIDI tick (a chord, dyad or single note).

    Notes are ordered by `(pitch descending, note_id)` — one fixed rule, the
    same order the chord solver and the JSON keep everywhere. Events carry no
    duration of their own: each note keeps its own onset/offset, so a ringing
    note is never trimmed to fit the next event.
    """

    index: int
    onset_ticks: int
    notes: tuple[MidiNote, ...]

    @property
    def note_ids(self) -> tuple[str, ...]:
        return tuple(note.id for note in self.notes)

    @property
    def pitches(self) -> tuple[int, ...]:
        return tuple(note.pitch for note in self.notes)

    @property
    def last_offset_ticks(self) -> int:
        return max(note.offset_ticks for note in self.notes)


@dataclass(frozen=True)
class PolyphonyAnalysis:
    """A deterministic description of how polyphonic the input is.

    Reported in the schema-v3 document and the CLI's --explain output; never
    used to remove notes. `overlapping_region_count` counts the elementary
    intervals of the timeline (split at every onset and offset tick) where two
    or more notes sound at once. `strictly_monophonic` is true when at most
    one note is ever active — simultaneous onsets included.
    """

    note_count: int
    onset_event_count: int
    polyphonic_event_count: int
    largest_onset_group: int
    overlapping_region_count: int
    max_active_notes: int
    strictly_monophonic: bool

    def to_dict(self) -> dict:
        return {
            "note_count": self.note_count,
            "onset_event_count": self.onset_event_count,
            "polyphonic_event_count": self.polyphonic_event_count,
            "largest_onset_group": self.largest_onset_group,
            "overlapping_region_count": self.overlapping_region_count,
            "max_active_notes": self.max_active_notes,
            "strictly_monophonic": self.strictly_monophonic,
        }


@dataclass(frozen=True)
class ChordNoteState:
    """One note of a chord shape: which string/fret sounds it, which finger."""

    note_id: str
    pitch: int
    position: FretPosition
    # None when the finger allocator could not label this note; the shape
    # stays valid (string/fret are what matters) and the state is flagged
    # via ChordFingeringState.finger_assignment_complete.
    finger: int | None


@dataclass(frozen=True)
class BarreState:
    """One finger lying across several strings at one fret.

    Emitted only when no open string of the same event sounds between
    `from_string` and `to_string` — a barre across a ringing open string is
    not something the annotation may claim.
    """

    finger: int
    fret: int
    from_string: int
    to_string: int
    note_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChordFingeringState:
    """A complete left-hand state for one onset event (1–6 notes).

    This is the DP state of the v3 solver: the whole chord is the unit, and
    the solver picks one shape per event, never per note. `notes` keeps the
    event's `(pitch desc, note_id)` order; `shape_cost` is the intrinsic cost
    of the shape itself (span, barres, high position, incomplete annotation).
    """

    event_index: int
    onset_ticks: int
    notes: tuple[ChordNoteState, ...]
    hand_position: int
    barres: tuple[BarreState, ...]
    shape_cost: float
    finger_assignment_complete: bool = True

    @property
    def positions(self) -> tuple[FretPosition, ...]:
        return tuple(n.position for n in self.notes)

    @property
    def closed_frets(self) -> tuple[int, ...]:
        return tuple(n.position.fret for n in self.notes if n.position.fret > 0)

    @property
    def has_open_string(self) -> bool:
        return any(n.position.fret == 0 for n in self.notes)

    def sort_key(self) -> tuple:
        """Canonical deterministic order of shapes at one event."""
        return (
            round(self.shape_cost, 6),
            self.hand_position,
            tuple((n.position.string, n.position.fret, n.finger or -1) for n in self.notes),
        )


@dataclass(frozen=True)
class AssignedEvent:
    """An onset event together with the solver's chosen chord shape."""

    event: NoteEvent
    state: ChordFingeringState
    generated_candidates: int
    pruned_candidates: int


@dataclass(frozen=True)
class ArrangementSolution:
    """Everything the JSON serializer needs, no more."""

    source: SourceInfo
    tuning: GuitarTuning
    config: SolverConfig
    phrases: tuple[PhraseSolution, ...]
    polyphony: PolyphonyAnalysis
    # Set when the input was reduced to one melodic line before solving
    # (melody policy `top`/`bottom`); None when no reduction ran.
    melody_reduction: MelodyReduction | None = None
