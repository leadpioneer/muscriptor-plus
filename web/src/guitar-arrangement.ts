/**
 * Types and API client for the Guitar Arranger Lab.
 *
 * The backend (POST /arrange/guitar) is the single source of truth: every
 * click here only produces a lock (override), and the whole arrangement is
 * re-fetched with the original MIDI plus the full lock set. Nothing in this
 * module edits strings/frets locally.
 *
 * The response is schema v3 as produced by
 * `muscriptor.guitar_arrangement.serialization` (byte-stable, no timestamps).
 * Legacy schema-v2 documents (monophonic, no events/polyphony analysis) are
 * still parsed for display; the UI's chord view is derived from shared
 * onsets, which is exactly what v3's `events` record.
 */

export type FretPosition = { string: number; fret: number };

export type FingeringState = {
  string: number;
  fret: number;
  hand_position: number;
  finger: number;
};

export type ArrangedNote = {
  id: string;
  /** The onset event this note belongs to (schema v3). */
  event_id?: string;
  phrase: number;
  pitch: number;
  onset_ticks: number;
  offset_ticks: number;
  velocity: number;
  string: number;
  fret: number;
  hand_position: number;
  /** null when the backend's finger annotation is incomplete. */
  finger: number | null;
  locked: boolean;
  legal_positions: FretPosition[];
  legal_fingerings: FingeringState[];
};

/** One onset event of the schema-v3 document (1–6 notes). */
export type GuitarEvent = {
  id: string;
  index: number;
  phrase: number;
  onset_ticks: number;
  note_ids: string[];
  hand_position: number;
  barres: {
    finger: number;
    fret: number;
    from_string: number;
    to_string: number;
    note_ids: string[];
  }[];
  shape_cost: number;
  finger_assignment_complete: boolean;
  generated_candidates: number;
  pruned_candidates: number;
  optimal_within: string;
};

export type PolyphonyAnalysis = {
  note_count: number;
  onset_event_count: number;
  polyphonic_event_count: number;
  largest_onset_group: number;
  overlapping_region_count: number;
  max_active_notes: number;
  strictly_monophonic: boolean;
};

export type GuitarPhrase = {
  index: number;
  start_tick: number;
  end_tick: number;
  cost: number;
  event_count: number;
  fret_travel: number;
  string_travel: number;
};

export type GuitarArrangement = {
  schema_version: 3;
  source: {
    filename: string;
    ticks_per_beat: number;
    track_index: number;
    track_name: string | null;
    channel: number;
    program: number | null;
  };
  instrument: {
    name: string;
    string_numbering: string;
    open_pitches: number[];
    max_fret: number;
    max_hand_position: number;
  };
  polyphony_analysis?: PolyphonyAnalysis;
  phrases: GuitarPhrase[];
  events?: GuitarEvent[];
  notes: ArrangedNote[];
  /** What the melody reduction removed (policy "off" when nothing ran). */
  melody_reduction: {
    policy: string;
    dropped_note_count: number;
    dropped: { tick: number; pitch: number }[];
  };
  metrics: {
    note_count: number;
    phrase_count: number;
    event_count: number;
    total_cost: number;
    position_change_count: number;
    total_hand_position_travel: number;
    largest_hand_position_shift: number;
    open_string_count: number;
    finger_usage: Record<string, number>;
    total_fret_travel: number;
    total_string_travel: number;
    locked_notes: number;
  };
};

/** One row of the ambiguous_track error's candidate list (`details.tracks`). */
export type GuitarTrackCandidate = {
  track_index: number;
  track_name: string | null;
  channel: number;
  program: number | null;
  note_count: number;
  drum: boolean;
};

/** A manual fingering fix: the note must sound from this string/fret. */
export type FingeringLock = { note_id: string; string: number; fret: number };

/** A structured `{code, message, details}` failure of the arrange endpoint. */
export class GuitarArrangementError extends Error {
  code: string;
  details: unknown;

  constructor(code: string, message: string, details: unknown) {
    super(message);
    this.name = "GuitarArrangementError";
    this.code = code;
    this.details = details;
  }
}

/** The response JSON is missing, malformed, or of an unknown schema version. */
export class GuitarSchemaError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GuitarSchemaError";
  }
}

/**
 * Validates the bare minimum of the arrangement document and rejects unknown
 * schema versions up front вЂ” the lab renders nothing rather than guessing.
 */
export function parseArrangement(raw: unknown): GuitarArrangement {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new GuitarSchemaError("arrangement response is not a JSON object");
  }
  const doc = raw as Record<string, unknown>;
  if (doc.schema_version !== 2 && doc.schema_version !== 3) {
    throw new GuitarSchemaError(
      `unsupported arrangement schema_version ${JSON.stringify(doc.schema_version)}, expected 2 or 3`,
    );
  }
  if (!Array.isArray(doc.notes) || !Array.isArray(doc.phrases)) {
    throw new GuitarSchemaError("arrangement response has no notes/phrases");
  }
  if (
    typeof doc.instrument !== "object" ||
    doc.instrument === null ||
    !Array.isArray((doc.instrument as Record<string, unknown>).open_pitches)
  ) {
    throw new GuitarSchemaError("arrangement response has no instrument");
  }
  return doc as unknown as GuitarArrangement;
}

