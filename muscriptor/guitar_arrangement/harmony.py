"""Jazz chord-symbol detection over a finished arrangement.

The input is the note timeline after normalization and reduction — melody and
accompaniment together, exactly as the tab plays it. The detector walks the
meter's beat grid, and for every beat collects the notes sounding in that
window, duration-weighted with a discount for notes that merely ring over
from the previous beat (fresh attacks decide the label, sustained bass is
still heard).

For each window every (root, quality) pair from a compact jazz vocabulary is
scored:

- chord tones that sound add support (their share of the window's weight);
- sounding notes outside the chord (a melody playing through, say) cost a
  penalty, but never veto the label;
- a chord tone that does not sound at all costs a smaller penalty, so a
  sparse voicing (root + third only) still gets a sensible name;
- the bass sounding the root is a bonus, which is also what disambiguates
  pitch-class twins like Am7 vs C6.

Consecutive beats with the same label merge into one segment, and a one-beat
blip between two identical labels is absorbed (A B A → A). The result is
deterministic: roots are tried in pitch-class order and the vocabulary is
declared simplest-first, so ties are stable.

Nothing here changes the music — the labels are derived data for display
(MusicXML `<harmony>` symbols) and are reported in the arrangement JSON's
`chords` block.
"""

from collections import defaultdict
from typing import Sequence

from .models import ChordLabel, MidiNote


class _Template:
    __slots__ = ("code", "suffix", "intervals")

    def __init__(self, code: str, suffix: str, intervals: tuple[int, ...]):
        self.code = code
        self.suffix = suffix
        self.intervals = intervals


# Declared simplest-first: it is also the deterministic tie-break order.
_TEMPLATES = (
    _Template("maj", "", (0, 4, 7)),
    _Template("m", "m", (0, 3, 7)),
    _Template("7", "7", (0, 4, 7, 10)),
    _Template("maj7", "maj7", (0, 4, 7, 11)),
    _Template("m7", "m7", (0, 3, 7, 10)),
    _Template("6", "6", (0, 4, 7, 9)),
    _Template("m6", "m6", (0, 3, 7, 9)),
    _Template("dim", "dim", (0, 3, 6)),
    _Template("dim7", "dim7", (0, 3, 6, 9)),
    _Template("m7b5", "m7b5", (0, 3, 6, 10)),
    _Template("sus2", "sus2", (0, 2, 7)),
    _Template("sus4", "sus4", (0, 5, 7)),
    _Template("add9", "add9", (0, 2, 4, 7)),
    _Template("madd9", "madd9", (0, 2, 3, 7)),
)

# Preferred spellings (jazz default: flats, except F#/C# which read better
# sharp); index == pitch class.
_ROOT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")

_EXTRA_PENALTY = 0.6  # a sounding note outside the chord
_MISSING_PENALTY = 0.5  # a chord tone that does not sound at all
_ROOT_BASS_BONUS = 0.1  # the lowest sounding note is the root
_SUSTAIN_DISCOUNT = 0.5  # a note ringing over from the previous beat
_MIN_SCORE = 0.5


def _meta_get(event, key: str, default):
    """Read a field from a dataclass-like or dict meta event."""
    if isinstance(event, dict):
        return event.get(key, default)
    return getattr(event, key, default)


