"""Onset events: grouping notes by tick and polyphony analysis.

A `NoteEvent` is every note whose onset is the same MIDI tick — the unit the
v3 solver optimizes. Grouping, ordering and the analysis are deterministic:
the same input always produces the same events and the same numbers, and the
analysis is purely descriptive — nothing here ever removes or changes notes.
"""

from .models import MidiNote, NoteEvent, PolyphonyAnalysis


def group_into_events(notes: tuple[MidiNote, ...]) -> tuple[NoteEvent, ...]:
    """Group notes into onset events, sorted by (onset, then per-event rule).

    Notes inside one event are ordered by `(pitch descending, note_id)` —
    the single fixed rule used by the solver, the JSON and the tab renderer.
    Events are indexed sequentially in onset order.
    """
    by_onset: dict[int, list[MidiNote]] = {}
    for note in notes:
        by_onset.setdefault(note.onset_ticks, []).append(note)
    events = []
    for index, tick in enumerate(sorted(by_onset)):
        group = sorted(by_onset[tick], key=lambda n: (-n.pitch, n.id))
        events.append(NoteEvent(index=index, onset_ticks=tick, notes=tuple(group)))
    return tuple(events)


def analyze_polyphony(events: tuple[NoteEvent, ...]) -> PolyphonyAnalysis:
    """Describe how polyphonic the event stream is. Purely diagnostic."""
    note_count = sum(len(e.notes) for e in events)
    polyphonic_event_count = sum(1 for e in events if len(e.notes) > 1)
    largest = max((len(e.notes) for e in events), default=0)

    # Sweep line over onset/offset deltas: each note contributes +1 at its
    # onset and -1 at its offset, so the active count is accumulated in one
    # pass instead of rescanning every note for every boundary.
    deltas: dict[int, int] = {}
    for e in events:
        for note in e.notes:
            deltas[note.onset_ticks] = deltas.get(note.onset_ticks, 0) + 1
            deltas[note.offset_ticks] = deltas.get(note.offset_ticks, 0) - 1

    max_active = 0
    overlapping_regions = 0
    active = 0
    boundaries = sorted(deltas)
    for index, tick in enumerate(boundaries):
        active += deltas[tick]
        # `active` holds the count on [tick, next boundary): onset <= t < offset.
        max_active = max(max_active, active)
        if index + 1 < len(boundaries) and active >= 2:
            overlapping_regions += 1

    return PolyphonyAnalysis(
        note_count=note_count,
        onset_event_count=len(events),
        polyphonic_event_count=polyphonic_event_count,
        largest_onset_group=largest,
        overlapping_region_count=overlapping_regions,
        max_active_notes=max_active,
        strictly_monophonic=max_active <= 1,
    )
