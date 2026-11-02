"""Unit tests for the chord (event) solver, locks and serialization."""

import json

import pytest

from muscriptor.guitar_arrangement import (
    InvalidOverridesError,
    MidiNote,
    STANDARD_TUNING,
    SolverConfig,
    arrange,
)

from .midi_build import melody_midi


def _note(index, pitch, onset, duration):
    return MidiNote(
        id=f"n{index}",
        track_index=0,
        channel=0,
        pitch=pitch,
        onset_ticks=onset,
        offset_ticks=onset + duration,
        velocity=100,
    )


# --- Locks (through the pipeline) ------------------------------------------


def _two_note_midi():
    return melody_midi([(64, 0, 240), (67, 240, 240)])


def test_lock_on_a_legal_position_is_honoured():
    result = arrange(
        _two_note_midi(),
        filename="song.mid",
        overrides_text=(
            '{"version": 1, "locks": [{"note_id": '
            '"track:0/channel:0/note:1", "string": 3, "fret": 9}]}'
        ),
    )
    first = result["notes"][0]
    assert first["locked"] is True
    # The lock pins string/fret; the solver still picks a compatible
    # hand_position + finger pair for it.
    assert (first["string"], first["fret"]) == (3, 9)
    assert first["hand_position"] + first["finger"] - 1 == first["fret"]
    assert 1 <= first["finger"] <= 4
    assert any(
        f["string"] == first["string"] and f["fret"] == first["fret"]
        for f in first["legal_fingerings"]
    )
    second = result["notes"][1]
    assert second["locked"] is False
    assert result["metrics"]["locked_notes"] == 1


def test_lock_that_changes_the_pitch_is_rejected():
    # String 2 fret 9 sounds 68, but the note is pitch 64.
    with pytest.raises(InvalidOverridesError) as excinfo:
        arrange(
            _two_note_midi(),
            filename="song.mid",
            overrides_text=(
                '{"version": 1, "locks": [{"note_id": '
                '"track:0/channel:0/note:1", "string": 2, "fret": 9}]}'
            ),
        )
    assert "pitch" in str(excinfo.value)


def test_lock_with_an_unknown_note_id_is_rejected():
    with pytest.raises(InvalidOverridesError) as excinfo:
        arrange(
            _two_note_midi(),
            filename="song.mid",
            overrides_text=(
                '{"version": 1, "locks": [{"note_id": "no/such/note", '
                '"string": 1, "fret": 0}]}'
            ),
        )
    assert "unknown note id" in str(excinfo.value)


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"version": 2, "locks": []}',
        '{"version": 1, "locks": [{"note_id": "x"}]}',
        '{"version": 1, "locks": [{"note_id": "x", "string": 0, "fret": 1}]}',
        '{"version": 1, "locks": [{"note_id": "x", "string": 1, "fret": -1}]}',
    ],
)
def test_malformed_overrides_are_rejected(text):
    with pytest.raises(InvalidOverridesError):
        arrange(_two_note_midi(), filename="song.mid", overrides_text=text)


# --- End-to-end property checks --------------------------------------------

_MELODIES = [
    [(64, 0, 240), (67, 240, 240), (71, 480, 240), (67, 720, 240)],
    [(45, 0, 480), (52, 480, 480), (57, 960, 480)],
    [(76, 0, 120), (74, 240, 120), (71, 480, 120), (69, 720, 120), (64, 960, 480)],
]


@pytest.mark.parametrize("melody", _MELODIES)
def test_arrangement_preserves_music_and_stays_physical(melody):
    result = arrange(melody_midi(melody), filename="song.mid")
    notes = result["notes"]
    assert len(notes) == len(melody)
    open_pitches = STANDARD_TUNING.open_pitches
    for original, arranged in zip(melody, notes):
        pitch, onset, duration = original
        assert arranged["pitch"] == pitch
        assert arranged["onset_ticks"] == onset
        assert arranged["offset_ticks"] == onset + duration
        string, fret = arranged["string"], arranged["fret"]
        hand_position, finger = (
            arranged["hand_position"],
            arranged["finger"],
        )
        assert 1 <= string <= len(open_pitches)
        assert 0 <= fret <= result["instrument"]["max_fret"]
        # Physically consistent: the position really sounds the note's pitch.
        assert open_pitches[string - 1] + fret == pitch
        # Ergonomic invariants (spec #8).
        if fret == 0:
            assert finger == 0
        else:
            assert 1 <= finger <= 4
            assert fret == hand_position + finger - 1
            assert 1 <= hand_position <= result["instrument"]["max_hand_position"]
        # And the chosen fingering was among the legal ones.
        assert {"string": string, "fret": fret} in arranged["legal_positions"]
        assert {
            "string": string,
            "fret": fret,
            "hand_position": hand_position,
            "finger": finger,
        } in arranged["legal_fingerings"]


def test_identical_input_gives_identical_output():
    data = melody_midi(_MELODIES[0])
    assert arrange(data, filename="song.mid") == arrange(data, filename="song.mid")


