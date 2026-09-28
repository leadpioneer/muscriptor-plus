import { describe, expect, it } from "vitest";
import {
  buildOverrides,
  parseArrangement,
  parseTrackCandidates,
  phraseHandMetrics,
  pitchName,
  GuitarSchemaError,
} from "./guitar-arrangement";
import { ARRANGEMENT } from "./test/fixtures";

describe("parseArrangement", () => {
  it("accepts schema v3 and keeps the event structure", () => {
    const parsed = parseArrangement(JSON.parse(JSON.stringify(ARRANGEMENT)));
    expect(parsed.schema_version).toBe(3);
    expect(parsed.notes[0].legal_positions).toHaveLength(3);
    expect(parsed.polyphony_analysis?.strictly_monophonic).toBe(true);
  });

  it("accepts legacy schema v2 documents (documented policy)", () => {
    const legacy = {
      ...JSON.parse(JSON.stringify(ARRANGEMENT)),
      schema_version: 2,
      polyphony_analysis: undefined,
      events: undefined,
    };
    const parsed = parseArrangement(legacy);
    expect(parsed.schema_version).toBe(2); // passed through; v2 renders fine
    expect(parsed.notes[0].finger).toBe(1);
  });

  it("rejects other schema versions with a readable error", () => {
    expect(() => parseArrangement({ schema_version: 4 })).toThrow(
      GuitarSchemaError,
    );
    expect(() => parseArrangement({ schema_version: 1 })).toThrow(
      /schema_version 1/,
    );
  });

  it("rejects non-object payloads and missing sections", () => {
    expect(() => parseArrangement(null)).toThrow(GuitarSchemaError);
    expect(() => parseArrangement([1, 2])).toThrow(GuitarSchemaError);
    expect(() => parseArrangement({ schema_version: 2 })).toThrow(GuitarSchemaError);
  });
});

describe("parseTrackCandidates", () => {
  it("reads the tracks list out of the ambiguous_track details", () => {
    const candidates = parseTrackCandidates({
      tracks: [
        {
          track_index: 2,
          track_name: "Electric Guitar",
          channel: 0,
          program: 30,
          note_count: 146,
          drum: false,
        },
      ],
    });
    expect(candidates).toEqual([
      {
        track_index: 2,
        track_name: "Electric Guitar",
        channel: 0,
        program: 30,
        note_count: 146,
        drum: false,
      },
    ]);
  });

  it("returns nothing usable for malformed details", () => {
    expect(parseTrackCandidates(null)).toEqual([]);
    expect(parseTrackCandidates({})).toEqual([]);
    expect(parseTrackCandidates({ tracks: ["nope", 3] })).toEqual([]);
  });
});

describe("buildOverrides", () => {
  it("serializes the full lock set in the overrides v1 transport", () => {
    const overrides = buildOverrides({
      "track:0/channel:0/note:1": {
        note_id: "track:0/channel:0/note:1",
        string: 4,
        fret: 10,
      },
      "track:0/channel:0/note:2": {
        note_id: "track:0/channel:0/note:2",
        string: 2,
        fret: 2,
      },
    });
    expect(JSON.parse(overrides)).toEqual({
      version: 1,
      locks: [
        { note_id: "track:0/channel:0/note:1", string: 4, fret: 10 },
        { note_id: "track:0/channel:0/note:2", string: 2, fret: 2 },
      ],
    });
  });

  it("serializes an empty set as an empty lock list", () => {
    expect(JSON.parse(buildOverrides({}))).toEqual({ version: 1, locks: [] });
  });
});

describe("pitchName", () => {
  it("uses scientific pitch notation with sharps", () => {
    expect(pitchName(60)).toBe("C4");
    expect(pitchName(61)).toBe("C#4");
    expect(pitchName(64)).toBe("E4");
    expect(pitchName(69)).toBe("A4");
    expect(pitchName(40)).toBe("E2");
    expect(pitchName(72)).toBe("C5");
  });
});

describe("phraseHandMetrics", () => {
  it("counts hand-position shifts between consecutive notes", () => {
    const notes = [
      { hand_position: 5 },
      { hand_position: 5 },
      { hand_position: 8 },
      { hand_position: 8 },
      { hand_position: 4 },
    ] as unknown as Parameters<typeof phraseHandMetrics>[0];
    expect(phraseHandMetrics(notes)).toEqual({ changes: 2, travel: 7, largest: 4 });
  });
});
