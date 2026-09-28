/**
 * Types and API client for the Guitar Arranger Lab.
 *
 * The backend (POST /arrange/guitar) is the single source of truth: every
 * click here only produces a lock (override), and the whole arrangement is
 * re-fetched with the original MIDI plus the full lock set. Nothing in this
 * module edits strings/frets locally.
 *
 * The response is schema v2 as produced by
 * `muscriptor.guitar_arrangement.serialization` вЂ” byte-stable, no timestamps.
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
  phrase: number;
  pitch: number;
  onset_ticks: number;
  offset_ticks: number;
  velocity: number;
  string: number;
  fret: number;
  hand_position: number;
  finger: number;
  locked: boolean;
  legal_positions: FretPosition[];
  legal_fingerings: FingeringState[];
};

export type GuitarPhrase = {
  index: number;
  start_tick: number;
  end_tick: number;
  cost: number;
  fret_travel: number;
  string_travel: number;
};

export type GuitarArrangement = {
  schema_version: 2;
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
  phrases: GuitarPhrase[];
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
    total_cost: number;
    position_change_count: number;
    total_hand_position_travel: number;
    largest_hand_position_shift: number;
    open_string_count: number;
    finger_usage: Record<string, number>;
    total_fret_travel: number;
    total_string_travel: number;
    largest_fret_transition: number;
    largest_string_transition: number;
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
  if (doc.schema_version !== 2) {
    throw new GuitarSchemaError(
      `unsupported arrangement schema_version ${JSON.stringify(doc.schema_version)}, expected 2`,
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
