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
    InvalidOverridesError,
    MidiParseError,
    PolyphonicInputError,
    TrackNotFoundError,
    UnplayableNoteError,
)
from .fretboard import STANDARD_TUNING, possible_positions, resolve_tuning
from .midi_input import DRUM_CHANNEL, ParsedMidi, TrackInfo, parse_midi, select_notes
from .models import (
    ArrangementSolution,
    AssignedNote,
    FretPosition,
    GuitarTuning,
    MidiNote,
    Phrase,
    PhraseSolution,
    SolverConfig,
    SourceInfo,
)
from .phrases import split_phrases
from .midi_input import check_monophonic
from .pipeline import arrange
from .serialization import OVERRIDES_VERSION, SCHEMA_VERSION, parse_overrides, to_json
from .solver import solve_phrase, solve_phrases

__all__ = [
    "SCHEMA_VERSION",
    "OVERRIDES_VERSION",
    "DRUM_CHANNEL",
    "STANDARD_TUNING",
    "AmbiguousTrackError",
    "ArrangementSolution",
    "AssignedNote",
    "FretPosition",
    "GuitarArrangementError",
    "GuitarTuning",
    "InvalidOverridesError",
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
    "check_monophonic",
    "parse_midi",
    "parse_overrides",
    "possible_positions",
    "resolve_tuning",
    "select_notes",
    "solve_phrase",
    "solve_phrases",
    "split_phrases",
    "to_json",
]
