/** Shared schema-v3 fixtures for the Guitar Arranger Lab tests. */
import type { ArrangedNote, GuitarArrangement } from "../guitar-arrangement";

export const NOTE: ArrangedNote = {
  id: "track:0/channel:0/note:1",
  event_id: "event:0",
  phrase: 0,
  pitch: 60,
  onset_ticks: 0,
  offset_ticks: 480,
  velocity: 90,
  string: 3,
  fret: 5,
  hand_position: 5,
  finger: 1,
  locked: false,
  legal_positions: [
    { string: 3, fret: 5 },
    { string: 4, fret: 10 },
    { string: 2, fret: 0 },
  ],
  legal_fingerings: [
    { string: 3, fret: 5, hand_position: 5, finger: 1 },
    { string: 4, fret: 10, hand_position: 10, finger: 1 },
    { string: 2, fret: 0, hand_position: 5, finger: 0 },
    { string: 2, fret: 0, hand_position: 6, finger: 0 },
  ],
};

export const ARRANGEMENT: GuitarArrangement = {
  schema_version: 3,
  source: {
    filename: "song.mid",
    ticks_per_beat: 480,
    track_index: 0,
    track_name: "Demo Lead",
    channel: 0,
    program: 30,
  },
  instrument: {
    name: "standard_guitar",
    string_numbering: "1_is_highest",
    open_pitches: [64, 59, 55, 50, 45, 40],
    max_fret: 24,
    max_hand_position: 21,
  },
  polyphony_analysis: {
    note_count: 1,
    onset_event_count: 1,
    polyphonic_event_count: 0,
    largest_onset_group: 1,
    overlapping_region_count: 0,
    max_active_notes: 1,
    strictly_monophonic: true,
  },
  phrases: [
    { index: 0, start_tick: 0, end_tick: 1440, cost: 0.5, event_count: 1, fret_travel: 3, string_travel: 1 },
  ],
  events: [],
  notes: [NOTE],
  melody_reduction: { policy: "off", dropped_note_count: 0, dropped: [] },
  metrics: {
    note_count: 1,
    phrase_count: 1,
    event_count: 1,
    total_cost: 0.5,
    position_change_count: 0,
    total_hand_position_travel: 0,
    largest_hand_position_shift: 0,
    open_string_count: 0,
    finger_usage: { 0: 0, 1: 1, 2: 0, 3: 0, 4: 0 },
    total_fret_travel: 3,
    total_string_travel: 1,
    locked_notes: 0,
  },
};
