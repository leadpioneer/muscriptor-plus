/**
 * Guitar Arranger Lab — diagnostic fingering editor.
 *
 * The backend is the single source of truth: a click only produces a lock
 * (override), after which the ORIGINAL midi plus the FULL lock set is sent to
 * POST /arrange/guitar and the whole displayed arrangement is replaced by the
 * response. On a rejected lock the local set rolls back to the last confirmed
 * one and the previous arrangement stays on screen.
 *
 * Two sources are supported: the MIDI of the current transcription (handed in
 * by OutputBar, no re-upload) and any local .mid/.midi file picked here.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { unzipSync } from "fflate";
import { Button } from "./Button";
import { GuitarFretboard } from "./GuitarFretboard";
import { GuitarPhraseNotes } from "./GuitarPhraseNotes";
import { SheetsDialog, type SheetFile } from "./SheetsDialog";
import { useAudioEngine } from "../hooks/useAudioEngine";
import { GM_PROGRAM, type NoteOpts } from "../audio";
import { useI18n } from "../i18n";
import { EN } from "../i18n/en";
import { track } from "../analytics";
import {
  arrangeGuitar,
  buildOverrides,
  parseTrackCandidates,
  phraseHandMetrics,
  pitchName,
  GuitarArrangementError,
  type ArrangedNote,
  type FingeringLock,
  type GuitarArrangement,
  type GuitarTrackCandidate,
} from "../guitar-arrangement";

type Selection = { track?: number; channel?: number };
type Confirmed = {
  text: string;
  arrangement: GuitarArrangement;
  locks: Record<string, FingeringLock>;
};

/** A failed arrange request: backend code (when structured) + raw message. */
type UiError = { code: string | null; message: string; details: unknown };

/** Query parameters for the localized message of a known error code. */
function errorParams(code: string, details: unknown): Record<string, string | number> {
  const d =
    typeof details === "object" && details !== null
      ? (details as Record<string, unknown>)
      : {};
  switch (code) {
    case "polyphonic_input":
      return {
        tick: Number(d.tick ?? 0),
        pitches: Array.isArray(d.pitches) ? d.pitches.join(", ") : "",
      };
    case "unplayable_note":
      return {
        pitch: Number(d.pitch ?? 0),
        low: Number(d.low_pitch ?? 0),
        high: Number(d.high_pitch ?? 0),
      };
    default:
      return {};
  }
}

/** True when arrow-key navigation must not fire (typing or on a control). */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "SELECT" ||
    tag === "TEXTAREA" ||
    tag === "BUTTON" ||
    target.isContentEditable
  );
}

/** Download helper: blob → transient object URL → anchor click. */
function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function reconcileSelection(
  arrangement: GuitarArrangement,
  keep: { phrase: number; noteId: string | null } | null,
): { phrase: number; noteId: string | null } {
  const indexes = arrangement.phrases.map((p) => p.index);
  const phrase =
    keep !== null && indexes.includes(keep.phrase) ? keep.phrase : (indexes[0] ?? 0);
  const notes = arrangement.notes.filter((n) => n.phrase === phrase);
  const note = notes.find((n) => n.id === keep?.noteId) ?? notes[0] ?? null;
  return { phrase, noteId: note?.id ?? null };
}

/** Nominal playback tempo: the document has no tempo map, so 120 BPM (2 s per
 *  beat) is the documented constant. Relative rhythm is exact. */
const NOMINAL_BPM = 120;

function playbackNotes(arrangement: GuitarArrangement): NoteOpts[] {
  const program = arrangement.source.program ?? 24;
  const instrument =
    Object.entries(GM_PROGRAM).find(([, p]) => p === program)?.[0] ??
    "acoustic_guitar";
  const sec = (ticks: number) =>
    (ticks / arrangement.source.ticks_per_beat) * (60 / NOMINAL_BPM);
  return arrangement.notes.map((n) => ({
    instrument,
    pitch: n.pitch,
    start: sec(n.onset_ticks),
    end: sec(n.offset_ticks),
  }));
}

