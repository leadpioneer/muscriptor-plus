"""Fretboard geometry: positions and ergonomic fingerings for a pitch."""

from .errors import InvalidOverridesError, UnplayableNoteError
from .models import FingeringState, FretPosition, GuitarTuning, SolverConfig

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


def possible_fingerings(
    position: FretPosition, config: SolverConfig
) -> tuple[FingeringState, ...]:
    """Every ergonomic `FingeringState` that sounds `position`, deterministically
    ordered (ascending finger for closed notes; ascending hand position for
    open ones).

    Closed note: `hand_position = fret - finger + 1` for fingers 1–4, clamped
    to `1 <= hand_position <= hand_position_limit` — a note on the 7th fret is
    reachable by finger 1 in position 7, finger 2 in position 6, and so on.
    Open string: `finger = 0` and the hand may sit anywhere in range, so the
    states cover every valid `hand_position` — the DP can keep the current
    hand position or move it while the open string rings. The state count
    stays bounded by `hand_position_limit` (≤ max_fret − 3 by default).
    """
    limit = config.hand_position_limit
    if position.fret == 0:
        return tuple(
            FingeringState(position=position, hand_position=hp, finger=0)
            for hp in range(1, limit + 1)
        )
    states = []
    for finger in (1, 2, 3, 4):
        hand_position = position.fret - finger + 1
        if 1 <= hand_position <= limit:
            states.append(
                FingeringState(
                    position=position, hand_position=hand_position, finger=finger
                )
            )
    return tuple(states)
