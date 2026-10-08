"""Fit an arranged part to the target tuning before solving.

Transcriptions frequently disagree with the score's tuning: a guitar recorded
half a step down sounds Eb2 (MIDI 39) where the standard low E is MIDI 40, so
every low root is unplayable. Rather than carrying alternate tuning presets,
every part is normalized here first:

* octave duplicates — an out-of-range note whose exact ±12 twin sounds in the
  same onset event (same offset and velocity) — are candidate transcription
  artefacts;
* the part is then transposed by the smallest offset that brings every
  remaining note into the playable range (that is what a human transcriber
  does with a detuned recording: play it in the written key);
* if some notes still cannot fit with any offset, nothing is changed here and
  the pipeline's range validation reports every offender with its original
  pitch — the normalization must never mask impossible input.

The trade-off between shifting the whole part and dropping doubled notes is
explicit: a semitone of transposition is allowed to "cost" a bounded number
of dropped duplicates (`_SHIFT_COST_IN_DROPS`). A couple of stray doubled
notes are cheaper to drop than to move the whole part, while a systematic
low-string line (dozens of doubled roots) is better fixed by transposing.

Nothing is silent: the chosen transposition and every removed note land in
the arrangement document's `normalization` block.
"""

from dataclasses import replace

from .models import DroppedNote, GuitarTuning, MidiNote, Normalization, SolverConfig

# Two octaves either way is plenty for real transcriptions (a bass part moves
# +12 into the guitar's range); the search stays bounded and deterministic.
_TRANSPOSITION_CANDIDATES = range(-24, 25)

# See the module docstring: below this many duplicates a drop is cheaper than
# a semitone shift, above it the shift wins. Ten leaves room for both the
# "single stray artefact" and the "detuned guitar with doubled roots" cases.
_SHIFT_COST_IN_DROPS = 10


def _event_key(note: MidiNote) -> tuple[int, int, int]:
    """Notes sharing this key can be octave twins of each other."""
    return (note.onset_ticks, note.offset_ticks, note.velocity)


def normalize_to_tuning(
    notes: tuple[MidiNote, ...], tuning: GuitarTuning, config: SolverConfig
) -> tuple[tuple[MidiNote, ...], Normalization]:
    """Return the fitted notes and a report of what was changed.

    When no offset can fit the part (`hard` offenders remain), the notes are
    returned unchanged with an empty report so that the regular range
    validation can list every offender with its original pitch.
    """
    if not notes:
        return notes, Normalization(tuning.name, None, None, 0, ())

    low = tuning.low_pitch
    high = max(tuning.open_pitches) + config.max_fret
    twins: dict[tuple[int, int, int], set[int]] = {}
    for note in notes:
        twins.setdefault(_event_key(note), set()).add(note.pitch)

    def classify(shift: int):
        """Split the part into kept / droppable duplicates / hard offenders."""
        kept: list[MidiNote] = []
        dropped: list[MidiNote] = []
        hard: list[MidiNote] = []
        for note in notes:
            if low <= note.pitch + shift <= high:
                kept.append(note)
                continue
            candidates = twins[_event_key(note)]
            if note.pitch + 12 in candidates or note.pitch - 12 in candidates:
                dropped.append(note)
            else:
                hard.append(note)
        return kept, dropped, hard

    best = None
    for shift in _TRANSPOSITION_CANDIDATES:
        kept, dropped, hard = classify(shift)
        # Impossible notes first; then a bounded trade-off between dropped
        # duplicates and the size of the shift; then prefer the smaller and,
        # on a tie, the positive shift (detuned-down recordings are the
        # common case).
        score = (
            len(hard),
            len(dropped) + _SHIFT_COST_IN_DROPS * abs(shift),
            abs(shift),
            -shift,
        )
        if best is None or score < best[0]:
            best = (score, shift, kept, dropped, hard)
    _score, shift, kept, dropped, hard = best

    source_low = min(note.pitch for note in notes)
    source_high = max(note.pitch for note in notes)
    if hard:
        return notes, Normalization(tuning.name, source_low, source_high, 0, ())

    fitted = tuple(replace(note, pitch=note.pitch + shift) for note in kept)
    report = Normalization(
        target_tuning=tuning.name,
        source_low_pitch=source_low,
        source_high_pitch=source_high,
        transposition_semitones=shift,
        dropped=tuple(
            DroppedNote(note.id, note.pitch, note.onset_ticks, "octave_duplicate")
            for note in dropped
        ),
    )
    return fitted, report