def _beat_windows(time_signatures, ticks_per_beat: int, total_ticks: int):
    """(start, end) windows, one per beat, from the meter map (4/4 default)."""
    signatures = sorted(
        (e for e in (time_signatures or []) if e is not None),
        key=lambda e: _meta_get(e, "tick", 0),
    )
    if not signatures or _meta_get(signatures[0], "tick", 0) > 0:
        signatures = [{"tick": 0, "numerator": 4, "denominator": 4}, *signatures]
    windows: list[tuple[int, int]] = []
    current = 0
    index = 0
    while current < total_ticks:
        while (
            index + 1 < len(signatures)
            and _meta_get(signatures[index + 1], "tick", 0) <= current
        ):
            index += 1
        signature = signatures[index]
        numerator = max(1, int(_meta_get(signature, "numerator", 4)))
        denominator = max(1, int(_meta_get(signature, "denominator", 4)))
        bar_ticks = max(1, int(round(numerator * 4 / denominator * ticks_per_beat)))
        beat_ticks = max(1, bar_ticks // numerator)
        for beat in range(numerator):
            start = current + beat * beat_ticks
            if start >= total_ticks:
                break
            windows.append((start, min(start + beat_ticks, total_ticks)))
        current += bar_ticks
    return windows


def _label_window(notes: Sequence[MidiNote], start: int, end: int):
    """Best chord for one window, or None when nothing conclusive sounds.

    Returned as `(label, root_name, kind, bass_name_or_None)`; the caller
    attaches the segment tick.
    """
    weights: dict[int, float] = defaultdict(float)
    lowest_pitch: int | None = None
    for note in notes:
        overlap_start = max(note.onset_ticks, start)
        overlap_end = min(note.offset_ticks, end)
        if overlap_end <= overlap_start:
            continue
        weight = float(overlap_end - overlap_start)
        if note.onset_ticks < start:
            weight *= _SUSTAIN_DISCOUNT
        weights[note.pitch % 12] += weight
        if lowest_pitch is None or note.pitch < lowest_pitch:
            lowest_pitch = note.pitch
    total = sum(weights.values())
    # Fewer than three distinct pitch classes is a dyad or a cluster
    # (power-chord fifths, doubled roots, chromatic neighbours): naming
    # those as jazz chords says nothing useful.
    if total <= 0 or len(weights) < 3:
        return None
    bass_pc = lowest_pitch % 12

    best = None
    for root in range(12):
        for template in _TEMPLATES:
            tones = {(root + interval) % 12 for interval in template.intervals}
            present = sum(weights.get(pc, 0.0) for pc in tones)
            extra = total - present
            missing = sum(1 for pc in tones if weights.get(pc, 0.0) <= 0)
            score = (
                present / total
                - _EXTRA_PENALTY * (extra / total)
                - _MISSING_PENALTY * (missing / len(template.intervals))
            )
            if root == bass_pc:
                score += _ROOT_BASS_BONUS
            if best is None or score > best[0] + 1e-12:
                best = (score, root, template)
    score, root, template = best
    if score < _MIN_SCORE:
        return None

    bass_name = None
    if bass_pc != root and bass_pc in {
        (root + interval) % 12 for interval in template.intervals
    }:
        # Only chord-tone basses become slash chords; a passing melody note
        # in the bass register must not invent an inversion.
        bass_name = _ROOT_NAMES[bass_pc]
    root_name = _ROOT_NAMES[root]
    label = root_name + template.suffix + (f"/{bass_name}" if bass_name else "")
    return label, root_name, template.code, bass_name


def detect_chord_labels(
    notes: Sequence[MidiNote], ticks_per_beat: int, time_signatures=()
) -> tuple[ChordLabel, ...]:
    """Detect one chord label per harmonic segment (deterministic)."""
    notes = tuple(notes)
    if not notes or ticks_per_beat <= 0:
        return ()
    total_ticks = max(note.offset_ticks for note in notes)
    raw: list[tuple[int, tuple | None]] = []
    for start, end in _beat_windows(time_signatures, ticks_per_beat, total_ticks):
        raw.append((start, _label_window(notes, start, end)))

    # Drop silent windows, then absorb a one-window blip between two equal
    # labels (A B A → A) before collapsing runs.
    items = [(tick, found) for tick, found in raw if found is not None]
    index = 1
    while index < len(items) - 1:
        previous = items[index - 1][1][0]
        following = items[index + 1][1][0]
        if previous == following and items[index][1][0] != previous:
            items[index] = (items[index][0], items[index - 1][1])
        index += 1

    labels: list[ChordLabel] = []
    for tick, (label, root_name, kind, bass_name) in items:
        if labels and labels[-1].label == label:
            continue
        labels.append(
            ChordLabel(
                tick=tick, label=label, root=root_name, kind=kind, bass=bass_name
            )
        )
    return tuple(labels)
