"""A small read-only adapter over `mido` for the guitar arranger.

Reads a Standard MIDI File from bytes and produces `MidiNote` records with
absolute ticks, stable ids and (track, channel) attribution. The source file
is never modified — the input is bytes, and nothing here writes anything.

Note ids look like `track:2/channel:0/note:17` where `17` is the ordinal of
the note-on event within the source track (counted across channels, in
message order). Ids therefore depend only on the source file, never on
solver output. `note_on` with velocity 0 is treated as `note_off`, as
required by the MIDI spec. A note-on left unmatched at the end of its track
keeps its offset at the track's final tick so no note is silently dropped.

Drum events (channel 9) are parsed like any other channel but are excluded
from automatic track selection.
"""

import io
from collections import deque
from dataclasses import dataclass

import mido
from mido import MetaMessage

from .errors import (
    AmbiguousTrackError,
    MidiParseError,
    PolyphonicInputError,
    TrackNotFoundError,
)
from .models import MidiNote, TempoEvent, TimeSignatureEvent

DRUM_CHANNEL = 9


@dataclass(frozen=True)
class TrackInfo:
    """All notes of one (track, channel) pair, plus describing metadata."""

    track_index: int
    channel: int
    name: str | None
    program: int | None
    notes: tuple[MidiNote, ...]

    @property
    def is_drum(self) -> bool:
        return self.channel == DRUM_CHANNEL

    def summary(self) -> dict:
        """JSON-friendly description used by --list-tracks and API errors."""
        return {
            "track_index": self.track_index,
            "track_name": self.name,
            "channel": self.channel,
            "program": self.program,
            "note_count": len(self.notes),
            "drum": self.is_drum,
        }


@dataclass(frozen=True)
class ParsedMidi:
    ticks_per_beat: int
    tracks: tuple[TrackInfo, ...]
    # Global meta maps collected across all tracks (tempo/time signatures
    # usually live in a conductor track that carries no notes). When the file
    # has none, the standard MIDI defaults (500000 µs/beat, 4/4) are supplied
    # at tick 0 and marked `is_default=True`.
    tempo_events: tuple[TempoEvent, ...] = ()
    time_signature_events: tuple[TimeSignatureEvent, ...] = ()

    def summaries(self) -> list[dict]:
        """All note-bearing (track, channel) pairs, in file order."""
        return [t.summary() for t in self.tracks if t.notes]


DEFAULT_TEMPO = 500000  # µs per beat — the Standard MIDI File default.


def parse_midi(data: bytes) -> ParsedMidi:
    """Parse MIDI file bytes into per-(track, channel) note lists."""
    try:
        midi = mido.MidiFile(file=io.BytesIO(data))
    except Exception as e:  # mido raises a mix of OSError/ValueError/EOFError
        raise MidiParseError(f"could not parse MIDI file: {e}") from e

    combos: dict[tuple[int, int], dict] = {}
    tempo_events: list[TempoEvent] = []
    time_signature_events: list[TimeSignatureEvent] = []

    def combo(track_index: int, channel: int) -> dict:
        return combos.setdefault(
            (track_index, channel),
            {"name": None, "program": None, "notes": []},
        )

    for track_index, track in enumerate(midi.tracks):
        tick = 0
        name: str | None = None
        # (channel, pitch) → note-ons awaiting their note_off, in event order.
        pending: dict[tuple[int, int], deque] = {}
        # Ordinal of the note-on event within this track; part of the note id
        # and, together with the onset, its stable sort key.
        note_ordinal = 0
        final_tick = 0
        for msg in track:
            tick += msg.time
            final_tick = max(final_tick, tick)
            if isinstance(msg, MetaMessage):
                if msg.type == "track_name" and name is None:
                    name = msg.name
                elif msg.type == "set_tempo":
                    tempo_events.append(
                        TempoEvent(tick=tick, tempo=int(msg.tempo))
                    )
                elif msg.type == "time_signature":
                    time_signature_events.append(
                        TimeSignatureEvent(
                            tick=tick,
                            numerator=int(msg.numerator),
                            denominator=int(msg.denominator),
                            clocks_per_click=int(msg.clocks_per_click),
                            notated_32nd_notes_per_beat=int(
                                msg.notated_32nd_notes_per_beat
                            ),
                        )
                    )
                continue
            if msg.type in ("note_on", "note_off"):
                note_on = msg.type == "note_on" and msg.velocity > 0
                if note_on:
                    note_ordinal += 1
                    pending.setdefault(
                        (msg.channel, msg.note), deque()
                    ).append((note_ordinal, msg.channel, msg.note, tick, msg.velocity))
                else:
                    # note_off, or note_on with velocity 0 (same thing per
                    # the MIDI spec). mido calls the MIDI note number `note`.
                    queue = pending.get((msg.channel, msg.note))
                    if queue:
                        ordinal, channel, pitch, onset, velocity = queue.popleft()
                        combo(track_index, msg.channel)["notes"].append(
                            MidiNote(
                                id=(
                                    f"track:{track_index}/channel:{channel}"
                                    f"/note:{ordinal}"
                                ),
                                track_index=track_index,
                                channel=channel,
                                pitch=pitch,
                                onset_ticks=onset,
                                offset_ticks=tick,
                                velocity=velocity,
                            )
                        )
            elif msg.type == "program_change":
                combo(track_index, msg.channel)["program"] = msg.program
        _flush_unmatched(track_index, pending, final_tick, combo)
        if name is not None:
            for channel in range(16):
                if (track_index, channel) in combos:
                    combos[(track_index, channel)]["name"] = name

    tracks = tuple(
        TrackInfo(
            track_index=track_index,
            channel=channel,
            name=info["name"],
            program=info["program"],
            notes=tuple(
                sorted(
                    info["notes"],
                    key=lambda n: (n.onset_ticks, int(n.id.rsplit(":", 1)[1])),
                )
            ),
        )
        for (track_index, channel), info in sorted(combos.items())
        if info["notes"]
    )
    if not tempo_events:
        tempo_events = [TempoEvent(tick=0, tempo=DEFAULT_TEMPO, is_default=True)]
    if not time_signature_events:
        time_signature_events = [
            TimeSignatureEvent(tick=0, numerator=4, denominator=4, is_default=True)
        ]
    return ParsedMidi(
        ticks_per_beat=midi.ticks_per_beat,
        tracks=tracks,
        tempo_events=tuple(tempo_events),
        time_signature_events=tuple(time_signature_events),
    )


