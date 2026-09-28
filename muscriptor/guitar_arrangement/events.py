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

    # Elementary timeline intervals: split at every onset and offset tick.
    # A note is active on [onset, offset); counting over the sorted boundary
    # ticks is exact and deterministic.
    boundaries = sorted({t for e in events for t in (e.onset_ticks,)}) + sorted(
        {note.offset_ticks for e in events for note in e.notes}
    )
    boundaries = sorted(set(boundaries))
    onsets = sorted(e.onset_ticks for e in events)
    boundaries = sorted(set(boundaries) | set(onsets))

    max_active = 0
    overlapping_regions = 0
    for start, end in zip(boundaries, boundaries[1:]):
        if end <= start:
            continue
        middle = start  # half-open [start, end): onset <= t < offset
        active = sum(
            1
            for e in events
            for note in e.notes
            if note.onset_ticks <= middle < note.offset_ticks
        )
        max_active = max(max_active, active)
        if active >= 2:
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
