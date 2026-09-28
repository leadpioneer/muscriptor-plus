/**
 * Guitar Arranger Lab UI tests: mocked fetch, real components.
 *
 * Tests assert meaning — roles, aria-labels, selected state, the exact
 * overrides document built for the request, and which arrangement is on
 * screen — never pixel coordinates.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { zipSync } from "fflate";
import { I18nProvider } from "../i18n";
import { GuitarArrangerDialog, GuitarArrangerEntry } from "./GuitarArrangerDialog";
import { ARRANGEMENT, NOTE } from "../test/fixtures";
import { EN } from "../i18n/en";
import { RU } from "../i18n/ru";
import type { ArrangedNote, GuitarArrangement } from "../guitar-arrangement";

/** The shared engine is mocked: jsdom has no AudioContext/Tone. */
const mockEngine = {
  snapshotNotes: vi.fn(() => []),
  replaceNotes: vi.fn(),
  play: vi.fn(async () => {}),
  pause: vi.fn(),
  stop: vi.fn(),
};

vi.mock("../hooks/useAudioEngine", () => ({
  useAudioEngine: () => mockEngine,
}));

type FetchResponse = { status: number; body: unknown };

/** Deep-copies the fixture so tests can mutate it freely. */
function arrangement(overrides?: Partial<GuitarArrangement>): GuitarArrangement {
  return JSON.parse(
    JSON.stringify({ ...ARRANGEMENT, ...overrides }),
  ) as GuitarArrangement;
}

/** A second note in the same phrase, for selection navigation. */
const NOTE2: ArrangedNote = {
  ...JSON.parse(JSON.stringify(NOTE)),
  id: "track:0/channel:0/note:2",
  pitch: 62,
  onset_ticks: 480,
  offset_ticks: 960,
  finger: 3,
  fret: 7,
  legal_positions: [
    { string: 3, fret: 7 },
    { string: 2, fret: 2 },
  ],
  legal_fingerings: [
    { string: 3, fret: 7, hand_position: 5, finger: 3 },
    { string: 2, fret: 2, hand_position: 5, finger: 1 },
  ],
};

/** The fixture arrangement, as the endpoint would serialize it. */
let responses: FetchResponse[] = [];
const fetchMock = vi.fn(async (_url: string, _init: RequestInit) => {
  const next = responses.shift();
  if (!next) throw new Error("no queued fetch response");
  const body =
    typeof next.body === "string" || next.body instanceof Uint8Array
      ? next.body
      : JSON.stringify(next.body);
  return new Response(body as BodyInit, {
    status: next.status,
    headers: { "content-type": "application/json" },
  });
});

function formField(form: FormData, name: string): string {
  const value = form.get(name);
  expect(value, `form field ${name}`).not.toBeNull();
  return String(value);
}

function formOverrides(init: RequestInit): { version: number; locks: unknown[] } {
  const form = init.body as FormData;
  const raw = form.get("overrides");
  return raw === null ? { version: 1, locks: [] } : JSON.parse(String(raw));
}

function renderDialog(initialMidi: Blob | null = new Blob([new Uint8Array([1, 2, 3])], { type: "audio/midi" })) {
  return render(
    <I18nProvider>
      <GuitarArrangerDialog
        initialMidi={initialMidi}
        initialFilename={initialMidi === null ? "" : "song.mid"}
        onClose={() => {}}
      />
    </I18nProvider>,
  );
}

/** The alternative legal position of the fixture note. */
/** The last anchor the component built for a download (never appended). */
let createElementSpy: ReturnType<typeof vi.spyOn>;

function lastAnchor(): HTMLAnchorElement {
  const anchors = createElementSpy.mock.results
    .map((r: { value: unknown }) => r.value)
    .filter((n: unknown): n is HTMLAnchorElement => n instanceof HTMLAnchorElement);
  expect(anchors.length, "an anchor was created").toBeGreaterThan(0);
  return anchors[anchors.length - 1];
}

const ALTERNATIVE = "C4: string 4, fret 10, hand position 10, finger 1";