# --- v2 regression tests (the v1 defect) ------------------------------------


def test_scale_does_not_crawl_up_one_string():
    """The reported defect: MIDI 60→72 was placed on one string, frets 1→13.
    v2 must prefer crossing strings in a small set of hand positions."""
    scale = [
        (60, 0, 480),
        (62, 480, 480),
        (64, 960, 480),
        (65, 1440, 480),
        (67, 1920, 480),
        (69, 2400, 480),
        (71, 2880, 480),
        (72, 3360, 960),
    ]
    result = arrange(melody_midi(scale), filename="song.mid")
    notes = result["notes"]
    metrics = result["metrics"]
    assert [n["pitch"] for n in notes] == [p for p, _, _ in scale]
    # Not the one-string crawl: several strings or few hand positions.
    strings_used = {n["string"] for n in notes}
    hand_positions = {n["hand_position"] for n in notes}
    assert len(strings_used) >= 2 or len(hand_positions) <= 2
    # Bounded hand movement: few position changes, small total travel.
    assert metrics["position_change_count"] <= 4
    assert metrics["total_hand_position_travel"] <= 8
    assert metrics["largest_hand_position_shift"] <= 4
    # Every note stays physically and ergonomically consistent.
    for note in notes:
        open_pitch = result["instrument"]["open_pitches"][note["string"] - 1]
        assert open_pitch + note["fret"] == note["pitch"]
        if note["fret"] > 0:
            assert note["fret"] == note["hand_position"] + note["finger"] - 1


def test_run_beyond_four_frets_shifts_or_crosses_explicitly():
    """A line that leaves a four-fret window must show it as a real hand
    shift (or a string crossing) — not hide it in fret movement."""
    # Pitches 60..64 on string 2 would be frets 1..5: beyond one position.
    line = [(60 + i, i * 240, 200) for i in range(5)]
    result = arrange(melody_midi(line), filename="song.mid")
    notes = result["notes"]
    metrics = result["metrics"]
    same_string = len({n["string"] for n in notes}) == 1
    if same_string:
        # All on one string → the hand must have moved at least once.
        assert metrics["position_change_count"] >= 1
        assert metrics["total_hand_position_travel"] >= 2
    # Either way, the movement is visible in the dedicated metrics.
    assert metrics["position_change_count"] >= 1 or metrics["total_string_travel"] >= 1


def test_thousands_of_notes_are_handled_quickly_enough():
    """No hard ms threshold (CI-unstable), but a pathological blowup would
    still hang the suite: 5000 notes must simply complete."""
    melody = [(60 + (i % 20), i * 120, 100) for i in range(5000)]
    result = arrange(melody_midi(melody), filename="song.mid")
    assert result["metrics"]["note_count"] == 5000
    assert result["metrics"]["phrase_count"] == 1


def test_two_thousand_events_with_chords_stay_bounded():
    """Benchmark-like v3 test: 2000 singleton events with periodic dyads,
    triads and a few six-note chords. Asserts completion, deterministic
    output and bounded candidate counts — no wall-clock thresholds."""
    notes = []
    tick = 0
    ordinal = 0
    for i in range(2000):
        kind = i % 40
        if kind == 0:
            pitches = (40, 47, 52, 56, 59, 64)  # six-note chord
        elif kind == 7:
            pitches = (60, 64, 67)  # triad
        elif kind == 13:
            pitches = (64, 67)  # dyad
        else:
            pitches = (60 + (i % 12),)
        for pitch in pitches:
            ordinal += 1
            notes.append((pitch, tick, 200))
        tick += 240
    data = melody_midi(notes)
    first = arrange(data, filename="song.mid")
    second = arrange(data, filename="song.mid")
    assert (
        first["metrics"]["note_count"]
        == sum(
            len({(p, t) for p, t, _ in notes if t == ev})
            for ev in range(0, 2000 * 240, 240)
        )
        or first["metrics"]["note_count"] > 2000
    )
    assert json.dumps(first) == json.dumps(second)
    # Candidates never explode: per event bounded by the cap.
    for event in first["events"]:
        assert event["generated_candidates"] <= 5000
        assert len(event["note_ids"]) <= 6


# --- Open-string register penalty (solo open string far from the nut) ------
#
# A solo open string with the hand high up the neck reads as a register
# mistake: the fretted in-position alternative must win. Open strings stay
# free near the nut (hand position <= 3) and whenever anything else sounds
# at the same time (chords, async overlaps, locked notes).


def _event_for(pitches, onsets=None, duration=240):
    """One NoteEvent (chord if several pitches share an onset)."""
    from muscriptor.guitar_arrangement import group_into_events

    onsets = onsets or [0] * len(pitches)
    notes = tuple(
        _note(i, pitch, onset, duration)
        for i, (pitch, onset) in enumerate(zip(pitches, onsets))
    )
    return group_into_events(notes)[0]


def _shapes_for(pitches):
    from muscriptor.guitar_arrangement import generate_chord_shapes

    return generate_chord_shapes(_event_for(pitches), STANDARD_TUNING, SolverConfig())


