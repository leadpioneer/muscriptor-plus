"""Guitar fingering arranger (MuScriptor Plus).

A symbolic post-transcription step: given one MIDI track, choose globally
convenient string/fret positions for every note with dynamic programming over
musical phrases. Onsets, durations and velocities are never modified. By
default the part is first normalized to the standard tuning: a global
transposition (for detuned recordings) and the removal of out-of-range
octave duplicates, both reported in the document; `normalize=False` disables
that and makes out-of-range notes a plain error. Unsupported input (an
ambiguous track choice, onsets with more notes than strings under
`chord_overflow="error"`, contradictory locks) fails with an explicit error
instead of a silent fallback.

The package is pure Python: no filesystem access, no FastAPI, no torch.
"""

from .errors import (
    AmbiguousTrackError,
    FingeringExportError,
    GuitarArrangementError,
    IncompatibleChordLocksError,
    InvalidArrangementError,
    InvalidMelodyPolicyError,
    InvalidOverridesError,
    MidiParseError,
    PolyphonicInputError,
    TooManyChordNotesError,
    TrackNotFoundError,
    UnplayableChordError,
    UnplayableNoteError,
    UnsupportedArrangementError,
)
from .events import analyze_polyphony, group_into_events
from .chords import generate_chord_shapes
from .harmony import detect_chord_labels
from .fretboard import (
    STANDARD_TUNING,
    possible_fingerings,
    possible_positions,
    resolve_tuning,
)
from .melody import MELODY_POLICIES, reduce_to_melody
from .normalize import normalize_to_tuning
from .midi_input import (
    DRUM_CHANNEL,
    ParsedMidi,
    TrackInfo,
    check_monophonic,
    parse_midi,
    select_notes,
)
from .models import (
    ArrangementSolution,
    AssignedEvent,
    AssignedNote,
    BarreState,
    ChordFingeringState,
    ChordLabel,
    ChordNoteState,
    ChordReduction,
    DroppedNote,
    FingeringState,
    FretPosition,
    GuitarTuning,
    MelodyReduction,
    MidiNote,
    Normalization,
    NoteEvent,
    Phrase,
    PhraseSolution,
    PolyphonyAnalysis,
    SolverConfig,
    SourceInfo,
    TempoEvent,
    TimeSignatureEvent,
)
from .tab import arrangement_json_to_tab
from .to_midi import arrangement_json_to_midi
from .musicxml import arrangement_json_to_musicxml
from .phrases import split_event_phrases, split_phrases
from .pipeline import arrange, arrange_solution
from .serialization import OVERRIDES_VERSION, SCHEMA_VERSION, parse_overrides, to_json
from .solver import (
    chord_open_string_penalty,
    chord_transition_cost,
    event_overlaps_others,
    explain_chord_lines,
    explain_lines,
    solve_event_phrase,
    solve_event_phrases,
    solve_phrase,
    solve_phrases,
)

__all__ = [
    "SCHEMA_VERSION",
    "OVERRIDES_VERSION",
    "DRUM_CHANNEL",
    "STANDARD_TUNING",
    "AmbiguousTrackError",
    "ArrangementSolution",
    "AssignedEvent",
    "AssignedNote",
    "BarreState",
    "ChordFingeringState",
    "ChordLabel",
    "ChordNoteState",
    "ChordReduction",
    "DroppedNote",
    "FingeringExportError",
    "FingeringState",
    "FretPosition",
    "GuitarArrangementError",
    "GuitarTuning",
    "IncompatibleChordLocksError",
    "InvalidArrangementError",
    "InvalidMelodyPolicyError",
    "InvalidOverridesError",
    "MELODY_POLICIES",
    "MelodyReduction",
    "MidiNote",
    "MidiParseError",
    "Normalization",
    "NoteEvent",
    "ParsedMidi",
    "Phrase",
    "PhraseSolution",
    "PolyphonicInputError",
    "PolyphonyAnalysis",
    "SolverConfig",
    "SourceInfo",
    "TempoEvent",
    "TimeSignatureEvent",
    "TooManyChordNotesError",
    "TrackInfo",
    "TrackNotFoundError",
    "UnplayableChordError",
    "UnplayableNoteError",
    "UnsupportedArrangementError",
    "analyze_polyphony",
    "arrange",
    "arrange_solution",
    "arrangement_json_to_midi",
    "arrangement_json_to_musicxml",
    "arrangement_json_to_tab",
    "check_monophonic",
    "chord_open_string_penalty",
    "chord_transition_cost",
    "detect_chord_labels",
    "event_overlaps_others",
    "explain_chord_lines",
    "explain_lines",
    "generate_chord_shapes",
    "group_into_events",
    "normalize_to_tuning",
    "parse_midi",
    "parse_overrides",
    "possible_fingerings",
    "possible_positions",
    "reduce_to_melody",
    "resolve_tuning",
    "select_notes",
    "solve_event_phrase",
    "solve_event_phrases",
    "solve_phrase",
    "solve_phrases",
    "split_event_phrases",
    "split_phrases",
    "to_json",
]
