"""Fretboard geometry: which string/fret spots can sound a given pitch."""

from .errors import InvalidOverridesError, UnplayableNoteError
from .models import FretPosition, GuitarTuning

STANDARD_TUNING = GuitarTuning(
    name="standard",
    # String 1 (highest) first: E4, B3, G3, D3, A2, E2.
    open_pitches=(64, 59, 55, 50, 45, 40),
)

_TUNINGS = {"standard": STANDARD_TUNING}


def resolve_tuning(name: str) -> GuitarTuning:
    """Preset lookup by name; the only place that knows the preset names."""
    try:
        return _TUNINGS[name]
    except KeyError:
        known = ", ".join(sorted(_TUNINGS))
        raise InvalidOverridesError(
            f"unknown tuning {name!r} (available: {known})"
        ) from None


def possible_positions(
    pitch: int, tuning: GuitarTuning, max_fret: int
) -> tuple[FretPosition, ...]:
    """Every string/fret combination that sounds `pitch`, deterministically
    sorted by (fret, string).

    `fret = pitch - open_pitch` must satisfy `0 <= fret <= max_fret`; no
    octave transposition is ever applied. Raises `UnplayableNoteError` with
    the pitch and the instrument's playable range when nothing fits.
    """
    positions = [
        FretPosition(string=number, fret=pitch - open_pitch)
        for number, open_pitch in enumerate(tuning.open_pitches, start=1)
        if 0 <= pitch - open_pitch <= max_fret
    ]
    if not positions:
        low = tuning.low_pitch
        high = low + max_fret
        raise UnplayableNoteError(
            f"pitch {pitch} cannot be played: the tuned range is MIDI "
            f"{low}–{high} (max_fret={max_fret}) and octave transposition "
            "is never applied automatically",
            pitch=pitch,
            low_pitch=low,
            high_pitch=high,
        )
    return tuple(sorted(positions, key=lambda p: (p.fret, p.string)))