def test_penalty_hits_only_solo_open_strings_above_the_free_position():
    from muscriptor.guitar_arrangement import chord_open_string_penalty

    config = SolverConfig()
    shapes = _shapes_for((64,))  # E4: open string 1 or fretted below
    open_far = next(
        s for s in shapes if s.notes[0].position.fret == 0 and s.hand_position == 7
    )
    open_near = next(
        s for s in shapes if s.notes[0].position.fret == 0 and s.hand_position <= 3
    )
    fretted = next(s for s in shapes if s.notes[0].position.fret > 0)

    assert chord_open_string_penalty(open_far, False, False, config) == (
        config.open_string_far_penalty
    )
    assert chord_open_string_penalty(open_near, False, False, config) == 0.0
    assert chord_open_string_penalty(fretted, False, False, config) == 0.0
    # Exemptions: overlap, lock, chords, and a disabled penalty.
    assert chord_open_string_penalty(open_far, True, False, config) == 0.0
    assert chord_open_string_penalty(open_far, False, True, config) == 0.0
    assert (
        chord_open_string_penalty(
            open_far, False, False, SolverConfig(open_string_far_penalty=0.0)
        )
        == 0.0
    )
    chord_shapes = _shapes_for((64, 74))  # includes open string 1 at hp 12–15
    chord_with_open = next(
        s for s in chord_shapes if any(n.position.fret == 0 for n in s.notes)
    )
    assert len(chord_with_open.notes) == 2
    assert chord_open_string_penalty(chord_with_open, False, False, config) == 0.0


def test_event_overlap_detection():
    from muscriptor.guitar_arrangement import (
        event_overlaps_others,
        group_into_events,
    )

    phrase = group_into_events(
        (
            _note(0, 40, 0, 1440),  # bass rings under both notes
            _note(1, 74, 240, 240),
            _note(2, 64, 480, 240),
        )
    )
    assert event_overlaps_others(phrase, 0)
    assert event_overlaps_others(phrase, 1)
    assert event_overlaps_others(phrase, 2)

    legato = group_into_events(
        (
            _note(0, 64, 0, 240),
            _note(1, 67, 240, 240),  # adjacent, not overlapping
        )
    )
    assert not event_overlaps_others(legato, 0)
    assert not event_overlaps_others(legato, 1)


def test_solo_open_string_is_replaced_by_the_fretted_in_position_note():
    # D5 (fret 10, string 1) — E4 (open string 1 or fret 9, string 3) — D5.
    # The context pins the hand at position 7; the open string must lose.
    melody = [(74, 0, 240), (64, 240, 240), (74, 480, 240)]
    result = arrange(melody_midi(melody), filename="song.mid")
    by_pitch = {n["pitch"]: (n["string"], n["fret"]) for n in result["notes"]}
    assert by_pitch[74] == (1, 10)
    assert by_pitch[64] == (3, 9), "solo open string must lose to fret 9"


def test_overlapped_open_string_is_still_welcome():
    # The same line, but a low E bass rings under it: the open string is
    # idiomatic again and must win (it is cheaper than the crossing).
    notes = [(40, 0, 1440), (74, 240, 240), (64, 480, 240), (74, 720, 240)]
    result = arrange(melody_midi(notes), filename="song.mid")
    by_onset = {n["onset_ticks"]: (n["string"], n["fret"]) for n in result["notes"]}
    assert by_onset[0] == (6, 0)  # E2 exists only as the open 6th string
    assert by_onset[480] == (1, 0), "overlapped open string must stay free"
    assert by_onset[240] == (1, 10)
    assert by_onset[720] == (1, 10)


def test_forced_open_note_never_drags_the_hand_around():
    # E2 can only be played open; the penalty is smaller than a down-and-back
    # hand trip, so the hand stays in one place and pays the penalty once.
    melody = [(74, 0, 240), (40, 240, 240), (74, 480, 240)]
    result = arrange(melody_midi(melody), filename="song.mid")
    notes = {n["pitch"]: n for n in result["notes"]}
    assert (notes[40]["string"], notes[40]["fret"]) == (6, 0)
    # D5: fret 10 on string 1 or fret 15 on string 2 — either way one stable
    # position, chosen together with the open string's hand position.
    assert (notes[74]["string"], notes[74]["fret"]) in {(1, 10), (2, 15)}
    assert result["metrics"]["total_hand_position_travel"] == 0


def test_chord_keeps_its_open_string_in_a_high_position():
    # E4 + D5: the shape with the open 1st string and D5 on fret 15 sits at
    # hand positions 12–15 — chords are exempt from the register penalty.
    result = arrange(melody_midi([(64, 0, 480), (74, 0, 480)]), filename="song.mid")
    by_pitch = {n["pitch"]: (n["string"], n["fret"]) for n in result["notes"]}
    assert by_pitch[64] == (1, 0)
    assert by_pitch[74] == (2, 15)