def _flush_unmatched(track_index, pending, final_tick, combo) -> None:
    """Give unmatched note-ons an offset at the track's final tick.

    No note is silently dropped, and the reserved ordinals keep the ids of
    the matched notes stable even when some note_off is missing.
    """
    for (channel, _pitch), queue in pending.items():
        for ordinal, _ch, pitch, onset, velocity in queue:
            combo(track_index, channel)["notes"].append(
                MidiNote(
                    id=(
                        f"track:{track_index}/channel:{channel}"
                        f"/note:{ordinal}"
                    ),
                    track_index=track_index,
                    channel=channel,
                    pitch=pitch,
                    onset_ticks=onset,
                    offset_ticks=final_tick,
                    velocity=velocity,
                )
            )


def select_notes(
    parsed: ParsedMidi, track: int | None = None, channel: int | None = None
) -> TrackInfo:
    """Pick the one (track, channel) pair to arrange.

    With no selector, exactly one non-drum note-bearing pair auto-selects.
    Multiple candidates raise `AmbiguousTrackError` listing every option —
    track names are never used to guess. An explicit `--track`/`--channel`
    selects precisely; the drum channel is reachable, just never automatic.
    """
    if track is None and channel is None:
        candidates = [t for t in parsed.tracks if t.notes and not t.is_drum]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise TrackNotFoundError(
                f"no note-bearing tracks to arrange ({_alternatives(parsed)})"
            )
        raise AmbiguousTrackError(
            "several note-bearing tracks: "
            + _alternatives(parsed)
            + " — pass --track (and, if needed, --channel) to pick one",
            parsed.summaries(),
        )

    if track is not None:
        candidates = [
            t
            for t in parsed.tracks
            if t.track_index == track
            and t.notes
            and (channel is None or t.channel == channel)
        ]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise TrackNotFoundError(
                f"track {track} has no notes"
                + (f" on channel {channel}" if channel is not None else "")
                + f"; available: {_alternatives(parsed)}"
            )
        # The track exists but several of its channels carry notes.
        raise AmbiguousTrackError(
            f"track {track} has notes on several channels; pass --channel",
            [t.summary() for t in candidates],
        )

    # channel given, track not.
    candidates = [t for t in parsed.tracks if t.channel == channel and t.notes]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise TrackNotFoundError(
            f"no notes on channel {channel}; available: {_alternatives(parsed)}"
        )
    raise AmbiguousTrackError(
        f"channel {channel} carries notes in several tracks; pass --track",
        [t.summary() for t in candidates],
    )


def _alternatives(parsed: ParsedMidi) -> str:
    summaries = parsed.summaries()
    if not summaries:
        return "no note-bearing tracks"
    return "; ".join(
        f"track {s['track_index']}"
        + (f" ({s['track_name']})" if s["track_name"] else "")
        + f" channel {s['channel']} ({s['note_count']} notes"
        + (", drums)" if s["drum"] else ")")
        for s in summaries
    )


def check_monophonic(notes: tuple[MidiNote, ...]) -> None:
    """Refuse simultaneous onsets instead of guessing a melodic line.

    Overlapping durations with distinct onsets (legato, a ringing previous
    note) are allowed; two or more notes starting at the same tick are not.
    """
    by_onset: dict[int, list[MidiNote]] = {}
    for note in notes:
        by_onset.setdefault(note.onset_ticks, []).append(note)
    for tick in sorted(by_onset):
        group = by_onset[tick]
        if len(group) > 1:
            ids = [n.id for n in group]
            pitches = [n.pitch for n in group]
            raise PolyphonicInputError(
                f"simultaneous note onsets at tick {tick}: pitches "
                + ", ".join(str(p) for p in pitches)
                + " — this arranger optimizes a single melodic line; extract "
                "a monophonic melody track first",
                tick=tick,
                note_ids=ids,
                pitches=pitches,
            )