beforeEach(() => {
  responses = [];
  fetchMock.mockClear();
  mockEngine.snapshotNotes.mockClear();
  mockEngine.replaceNotes.mockClear();
  mockEngine.play.mockClear();
  mockEngine.pause.mockClear();
  mockEngine.stop.mockClear();
  vi.stubGlobal("fetch", fetchMock);
  // jsdom has no object URL implementation; the download tests want a hook.
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:mock"),
    revokeObjectURL: vi.fn(),
  });
  createElementSpy = vi.spyOn(document, "createElement");
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("GuitarArrangerDialog", () => {
  it("sends the initial request without track/channel and renders schema v2", async () => {
    responses.push({ status: 200, body: ARRANGEMENT });
    renderDialog();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/arrange/guitar");
    const form = init.body as FormData;
    expect(form.get("track")).toBeNull();
    expect(form.get("channel")).toBeNull();
    expect(form.get("overrides")).toBeNull();
    expect(form.get("file")).toBeTruthy();
    // The selected note's state is visible.
    expect(await screen.findByText("Finger: 1")).toBeInTheDocument();
    expect(screen.getByText("Hand position: 5")).toBeInTheDocument();
  });

  it("rejects an unknown schema version with a readable error", async () => {
    responses.push({
      status: 200,
      body: { ...ARRANGEMENT, schema_version: 3 },
    });
    renderDialog();
    expect(await screen.findByRole("alert")).toHaveTextContent(/schema_version 3/);
    // Nothing is rendered from an untrusted version.
    expect(screen.queryByText("Finger: 1")).not.toBeInTheDocument();
  });

  it("explains a polyphonic input in the UI language, with the raw details", async () => {
    responses.push({
      status: 422,
      body: {
        detail: {
          code: "polyphonic_input",
          message:
            "simultaneous note onsets at tick 6346: pitches 47, 67 — this arranger optimizes a single melodic line; extract a monophonic melody track first",
          details: { tick: 6346, note_ids: ["a", "b"], pitches: [47, 67] },
        },
      },
    });
    renderDialog();
    const alert = await screen.findByRole("alert");
    // Localized explanation with the useful numbers…
    expect(alert).toHaveTextContent(/Several notes start at the same moment/);
    expect(alert).toHaveTextContent(/tick 6346/);
    expect(alert).toHaveTextContent(/pitches 47, 67/);
    // …plus the verbatim backend message for diagnostics.
    expect(alert).toHaveTextContent(/simultaneous note onsets at tick 6346/);
    expect(screen.queryByText("Finger: 1")).not.toBeInTheDocument();
  });

  it("opens without MIDI (Mode B): no request until a file is picked", async () => {
    const user = userEvent.setup();
    renderDialog(null);
    // Nothing is sent and a prominent prompt is shown instead.
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/Load a MIDI file/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open MIDI" })).toBeInTheDocument();
    // Picking a file starts the arrange request with that very file.
    const file = new File([new Uint8Array([9, 9, 9])], "riff.mid", {
      type: "audio/midi",
    });
    await user.upload(screen.getByLabelText("Open MIDI"), file);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    const form = fetchMock.mock.calls[0][1].body as FormData;
    expect((form.get("file") as File).name).toBe("riff.mid");
  });

  it("draws string 1 above string 6", async () => {
    responses.push({ status: 200, body: ARRANGEMENT });
    const { container } = renderDialog();
    await screen.findByText("Finger: 1");
    const lines = Array.from(
      container.querySelectorAll<SVGLineElement>("line[data-string]"),
    );
    expect(lines).toHaveLength(6);
    const yOf = (s: string) =>
      Number(lines.find((l) => l.dataset.string === s)!.getAttribute("y1"));
    expect(yOf("1")).toBeLessThan(yOf("6"));
    expect(yOf("1")).toBeLessThan(yOf("2"));
  });

  it("renders the selected note's state and every legal position interactively", async () => {
    responses.push({ status: 200, body: ARRANGEMENT });
    const { container } = renderDialog();
    await screen.findByText("Finger: 1");
    const svg = within(container.querySelector("svg") as unknown as HTMLElement);
    // Current spot, marked as pressed.
    const current = svg.getByRole("button", {
      name: "C4: string 3, fret 5, hand position 5, finger 1",
    });
    expect(current).toHaveAttribute("aria-pressed", "true");
    // Every alternative legal position is an interactive element…
    expect(svg.getByRole("button", { name: ALTERNATIVE })).toBeInTheDocument();
    // …including the open string, with every compatible hand position named.
    expect(
      svg.getByRole("button", {
        name: "C4: string 2, fret 0, hand positions 5, 6",
      }),
    ).toBeInTheDocument();
    // Illegal spots are never drawn: pitch 60 cannot sound on strings 1/5/6.
    expect(svg.queryByRole("button", { name: /string 1,/ })).toBeNull();
    expect(svg.queryByRole("button", { name: /string 5,/ })).toBeNull();
    expect(svg.queryByRole("button", { name: /string 6,/ })).toBeNull();
  });

  it("sends the correct lock and replaces the arrangement with the response", async () => {
    const locked = arrangement();
    const note = locked.notes[0];
    note.string = 4;
    note.fret = 10;
    note.hand_position = 10;
    note.locked = true;
    responses.push({ status: 200, body: ARRANGEMENT });
    responses.push({ status: 200, body: locked });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText("Finger: 1");
    await user.click(within(document.body).getByRole("button", { name: ALTERNATIVE }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [, init] = fetchMock.mock.calls[1];
    expect(formOverrides(init)).toEqual({
      version: 1,
      locks: [{ note_id: NOTE.id, string: 4, fret: 10 }],
    });
    // The confirmed backend response replaces the whole displayed arrangement.
    expect(await screen.findByText("Hand position: 10")).toBeInTheDocument();
    expect(screen.queryByText("Hand position: 5")).not.toBeInTheDocument();
    expect(
      within(document.body.querySelector("svg") as unknown as HTMLElement)
        .getByRole("button", { name: ALTERNATIVE }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("unlock removes the lock and re-runs the solver", async () => {
    const locked = arrangement();
    const note = locked.notes[0];
    note.string = 4;
    note.fret = 10;
    note.hand_position = 10;
    note.locked = true;
    responses.push({ status: 200, body: ARRANGEMENT });
    responses.push({ status: 200, body: locked });
    responses.push({ status: 200, body: ARRANGEMENT });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText("Finger: 1");
    await user.click(within(document.body).getByRole("button", { name: ALTERNATIVE }));
    await screen.findByText("Hand position: 10");
    await user.click(screen.getByRole("button", { name: "Unlock position" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [, init] = fetchMock.mock.calls[2];
    expect(formOverrides(init)).toEqual({ version: 1, locks: [] });
    // The automatic (backend-chosen) position is back on screen.
    expect(await screen.findByText("Hand position: 5")).toBeInTheDocument();
  });

  it("rolls back to the last confirmed locks when the backend rejects one", async () => {
    const locked = arrangement();
    const note = locked.notes[0];
    note.string = 4;
    note.fret = 10;
    note.hand_position = 10;
    note.locked = true;
    // The confirmed response also re-derives legal positions for the note.
    note.legal_positions.push({ string: 5, fret: 15 });
    note.legal_fingerings.push({
      string: 5,
      fret: 15,
      hand_position: 15,
      finger: 1,
    });
    responses.push({ status: 200, body: ARRANGEMENT });
    responses.push({ status: 200, body: locked });
    responses.push({
      status: 400,
      body: {
        detail: {
          code: "invalid_overrides",
          message: "lock for 'track:0/channel:0/note:1' contradicts the input",
          details: null,
        },
      },
    });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText("Finger: 1");
    await user.click(within(document.body).getByRole("button", { name: ALTERNATIVE }));
    await screen.findByText("Hand position: 10");
    await user.click(
      within(document.body).getByRole("button", {
        name: "C4: string 5, fret 15, hand position 15, finger 1",
      }),
    );
    // The backend message is shown, the editor stays open…
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /contradicts the MIDI input/,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      /lock for 'track:0\/channel:0\/note:1' contradicts the input/,
    );
    // …the displayed arrangement is still the last confirmed one…
    expect(screen.getByText("Hand position: 10")).toBeInTheDocument();
    // …and the rejected attempt carried the optimistic lock set (a second
    // click on the same note replaces its lock, same note_id key).
    const [, init] = fetchMock.mock.calls[2];
    expect(formOverrides(init)).toEqual({
      version: 1,
      locks: [{ note_id: NOTE.id, string: 5, fret: 15 }],
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("shows track candidates on an ambiguous_track error", async () => {
    responses.push({
      status: 422,
      body: {
        detail: {
          code: "ambiguous_track",
          message: "several note-bearing tracks",
          details: {
            tracks: [
              {
                track_index: 2,
                track_name: "Electric Guitar",
                channel: 0,
                program: 30,
                note_count: 146,
                drum: false,
              },
              {
                track_index: 3,
                track_name: "Distortion Guitar",
                channel: 1,
                program: 30,
                note_count: 84,
                drum: false,
              },
            ],
          },
        },
      },
    });
    renderDialog();
    expect(
      await screen.findByText("Electric Guitar — track 2, channel 0 — 146 notes"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Distortion Guitar — track 3, channel 1 — 84 notes"),
    ).toBeInTheDocument();
    // No arrangement is guessed or drawn before the user picks a track.
    expect(screen.queryByText("Finger: 1")).not.toBeInTheDocument();
  });

  it("repeats the request with the chosen track/channel", async () => {
    responses.push({
      status: 422,
      body: {
        detail: {
          code: "ambiguous_track",
          message: "several note-bearing tracks",
          details: {
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
          },
        },
      },
    });
    responses.push({ status: 200, body: ARRANGEMENT });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText(/Electric Guitar — track 2/);
    await user.click(
      screen.getByRole("button", { name: /Electric Guitar — track 2/ }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [, init] = fetchMock.mock.calls[1];
    const form = init.body as FormData;
    expect(formField(form, "track")).toBe("2");
    expect(formField(form, "channel")).toBe("0");
    expect(await screen.findByText("Finger: 1")).toBeInTheDocument();
  });

  it("ArrowLeft/ArrowRight move the selected note, but not from controls", async () => {
    const multi = arrangement();
    multi.notes = [JSON.parse(JSON.stringify(NOTE)), JSON.parse(JSON.stringify(NOTE2))];
    multi.metrics.note_count = 2;
    responses.push({ status: 200, body: multi });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText("Finger: 1");
    const dialog = screen.getByRole("dialog");

    fireEvent.keyDown(dialog, { key: "ArrowRight" });
    expect(await screen.findByText("Finger: 3")).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: "ArrowLeft" });
    expect(await screen.findByText("Finger: 1")).toBeInTheDocument();

    // Shortcuts stay quiet while the focus is on a control (note-list button).
    fireEvent.keyDown(
      screen.getByRole("button", { name: "C4: string 3, fret 5" }),
      { key: "ArrowRight" },
    );
    expect(screen.queryByText("Finger: 3")).not.toBeInTheDocument();
    // Clicking a note in the list also selects it.
    await user.click(
      screen.getByRole("button", { name: "D4: string 3, fret 7" }),
    );
    expect(await screen.findByText("Finger: 3")).toBeInTheDocument();
  });

  it("downloads the last confirmed backend response verbatim", async () => {
    responses.push({ status: 200, body: ARRANGEMENT });
    const user = userEvent.setup();
    const createElement = vi.spyOn(document, "createElement");
    renderDialog();
    await screen.findByText("Finger: 1");
    await user.click(
      screen.getByRole("button", { name: "Download arrangement.json" }),
    );
    // The dialog builds an anchor directly (never appended to the document),
    // so capture it through the createElement spy.
    const anchor = createElement.mock.results
      .map((r) => r.value)
      .filter((n): n is HTMLAnchorElement => n instanceof HTMLAnchorElement)
      .pop()!;
    expect(anchor).toBeTruthy();
    expect(anchor.download).toBe("song.guitar-arrangement.json");
    const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob;
    const text = JSON.parse(await blob.text()) as GuitarArrangement;
    expect(text.schema_version).toBe(2);
    expect(text.notes[0].id).toBe(NOTE.id);
  });

  it("offers melody reduction buttons on a polyphonic error", async () => {
    const reduced = arrangement();
    responses.push({
      status: 422,
      body: {
        detail: {
          code: "polyphonic_input",
          message: "simultaneous note onsets at tick 0: pitches 60, 67",
          details: { tick: 0, note_ids: ["a", "b"], pitches: [60, 67] },
        },
      },
    });
    responses.push({ status: 200, body: reduced });
    reduced.melody_reduction = { policy: "top", dropped_note_count: 0, dropped: [] };
    const user = userEvent.setup();
    renderDialog();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/Several notes start at the same moment/);
    expect(
      screen.getByRole("button", { name: "Take the top voice" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Take the bottom voice" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Take the top voice" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [, init] = fetchMock.mock.calls[1];
    const form = init.body as FormData;
    expect(formField(form, "melody")).toBe("top");
    expect(await screen.findByText("Finger: 1")).toBeInTheDocument();
    // The reduction is reported on screen.
    expect(screen.getByText("Melody: top voice · 0 notes dropped")).toBeInTheDocument();
  });

  it("auditions the arrangement through the engine at nominal tempo", async () => {
    responses.push({ status: 200, body: ARRANGEMENT });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText("Finger: 1");
    await user.click(screen.getByRole("button", { name: "Listen" }));
    // One NoteOpts per arrangement note: MIDI 60, 0..480 ticks at 120 BPM
    // (480 ticks_per_beat = 2 s/beat) → 0..0.5 s, on the source's GM program
    // (30 = distorted electric guitar in the fixture).
    expect(mockEngine.replaceNotes).toHaveBeenCalledWith(
      [
        {
          instrument: "distorted_electric_guitar",
          pitch: NOTE.pitch,
          start: 0,
          end: 0.5,
        },
      ],
      expect.any(Number),
    );
    expect(mockEngine.play).toHaveBeenCalled();
    // Pause hands over to the engine without restoring yet.
    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(mockEngine.pause).toHaveBeenCalled();
  });

  it("downloads the converted MIDI from the dedicated endpoint", async () => {
    responses.push({ status: 200, body: ARRANGEMENT });
    responses.push({ status: 200, body: "MThd-fake-midi-bytes" });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText("Finger: 1");
    await user.click(
      screen.getByRole("button", { name: "Download arrangement.mid" }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/arrange/guitar/midi");
    const form = init.body as FormData;
    expect(form.get("document")).toBeTruthy();
    const anchor = lastAnchor();
    expect(anchor.download).toBe("song.mid");
    const blob = vi.mocked(URL.createObjectURL).mock.calls.at(-1)![0] as Blob;
    expect(await blob.text()).toBe("MThd-fake-midi-bytes");
  });

  it("fetches, previews and downloads the ASCII tab", async () => {
    const TAB = "E4 |-0--3-|\nB3 |------|\nG3 |------|\nD3 |------|\nA2 |------|\nE2 |------|";
    responses.push({ status: 200, body: ARRANGEMENT });
    responses.push({ status: 200, body: TAB });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText("Finger: 1");
    await user.click(screen.getByRole("button", { name: "Tablature" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toBe("/arrange/guitar/tab");
    // Preview shows the tab (checked via textContent: findByText collapses
    // the multi-line whitespace inside <pre>).
    const pre = await screen.findByText((_, el) => el?.tagName === "PRE");
    expect(pre.textContent).toBe(TAB);
    await user.click(screen.getByRole("button", { name: "Download tab (.txt)" }));
    const anchor = lastAnchor();
    expect(anchor.download).toBe("song.tab.txt");
    const blob = vi.mocked(URL.createObjectURL).mock.calls.at(-1)![0] as Blob;
    expect(await blob.text()).toBe(TAB);
  });

  it("engraves the arrangement via /sheets and shows the PDF set", async () => {
    // A real (tiny) members-stored zip, as /sheets produces.
    const zip = zipSync({
      "full_score.pdf": new Uint8Array([1, 2, 3]),
      "01_acoustic_guitar_tab.pdf": new Uint8Array([4, 5]),
    });
    responses.push({ status: 200, body: ARRANGEMENT });
    responses.push({ status: 200, body: new Uint8Array([77, 84, 104, 100]) }); // MThd
    responses.push({ status: 200, body: zip });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText("Finger: 1");
    await user.click(screen.getByRole("button", { name: "PDF (score + tab)" }));
    // Request order: arrangement → MIDI, then MIDI → /sheets.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[1][0]).toBe("/arrange/guitar/midi");
    expect(fetchMock.mock.calls[2][0]).toBe("/sheets");
    const sheetsForm = fetchMock.mock.calls[2][1].body as FormData;
    expect(sheetsForm.get("quantized")).toBe("false");
    expect((sheetsForm.get("midi") as File).name).toBe("song.mid");
    // The engraved set opens in the familiar sheets dialog.
    expect(await screen.findByText("full_score.pdf")).toBeInTheDocument();
    expect(screen.getByText("01_acoustic_guitar_tab.pdf")).toBeInTheDocument();
  });

  it("shows a sheets failure (e.g. no MuseScore) without closing the lab", async () => {
    responses.push({ status: 200, body: ARRANGEMENT });
    responses.push({ status: 200, body: new Uint8Array([77]) });
    responses.push({ status: 503, body: "MuseScore was not found on the server" });
    const user = userEvent.setup();
    renderDialog();
    await screen.findByText("Finger: 1");
    await user.click(screen.getByRole("button", { name: "PDF (score + tab)" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /MuseScore was not found/,
    );
    // The lab stays open with its arrangement on screen.
    expect(screen.getByText("Hand position: 5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Listen" })).toBeInTheDocument();
  });

  it("has RU and EN strings for every guitar key", () => {
    const keys = Object.keys(EN).filter((k) => k.startsWith("guitar_"));
    expect(keys.length).toBeGreaterThanOrEqual(25);
    for (const key of keys) {
      expect(EN[key], key).toBeTruthy();
      expect(RU[key], key).toBeTruthy();
      // Actually translated, not copied.
      expect(RU[key]).not.toBe(EN[key]);
    }
  });

  it("the welcome-screen entry opens the lab in Mode B", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <GuitarArrangerEntry />
      </I18nProvider>,
    );
    expect(screen.getByRole("button", { name: "Edit fingering" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit fingering" }));
    // The dialog opens in its no-MIDI state and sends nothing.
    expect(await screen.findByText(/Load a MIDI file/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