/** Extracts the track candidates from an ambiguous_track error payload. */
export function parseTrackCandidates(details: unknown): GuitarTrackCandidate[] {
  const tracks =
    typeof details === "object" && details !== null && "tracks" in details
      ? (details as { tracks: unknown }).tracks
      : null;
  if (!Array.isArray(tracks)) return [];
  return tracks.filter(
    (t): t is GuitarTrackCandidate =>
      typeof t === "object" &&
      t !== null &&
      typeof (t as Record<string, unknown>).track_index === "number" &&
      typeof (t as Record<string, unknown>).channel === "number",
  );
}

/** Serializes the current lock set into the overrides transport document. */
export function buildOverrides(locks: Record<string, FingeringLock>): string {
  return JSON.stringify({ version: 1, locks: Object.values(locks) });
}

export type ArrangeGuitarOptions = {
  midi: Blob;
  filename: string;
  track?: number;
  channel?: number;
  /** Monophonic reduction policy: off (default), top, bottom. */
  melody?: string;
  /** JSON overrides document (see `buildOverrides`). */
  overrides?: string;
  signal?: AbortSignal;
};

/**
 * POST /arrange/guitar. Resolves with the raw response text (kept verbatim
 * for the download button) and the validated arrangement. Structured backend
 * errors surface as `GuitarArrangementError`; aborts are rethrown untouched
 * so the caller can tell them apart from real failures.
 */
export async function arrangeGuitar(
  options: ArrangeGuitarOptions,
): Promise<{ text: string; arrangement: GuitarArrangement }> {
  const form = new FormData();
  form.append("file", options.midi, options.filename);
  if (options.track !== undefined) form.append("track", String(options.track));
  if (options.channel !== undefined) {
    form.append("channel", String(options.channel));
  }
  if (options.melody !== undefined && options.melody !== "off") {
    form.append("melody", options.melody);
  }
  if (options.overrides !== undefined) {
    form.append("overrides", options.overrides);
  }

  let resp: Response;
  try {
    resp = await fetch("/arrange/guitar", {
      method: "POST",
      body: form,
      signal: options.signal,
    });
  } catch (e) {
    if (options.signal?.aborted) {
      throw new DOMException("The request was aborted", "AbortError");
    }
    throw e;
  }

  const text = await resp.text();
  if (!resp.ok) {
    // FastAPI wraps our structured errors into `detail`, but network layers
    // and proxies may answer with anything вЂ” keep a readable fallback.
    let code = "request_failed";
    let message = text || `HTTP ${resp.status}`;
    let details: unknown = null;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (
        typeof parsed.detail === "object" &&
        parsed.detail !== null &&
        "code" in parsed.detail
      ) {
        const d = parsed.detail as Record<string, unknown>;
        code = String(d.code);
        message = String(d.message ?? message);
        details = d.details ?? null;
      } else if (typeof parsed.detail === "string") {
        message = parsed.detail;
      }
    } catch {
      /* not JSON вЂ” keep the raw body as the message */
    }
    throw new GuitarArrangementError(code, message, details);
  }

  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch {
    throw new GuitarSchemaError("arrangement response is not valid JSON");
  }
  return { text, arrangement: parseArrangement(json) };
}

const PITCH_NAMES = [
  "C",
  "C#",
  "D",
  "D#",
  "E",
  "F",
  "F#",
  "G",
  "G#",
  "A",
  "A#",
  "B",
] as const;

/** MIDI 60 в†’ "C4" (scientific pitch notation, sharps only). */
export function pitchName(pitch: number): string {
  return PITCH_NAMES[pitch % 12] + (Math.floor(pitch / 12) - 1);
}

/** Phrase-level hand metrics, derived from the notes' hand_position path. */
export function phraseHandMetrics(notes: ArrangedNote[]): {
  changes: number;
  travel: number;
  largest: number;
} {
  let changes = 0;
  let travel = 0;
  let largest = 0;
  for (let i = 1; i < notes.length; i++) {
    const shift = Math.abs(notes[i].hand_position - notes[i - 1].hand_position);
    if (shift > 0) {
      changes += 1;
      travel += shift;
      largest = Math.max(largest, shift);
    }
  }
  return { changes, travel, largest };
}

/** Every legal_fingerings entry that lands on this string/fret. */
export function fingeringsAt(
  note: ArrangedNote,
  string: number,
  fret: number,
): FingeringState[] {
  return note.legal_fingerings.filter(
    (f) => f.string === string && f.fret === fret,
  );
}

/**
 * Groups one phrase's notes into onset events (pitch descending, then id —
 * the same canonical order the backend uses). Used for the chord view and
 * the Arrow-key navigation; equivalent to the document's `events` list.
 */
export function groupPhraseEvents(notes: ArrangedNote[]): ArrangedNote[][] {
  const byOnset = new Map<number, ArrangedNote[]>();
  for (const note of notes) {
    const group = byOnset.get(note.onset_ticks);
    if (group) {
      group.push(note);
    } else {
      byOnset.set(note.onset_ticks, [note]);
    }
  }
  return [...byOnset.keys()]
    .sort((a, b) => a - b)
    .map((onset) =>
      (byOnset.get(onset) ?? []).sort(
        (a, b) => b.pitch - a.pitch || a.id.localeCompare(b.id),
      ),
    );
}

/** The document's event record for a note (when the backend sent events). */
export function eventOf(
  arrangement: GuitarArrangement | null,
  note: ArrangedNote | null,
): GuitarEvent | null {
  if (arrangement === null || note === null || !Array.isArray(arrangement.events))
    return null;
  return (
    arrangement.events.find(
      (e) =>
        e.note_ids.includes(note.id) ||
        (e.onset_ticks === note.onset_ticks && e.phrase === note.phrase),
    ) ?? null
  );
}
