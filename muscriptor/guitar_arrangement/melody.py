"""Deterministic monophonic reduction: pick one melodic line from polyphony.

Real transcription output (and any DAW export) almost always contains at
least a few double stops or chords, which a single-line arranger must refuse.
Rather than guessing silently, the caller chooses an explicit policy:

- `off`    — no reduction; polyphonic input keeps raising `PolyphonicInputError`.
- `top`    — skyline: in every simultaneous-onset group keep the highest note.
- `bottom` — keep the lowest note.

The reduction is pure and deterministic: kept notes keep their identity (ids,
onsets, offsets, velocities are untouched), only whole notes of a conflicting
group are dropped — timings are never trimmed. Every dropped note is reported,
so the arrangement JSON can show exactly what was taken out.
"""

from .models import MelodyReduction, MidiNote

MELODY_POLICIES = ("off", "top", "bottom")


def _keep(policy: str, group: list[MidiNote]) -> MidiNote:
    if policy == "top":
        return max(group, key=lambda n: n.pitch)
    return min(group, key=lambda n: n.pitch)


def reduce_to_melody(
    notes: tuple[MidiNote, ...], policy: str
) -> tuple[tuple[MidiNote, ...], MelodyReduction]:
    """Reduce the note stream to one melodic line under `policy`.

    Notes are grouped by onset tick; a group larger than one loses all but
    one member (the highest for `top`, the lowest for `bottom`, ties on equal
    pitch keep the first in input order). Unisons — the same tick AND pitch —
    collapse to a single note. Kept notes keep their original ordering and
    identity, so note ids stay stable for locks and the editor.
    """
    if policy not in MELODY_POLICIES:
        raise ValueError(
            f"unknown melody policy {policy!r} (expected one of {MELODY_POLICIES})"
        )
    by_onset: dict[int, list[MidiNote]] = {}
    for note in notes:
        by_onset.setdefault(note.onset_ticks, []).append(note)

    kept: list[MidiNote] = []
    dropped: list[MidiNote] = []
    for tick in sorted(by_onset):
        group = by_onset[tick]
        if len(group) == 1:
            kept.append(group[0])
            continue
        winner = _keep(policy, group)
        kept.append(winner)
        for note in group:
            if note is not winner:
                dropped.append(note)
    return tuple(kept), MelodyReduction(policy=policy, dropped=tuple(dropped))
