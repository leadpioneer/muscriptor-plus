"""Splitting a monophonic note sequence into independently optimized phrases.

A new phrase starts when the gap between the previous note's offset and the
next note's onset reaches `phrase_gap_beats` beats. Overlapping durations
(legato, ringing notes) make the gap negative, which counts as zero — a long
ringing note never forces a phrase break.
"""

from .models import MidiNote, Phrase


def split_phrases(
    notes: tuple[MidiNote, ...],
    ticks_per_beat: int,
    phrase_gap_beats: float,
) -> tuple[Phrase, ...]:
    """Group `notes` (already sorted by onset) into phrases."""
    if not notes:
        return ()
    threshold_ticks = phrase_gap_beats * ticks_per_beat
    phrases: list[list[MidiNote]] = [[notes[0]]]
    for note in notes[1:]:
        gap = max(0, note.onset_ticks - phrases[-1][-1].offset_ticks)
        if gap >= threshold_ticks:
            phrases.append([])
        phrases[-1].append(note)
    return tuple(
        Phrase(index=index, notes=tuple(group))
        for index, group in enumerate(phrases)
    )
