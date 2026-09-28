"""Errors raised by the guitar arrangement module.

Follows the project-wide convention (see `muscriptor.preprocessing.errors`):
every message is written for the person reading it. The CLI prints `str(e)`
to stderr as-is; the HTTP endpoint wraps it into a structured
`{"code", "message", "details"}` payload using the `code` and `details`
attributes below.
"""


class GuitarArrangementError(Exception):
    """Base class for guitar arrangement failures."""

    code = "guitar_arrangement_error"
    details: dict = {}

    def __init__(self, message: str) -> None:
        super().__init__(message)


class MidiParseError(GuitarArrangementError):
    """The upload is not a readable Standard MIDI File."""

    code = "invalid_midi"


class TrackNotFoundError(GuitarArrangementError):
    """No note-bearing track/channel matched the request."""

    code = "track_not_found"


class AmbiguousTrackError(GuitarArrangementError):
    """Several note-bearing tracks exist and the caller did not pick one.

    `details["tracks"]` carries the track/channel summaries so a CLI user or
    an API client can choose a `--track`/`--channel` pair. Selection is never
    guessed from track names.
    """

    code = "ambiguous_track"

    def __init__(self, message: str, candidates: list[dict]) -> None:
        super().__init__(message)
        self.details = {"tracks": candidates}


class PolyphonicInputError(GuitarArrangementError):
    """Two or more different notes start at the same tick.

    Version 1 arranges a single melodic line; simultaneous onsets are refused
    instead of silently picking (e.g.) the top note. Overlapping durations
    with distinct onsets are fine and do not trigger this.

    Since v3 the chord solver handles 1–6 simultaneous onsets, so this error
    is only raised by the explicit `check_monophonic` helper (kept for the
    legacy monophonic path and its tests) — never by the default pipeline.
    """

    code = "polyphonic_input"

    def __init__(
        self, message: str, tick: int, note_ids: list[str], pitches: list[int]
    ) -> None:
        super().__init__(message)
        self.details = {
            "tick": tick,
            "note_ids": note_ids,
            "pitches": pitches,
        }


class UnplayableNoteError(GuitarArrangementError):
    """A note's pitch cannot be produced anywhere on the tuned fretboard."""

    code = "unplayable_note"

    def __init__(
        self, message: str, pitch: int, low_pitch: int, high_pitch: int
    ) -> None:
        super().__init__(message)
        self.details = {
            "pitch": pitch,
            "low_pitch": low_pitch,
            "high_pitch": high_pitch,
        }


class InvalidOverridesError(GuitarArrangementError):
    """The overrides document is malformed or contradicts the MIDI input."""

    code = "invalid_overrides"


class InvalidMelodyPolicyError(GuitarArrangementError):
    """The requested melody reduction policy is not one of off/top/bottom."""

    code = "invalid_melody_policy"


class InvalidArrangementError(GuitarArrangementError):
    """The arrangement document is not a readable schema-v2/v3 JSON."""

    code = "invalid_arrangement"


class TooManyChordNotesError(GuitarArrangementError):
    """An onset event starts more notes than the instrument has strings.

    Nothing is dropped: the error lists the event so the caller can reduce it
    explicitly (melody top/bottom) or fix the input.
    """

    code = "too_many_chord_notes"

    def __init__(
        self,
        message: str,
        onset_ticks: int,
        note_ids: list[str],
        pitches: list[int],
        available_strings: int,
    ) -> None:
        super().__init__(message)
        self.details = {
            "onset_ticks": onset_ticks,
            "note_ids": note_ids,
            "pitches": pitches,
            "available_strings": available_strings,
        }


class UnplayableChordError(GuitarArrangementError):
    """No string assignment can sound every note of one onset event.

    Every note is individually playable, but not on distinct strings at the
    same time (e.g. two identical pitches with only one possible position).
    """

    code = "unplayable_chord"

    def __init__(
        self,
        message: str,
        onset_ticks: int,
        note_ids: list[str],
        pitches: list[int],
        available_strings: int,
        reason: str = "",
    ) -> None:
        super().__init__(message)
        self.details = {
            "onset_ticks": onset_ticks,
            "note_ids": note_ids,
            "pitches": pitches,
            "available_strings": available_strings,
            "reason": reason,
        }


class IncompatibleChordLocksError(GuitarArrangementError):
    """The locks of one chord event contradict each other.

    Two locks on the same string, or locks that leave no legal completion for
    the remaining notes of the event.
    """

    code = "incompatible_chord_locks"

    def __init__(
        self, message: str, onset_ticks: int, note_ids: list[str], strings: list[int]
    ) -> None:
        super().__init__(message)
        self.details = {
            "onset_ticks": onset_ticks,
            "note_ids": note_ids,
            "strings": strings,
        }


class UnsupportedArrangementError(GuitarArrangementError):
    """The arrangement document's schema_version is not supported."""

    code = "unsupported_arrangement_schema"


class FingeringExportError(GuitarArrangementError):
    """The fingering-preserving engraving failed after MuseScore ran."""

    code = "fingering_export_failed"
