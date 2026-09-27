"""Programmatic MIDI fixture builders for the guitar-arranger tests.

No binary fixtures: every test file builds exactly the MIDI it needs with
mido, keeping the tests hermetic and self-documenting.
"""

import io

from mido import Message, MetaMessage, MidiFile, MidiTrack


def melody_midi(
    notes,
    ticks_per_beat: int = 480,
    name: str | None = "Melody",
    channel: int = 0,
    program: int | None = None,
) -> bytes:
    """Build a single-track MIDI file from `(pitch, onset_ticks, duration)`.

    Note-offs at the same tick as the next note-on are written first, so a
    repeated pitch is matched correctly. Other event kinds (control change
    noise) are intentionally absent — the parser must cope with real files
    separately if needed.
    """
    midi = MidiFile(ticks_per_beat=ticks_per_beat)
    track = MidiTrack()
    midi.tracks.append(track)
    if name is not None:
        track.append(MetaMessage("track_name", name=name, time=0))
    if program is not None:
        track.append(
            Message("program_change", channel=channel, program=program, time=0)
        )
    events = []
    for pitch, onset, duration in notes:
        events.append((onset, True, pitch))
        events.append((onset + duration, False, pitch))
    # Note-offs before note-ons on the same tick; stable within a group.
    events.sort(key=lambda e: (e[0], e[1]))
    previous = 0
    for tick, is_on, pitch in events:
        delta = tick - previous
        previous = tick
        if is_on:
            track.append(
                Message(
                    "note_on", channel=channel, note=pitch, velocity=100, time=delta
                )
            )
        else:
            track.append(
                Message(
                    "note_off", channel=channel, note=pitch, velocity=0, time=delta
                )
            )
    buffer = io.BytesIO()
    midi.save(file=buffer)
    return buffer.getvalue()


def raw_midi(tracks, ticks_per_beat: int = 480) -> bytes:
    """Build a MIDI file from raw mido message lists (absolute freedom)."""
    midi = MidiFile(ticks_per_beat=ticks_per_beat)
    for messages in tracks:
        track = MidiTrack()
        midi.tracks.append(track)
        track.extend(messages)
    buffer = io.BytesIO()
    midi.save(file=buffer)
    return buffer.getvalue()
