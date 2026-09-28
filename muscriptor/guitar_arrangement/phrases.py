"""Splitting an onset-event sequence into independently optimized phrases.

A new phrase starts before an event only when *every* note started before it
has already stopped (a long ringing bass note that overlaps the next onset is
NOT silence) and the gap between that full sound end and the event's onset
reaches `phrase_gap_beats`. The v2 note-level `split_phrases` is kept for the
legacy monophonic path.
"""

from .models import MidiNote, NoteEvent, Phrase


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


def split_event_phrases(
    events: tuple[NoteEvent, ...],
    ticks_per_beat: int,
    phrase_gap_beats: float,
) -> tuple[tuple[NoteEvent, ...], ...]:
    """Group onset events into phrases.

    The silence before an event is measured from the moment ALL notes started
    before it have stopped — the maximum offset so far, not the previous
    event's own last onset or any single note's offset. An event overlapping
    a still-sounding note never starts a new phrase.
    """
    if not events:
        return ()
    threshold_ticks = phrase_gap_beats * ticks_per_beat
    phrases: list[list[NoteEvent]] = [[events[0]]]
    sound_end = events[0].last_offset_ticks
    for event in events[1:]:
        gap = event.onset_ticks - sound_end
        if gap >= threshold_ticks:
            phrases.append([])
        phrases[-1].append(event)
        sound_end = max(sound_end, event.last_offset_ticks)
    return tuple(tuple(group) for group in phrases)