export function GuitarArrangerDialog(props: {
  /** The transcription result's MIDI (Mode A), or null to start from a
   *  picked file (Mode B — the welcome-screen entry point). */
  initialMidi: Blob | null;
  initialFilename: string;
  onClose: () => void;
}) {
  const { onClose } = props;
  const { t } = useI18n();

  const [sourceMidi, setSourceMidi] = useState<Blob | null>(props.initialMidi);
  const [sourceFilename, setSourceFilename] = useState(props.initialFilename);
  const sourceRef = useRef<{ midi: Blob | null; filename: string }>({
    midi: props.initialMidi,
    filename: props.initialFilename,
  });
  sourceRef.current = { midi: sourceMidi, filename: sourceFilename };

  const [applied, setApplied] = useState<Confirmed | null>(null);
  // The last confirmed state, readable inside the async run below without
  // re-creating it (and thus without retriggering the initial-load effect).
  const appliedRef = useRef<Confirmed | null>(null);
  appliedRef.current = applied;

  const [locks, setLocks] = useState<Record<string, FingeringLock>>({});
  const [melodyPolicy, setMelodyPolicy] = useState("off");
  const melodyRef = useRef(melodyPolicy);
  melodyRef.current = melodyPolicy;
  const [candidates, setCandidates] = useState<GuitarTrackCandidate[] | null>(null);
  const [selection, setSelection] = useState<Selection>({});
  const selectionRef = useRef<Selection>({});
  selectionRef.current = selection;

  const [phrase, setPhrase] = useState(0);
  const [noteId, setNoteId] = useState<string | null>(null);
  const phraseRef = useRef(phrase);
  phraseRef.current = phrase;
  const noteIdRef = useRef(noteId);
  noteIdRef.current = noteId;

  const [loading, setLoading] = useState(props.initialMidi !== null);
  const [error, setError] = useState<UiError | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const emptyInputRef = useRef<HTMLInputElement | null>(null);

  // Playback ("listen to what the arranger did"): the lab auditions its notes
  // through the shared engine, snapshotting the transcription's note set and
  // restoring it when the dialog closes.
  const audio = useAudioEngine();
  const snapshotRef = useRef<NoteOpts[] | null>(null);
  const [playing, setPlaying] = useState(false);
  const [tabText, setTabText] = useState<string | null>(null);
  const [tabOpen, setTabOpen] = useState(false);
  // The engraved PDF set (score + tab) built from the arrangement's MIDI via
  // the existing /sheets pipeline — the same dialog the transcription uses.
  const [pdfBusy, setPdfBusy] = useState<string | null>(null);
  const [pdf, setPdf] = useState<{
    files: SheetFile[];
    zipBlob: Blob;
    zipFilename: string;
  } | null>(null);
  const [pdfOpen, setPdfOpen] = useState(false);

  /**
   * One arrange round trip. `lockSet` is what the user is asking for; only a
   * successful response confirms it (and the displayed result) atomically.
   */
  const run = useCallback(
    async (
      sel: Selection,
      lockSet: Record<string, FingeringLock>,
      keep: { phrase: number; noteId: string | null } | null,
    ) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);
      setError(null);
      if (sourceRef.current.midi === null) {
        setLoading(false);
        return;
      }
      try {
        const response = await arrangeGuitar({
          midi: sourceRef.current.midi,
          filename: sourceRef.current.filename,
          track: sel.track,
          channel: sel.channel,
          melody: melodyRef.current,
          overrides:
            Object.keys(lockSet).length > 0 ? buildOverrides(lockSet) : undefined,
          signal: controller.signal,
        });
        // Confirmed: the backend result replaces everything we displayed.
        setApplied({
          text: response.text,
          arrangement: response.arrangement,
          locks: lockSet,
        });
        setLocks(lockSet);
        setCandidates(null);
        const next = reconcileSelection(response.arrangement, keep);
        setPhrase(next.phrase);
        setNoteId(next.noteId);
        // Auditioning an older arrangement? Swap in the fresh one (paused).
        if (snapshotRef.current !== null) {
          const notes = playbackNotes(response.arrangement);
          audio.replaceNotes(notes, Math.max(1, ...notes.map((n) => n.end)) + 0.3);
          setPlaying(false);
        }
        // Any re-solve invalidates the rendered tab and the PDF set.
        setTabText(null);
        setTabOpen(false);
        setPdf(null);
        setPdfOpen(false);
      } catch (e) {
        if (controller.signal.aborted) return; // superseded by a newer click
        if (e instanceof GuitarArrangementError && e.code === "ambiguous_track") {
          setCandidates(parseTrackCandidates(e.details));
        } else {
          // A rejected lock rolls the optimistic set back; the last confirmed
          // arrangement stays on screen and the editor stays open.
          setLocks(appliedRef.current?.locks ?? {});
          setError(
            e instanceof GuitarArrangementError
              ? { code: e.code, message: e.message, details: e.details }
              : { code: null, message: e instanceof Error ? e.message : String(e), details: null },
          );
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // Initial load (and reload when Mode B swaps in another MIDI file).
  useEffect(() => {
    if (sourceMidi === null) return; // Mode B entry: no MIDI picked yet
    run({}, {}, null);
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceMidi, sourceFilename]);

  function pickCandidate(c: GuitarTrackCandidate) {
    const sel = { track: c.track_index, channel: c.channel };
    setSelection(sel);
    run(sel, {}, null);
  }

  function pickFile(file: File) {
    // A different MIDI invalidates every lock, selection and melody choice.
    track("guitar_arranger", { action: "open_midi" });
    setApplied(null);
    setLocks({});
    setMelodyPolicy("off");
    setCandidates(null);
    setSelection({});
    setNoteId(null);
    setPhrase(0);
    setError(null);
    setSourceMidi(file);
    setSourceFilename(file.name);
  }

  function takeMelody(policy: string) {
    track("guitar_arranger", { action: "melody", policy });
    melodyRef.current = policy; // the run below must see it immediately
    setMelodyPolicy(policy);
    run(selectionRef.current, locks, null);
  }

  function selectPhrase(index: number) {
    setPhrase(index);
    const notes = applied?.arrangement.notes.filter((n) => n.phrase === index) ?? [];
    setNoteId(notes[0]?.id ?? null);
  }

  function selectNote(id: string) {
    setNoteId(id);
  }

  function moveNote(delta: -1 | 1) {
    if (applied === null) return;
    const notes = applied.arrangement.notes.filter((n) => n.phrase === phrase);
    const index = notes.findIndex((n) => n.id === noteIdRef.current);
    if (index === -1) return;
    const next = notes[Math.min(notes.length - 1, Math.max(0, index + delta))];
    if (next) setNoteId(next.id);
  }

  function lockPosition(string: number, fret: number) {
    if (selectedNote === null || loading) return;
    track("guitar_arranger", { action: "lock" });
    run(
      selectionRef.current,
      {
        ...locks,
        [selectedNote.id]: { note_id: selectedNote.id, string, fret },
      },
      { phrase: phraseRef.current, noteId: noteIdRef.current },
    );
  }

  function unlock() {
    if (selectedNote === null || loading || !selectedNote.locked) return;
    track("guitar_arranger", { action: "unlock" });
    const next = { ...locks };
    delete next[selectedNote.id];
    run(selectionRef.current, next, {
      phrase: phraseRef.current,
      noteId: noteIdRef.current,
    });
  }

  function download() {
    if (applied === null) return;
    track("guitar_arranger", { action: "download" });
    const url = URL.createObjectURL(
      new Blob([applied.text], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = sourceFilename.replace(/\.[^.]+$/, "") + ".guitar-arrangement.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  function stem(): string {
    return sourceFilename.replace(/\.[^.]+$/, "") || "arrangement";
  }

  async function togglePlay() {
    if (playing) {
      audio.pause();
      setPlaying(false);
      return;
    }
    if (applied === null) return;
    track("guitar_arranger", { action: "play" });
    const notes = playbackNotes(applied.arrangement);
    if (snapshotRef.current === null) {
      snapshotRef.current = audio.snapshotNotes();
    }
    audio.replaceNotes(notes, Math.max(1, ...notes.map((n) => n.end)) + 0.3);
    await audio.play();
    setPlaying(true);
  }

  /** Give the shared engine its transcription notes back. */
  function restoreEngine() {
    if (snapshotRef.current !== null) {
      audio.replaceNotes(snapshotRef.current);
      snapshotRef.current = null;
    }
    audio.stop();
    setPlaying(false);
  }

  // Leaving the lab always hands the engine back to the transcription.
  useEffect(() => restoreEngine, []);

  async function downloadMidi() {
    if (applied === null) return;
    track("guitar_arranger", { action: "download_midi" });
    const form = new FormData();
    form.append(
      "document",
      new Blob([applied.text], { type: "application/json" }),
      "arrangement.json",
    );
    const resp = await fetch("/arrange/guitar/midi", { method: "POST", body: form });
    if (!resp.ok) {
      setError({ code: null, message: await resp.text(), details: null });
      return;
    }
    saveBlob(await resp.blob(), stem() + ".mid");
  }

  async function toggleTab() {
    if (tabText !== null) {
      setTabOpen(false);
      return;
    }
    if (applied === null) return;
    track("guitar_arranger", { action: "tab" });
    const form = new FormData();
    form.append(
      "document",
      new Blob([applied.text], { type: "application/json" }),
      "arrangement.json",
    );
    const resp = await fetch("/arrange/guitar/tab", { method: "POST", body: form });
    if (!resp.ok) {
      setError({ code: null, message: await resp.text(), details: null });
      return;
    }
    setTabText(await resp.text());
    setTabOpen(true);
  }

  async function downloadTab() {
    if (tabText === null) return;
    saveBlob(new Blob([tabText], { type: "text/plain" }), stem() + ".tab.txt");
  }

  /**
   * Engrave the arrangement as notation: convert the confirmed document to
   * MIDI (the same endpoint the download button uses) and hand it to the
   * existing /sheets pipeline, which answers with score + tab PDFs.
   */
  async function downloadPdf() {
    if (applied === null || pdfBusy !== null) return;
    track("guitar_arranger", { action: "pdf" });
    setPdfBusy(t("guitar_pdf_busy"));
    try {
      const midiForm = new FormData();
      midiForm.append(
        "document",
        new Blob([applied.text], { type: "application/json" }),
        "arrangement.json",
      );
      const midiResp = await fetch("/arrange/guitar/midi", {
        method: "POST",
        body: midiForm,
      });
      if (!midiResp.ok) {
        throw new Error(await midiResp.text());
      }
      const midiBlob = await midiResp.blob();
      const sheetsForm = new FormData();
      sheetsForm.append("midi", midiBlob, stem() + ".mid");
      sheetsForm.append("quantized", "false");
      const sheetsResp = await fetch("/sheets", { method: "POST", body: sheetsForm });
      if (!sheetsResp.ok) {
        throw new Error(await sheetsResp.text());
      }
      const zipBlob = await sheetsResp.blob();
      // Stored, not deflated members — unpacking is a copy, same as OutputBar.
      const unpacked = unzipSync(new Uint8Array(await zipBlob.arrayBuffer()));
      const files: SheetFile[] = Object.entries(unpacked).map(([name, bytes]) => ({
        name,
        bytes: bytes as Uint8Array<ArrayBuffer>,
      }));
      if (files.length === 0) {
        throw new Error("the server returned an empty archive");
      }
      setPdf({ files, zipBlob, zipFilename: stem() + "_sheets.zip" });
      setPdfOpen(true);
    } catch (e) {
      setError({ code: null, message: e instanceof Error ? e.message : String(e), details: null });
    } finally {
      setPdfBusy(null);
    }
  }

  const arrangement = applied?.arrangement ?? null;
  const phraseNotes: ArrangedNote[] =
    arrangement?.notes.filter((n) => n.phrase === phrase) ?? [];
  const selectedNote =
    phraseNotes.find((n) => n.id === noteId) ?? phraseNotes[0] ?? null;
  const handMetrics = phraseHandMetrics(phraseNotes);
  const phraseInfo = arrangement?.phrases.find((p) => p.index === phrase) ?? null;

  return (
    // Above the page grain, below the drag-and-drop overlay (SheetsDialog pattern).
    <div
      className="fixed inset-0 z-[150] flex items-center justify-center bg-[rgba(11,12,16,0.72)] p-6 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("guitar_title")}
        className="flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-card border border-line-strong bg-surface shadow-overlay"
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
          if (
            (e.key === "ArrowLeft" || e.key === "ArrowRight") &&
            !isTypingTarget(e.target)
          ) {
            e.preventDefault();
            moveNote(e.key === "ArrowLeft" ? -1 : 1);
          }
        }}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="m-0 text-base font-semibold text-content">{t("guitar_title")}</h2>
          <Button kind="ghost" pad="p-1" onClick={onClose} aria-label={t("close")}>
            ✕
          </Button>
        </div>

        {/* Source row: the current transcription's MIDI or an external file. */}
        {sourceMidi !== null && (
          <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
            <span className="truncate font-mono text-xs text-muted" title={sourceFilename}>
              {sourceFilename}
            </span>
            <label className="ml-auto cursor-pointer font-mono text-xs text-accent hover:underline">
              <input
                type="file"
                accept=".mid,.midi,audio/midi"
                className="sr-only"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) pickFile(file);
                  e.target.value = "";
                }}
              />
              {t("guitar_open_midi")}
            </label>
          </div>
        )}

        {sourceMidi === null && !loading && (
          // Mode B entry point: no MIDI anywhere yet — ask for one.
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <p className="m-0 max-w-sm text-sm text-muted">{t("guitar_no_source")}</p>
            <input
              ref={emptyInputRef}
              type="file"
              accept=".mid,.midi,audio/midi"
              className="sr-only"
              aria-label={t("guitar_open_midi")}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) pickFile(file);
                e.target.value = "";
              }}
            />
            <Button
              kind="primary"
              size="text-base"
              pad="px-7 py-3"
              onClick={() => emptyInputRef.current?.click()}
            >
              {t("guitar_open_midi")}
            </Button>
          </div>
        )}

        {candidates !== null && (
          <div className="border-b border-line px-5 py-3">
            <p className="m-0 mb-2 text-[13px] text-content">{t("guitar_pick_track")}</p>
            <div className="flex flex-col gap-1.5">
              {candidates.map((c) => (
                <Button
                  key={`${c.track_index}:${c.channel}`}
                  pad="px-3 py-1.5"
                  className="justify-start text-left font-mono text-[12px]"
                  disabled={loading}
                  onClick={() => pickCandidate(c)}
                >
                  {t("guitar_track_option", {
                    name: c.track_name ?? t("guitar_track_unnamed"),
                    track: c.track_index,
                    channel: c.channel,
                    n: c.note_count,
                  })}
                </Button>
              ))}
            </div>
          </div>
        )}

        {error !== null && (
          <div
            role="alert"
            title={error.message}
            className="border-b border-line bg-[#3a2020] px-5 py-2.5 text-[13px] text-[#f2b8b5]"
          >
            {/* Known backend codes get a localized, human explanation (with
                the useful details); anything else shows the raw message. */}
            {error.code !== null && EN[`guitar_error_${error.code}`] !== undefined
              ? t(`guitar_error_${error.code}`, errorParams(error.code, error.details))
              : error.message}
            {error.code !== null && EN[`guitar_error_${error.code}`] !== undefined && (
              <span className="mt-1 block font-mono text-[11px] text-[#f2b8b5]/70">
                {error.message}
              </span>
            )}
            {error.code === "polyphonic_input" && (
              <div className="mt-2 flex gap-2">
                <Button
                  kind="primary"
                  pad="px-3 py-1.5"
                  size="text-xs"
                  disabled={loading}
                  onClick={() => takeMelody("top")}
                >
                  {t("guitar_take_top")}
                </Button>
                <Button
                  pad="px-3 py-1.5"
                  size="text-xs"
                  disabled={loading}
                  onClick={() => takeMelody("bottom")}
                >
                  {t("guitar_take_bottom")}
                </Button>
              </div>
            )}
          </div>
        )}

        {arrangement !== null && (
          <>
            {/* Phrase list */}
            <div className="flex flex-wrap items-center gap-1.5 border-b border-line px-5 py-3">
              {arrangement.phrases.map((p) => {
                const count = arrangement.notes.filter((n) => n.phrase === p.index).length;
                const active = p.index === phrase;
                return (
                  <Button
                    key={p.index}
                    pad="px-3 py-1"
                    size="text-xs"
                    aria-pressed={active}
                    className={active ? "border-accent bg-accent/15 text-content" : ""}
                    onClick={() => selectPhrase(p.index)}
                  >
                    {t("guitar_phrase_option", { n: p.index + 1, count })}
                  </Button>
                );
              })}
              {arrangement.melody_reduction.policy !== "off" && (
                <span className="ml-auto font-mono text-[11px] text-faint">
                  {t("guitar_melody_summary", {
                    policy: t(`guitar_melody_${arrangement.melody_reduction.policy}`),
                    n: arrangement.melody_reduction.dropped_note_count,
                  })}
                </span>
              )}
            </div>

            {/* Fretboard + note list of the selected phrase */}
            <div className="grid grid-cols-[1fr_190px] gap-4 overflow-y-auto px-5 py-4 max-[760px]:grid-cols-1">
              <div className="min-w-0">
                {selectedNote !== null && (
                  <GuitarFretboard
                    arrangement={arrangement}
                    note={selectedNote}
                    disabled={loading}
                    onSelect={(_id, s, f) => lockPosition(s, f)}
                  />
                )}
                <p className="mt-2 text-[12px] text-muted">{t("guitar_hint")}</p>
              </div>
              <GuitarPhraseNotes
                notes={phraseNotes}
                selectedNoteId={selectedNote?.id ?? null}
                disabled={loading}
                onSelect={selectNote}
              />
            </div>

            {/* Selected note + phrase metrics */}
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line px-5 py-3 text-[13px]">
              {selectedNote !== null && (
                <>
                  <span className="font-semibold text-content">
                    {pitchName(selectedNote.pitch)}
                  </span>
                  <span className="text-muted">
                    {t("guitar_hand_position", { n: selectedNote.hand_position })}
                  </span>
                  <span className="text-muted">
                    {t("guitar_finger_label", { n: selectedNote.finger })}
                  </span>
                  {selectedNote.locked && (
                    <Button
                      pad="px-2.5 py-1"
                      size="text-xs"
                      disabled={loading}
                      onClick={unlock}
                    >
                      {t("guitar_unlock")}
                    </Button>
                  )}
                </>
              )}
              <span className="ml-auto flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-faint">
                <span>{t("guitar_position_changes", { n: handMetrics.changes })}</span>
                <span>{t("guitar_hand_travel", { n: handMetrics.travel })}</span>
                <span>{t("guitar_largest_shift", { n: handMetrics.largest })}</span>
                <span>{t("guitar_phrase_cost", { n: phraseInfo?.cost ?? 0 })}</span>
              </span>
            </div>
          </>
        )}

        {/* Tab preview (fetched lazily, invalidated by every re-solve). */}
        {tabOpen && tabText !== null && (
          <div className="border-b border-line px-5 py-3">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-medium text-content">
                {t("guitar_tab_title")}
              </span>
              <Button
                kind="ghost"
                pad="px-2 py-0.5"
                size="text-xs"
                className="text-accent underline underline-offset-4"
                onClick={downloadTab}
              >
                {t("guitar_download_tab")}
              </Button>
            </div>
            <pre className="mt-2 max-h-40 overflow-auto font-mono text-[10px] leading-4 text-muted">
              {tabText}
            </pre>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3.5">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              disabled={applied === null || loading}
              title={t("guitar_play_title")}
              onClick={togglePlay}
            >
              {playing ? t("guitar_pause") : t("guitar_play")}
            </Button>
            <Button disabled={applied === null || loading} onClick={downloadMidi}>
              {t("guitar_download_midi")}
            </Button>
            <Button
              disabled={applied === null || loading}
              onClick={toggleTab}
              aria-pressed={tabOpen}
            >
              {t("guitar_tab_button")}
            </Button>
            <Button
              disabled={applied === null || loading || pdfBusy !== null}
              onClick={downloadPdf}
            >
              {pdfBusy ?? t("guitar_pdf")}
            </Button>
            <span className="font-mono text-xs text-faint">
              {loading ? t("guitar_loading") : ""}
            </span>
          </div>
          <div className="flex gap-2">
            <Button kind="primary" disabled={applied === null} onClick={download}>
              {t("guitar_download")}
            </Button>
            <Button onClick={onClose}>{t("close")}</Button>
          </div>
        </div>

        {pdf && pdfOpen && (
          <SheetsDialog
            files={pdf.files}
            zipBlob={pdf.zipBlob}
            zipFilename={pdf.zipFilename}
            // No beat-grid story applies to a converted arrangement MIDI —
            // same reasoning as the welcome screen's MIDI→sheets path.
            quantized={true}
            onClose={() => setPdfOpen(false)}
          />
        )}
      </div>
    </div>
  );
}

/**
 * Welcome-screen entry point for the lab (next to "MIDI → sheet music").
 *
 * Opens the dialog with no MIDI attached: the dialog shows its file prompt,
 * and the user picks any .mid/.midi from disk. No transcription, no model,
 * no audio — the lab works on its own from here.
 */
export function GuitarArrangerEntry() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        kind="ghost"
        className="px-1 py-0.5 text-sm text-muted underline underline-offset-4 hover:bg-transparent enabled:hover:text-content"
        onClick={() => {
          track("guitar_arranger", { action: "open_welcome" });
          setOpen(true);
        }}
      >
        {t("guitar_open")}
      </Button>
      {open && (
        <GuitarArrangerDialog
          initialMidi={null}
          initialFilename=""
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
