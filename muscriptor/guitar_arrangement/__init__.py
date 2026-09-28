"""Guitar fingering arranger (MuScriptor Plus).

A symbolic post-transcription step: given one monophonic MIDI track, choose
globally convenient string/fret positions for every note with dynamic
programming over musical phrases. Pitch, onset and duration are never
modified; unsupported input (polyphony, unplayable pitches, ambiguous track
selection) fails with an explicit error instead of a silent fallback.

The package is pure Python: no filesystem access, no FastAPI, no torch.
"""

from .errors import (
    AmbiguousTrackError,
    GuitarArrangementError,
    InvalidArrangementError,
    InvalidMelodyPolicyError,
    InvalidOverridesError,
    MidiParseError,
    PolyphonicInputError,
    TrackNotFoundError,
    UnplayableNoteError,
)
from .fretboard import (
    STANDARD_TUNING,
    possible_fingerings,
    possible_positions,
    resolve_tuning,
)
from .melody import MELODY_POLICIES, reduce_to_melody
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
    AssignedNote,
    FingeringState,
    FretPosition,
    GuitarTuning,
    MelodyReduction,
    MidiNote,
    Phrase,
    PhraseSolution,
    SolverConfig,
    SourceInfo,
)
from .tab import arrangement_json_to_tab
from .to_midi import arrangement_json_to_midi
from .phrases import split_phrases
from .pipeline import arrange, arrange_solution
from .serialization import OVERRIDES_VERSION, SCHEMA_VERSION, parse_overrides, to_json
from .solver import explain_lines, solve_phrase, solve_phrases

__all__ = [
    "SCHEMA_VERSION",
    "OVERRIDES_VERSION",
    "DRUM_CHANNEL",
    "STANDARD_TUNING",
    "AmbiguousTrackError",
    "ArrangementSolution",
    "AssignedNote",
    "FingeringState",
    "FretPosition",
    "GuitarArrangementError",
    "GuitarTuning",
    "InvalidMelodyPolicyError",
    "InvalidOverridesError",
    "MELODY_POLICIES",
    "MelodyReduction",
    "MidiNote",
    "MidiParseError",
    "ParsedMidi",
    "Phrase",
    "PhraseSolution",
    "PolyphonicInputError",
    "SolverConfig",
    "SourceInfo",
    "TrackInfo",
    "TrackNotFoundError",
    "UnplayableNoteError",
    "arrange",
    "arrange_solution",
    "arrangement_json_to_midi",
    "arrangement_json_to_tab",
    "check_monophonic",
    "explain_lines",
    "parse_midi",
    "parse_overrides",
    "possible_fingerings",
    "possible_positions",
    "reduce_to_melody",
    "resolve_tuning",
    "select_notes",
    "solve_phrase",
    "solve_phrases",
    "split_phrases",
    "to_json",
]
