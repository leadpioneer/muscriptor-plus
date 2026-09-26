import { useRef, useState } from "react";
import { unzipSync } from "fflate";
import { Button } from "./Button";
import { SheetsDialog, type SheetFile } from "./SheetsDialog";
import { useI18n } from "../i18n";
import { track } from "../analytics";

/** The FastAPI `detail` of a failed response, or its raw body if it isn't one. */
async function errorDetail(resp: Response): Promise<string> {
  const text = await resp.text();
  try {
    return JSON.parse(text).detail ?? text;
  } catch {
    // not JSON — keep the raw body
    return text;
  }
}

/**
 * "Engrave a MIDI file you already have" path, on the welcome screen.
 *
 * Posts the upload straight to /sheets — the same endpoint the transcription
 * result's Sheet music button uses — and opens the same file picker over the
 * returned archive. No model involved: this only needs MuseScore on the
 * server, so it works even while a transcription is busy elsewhere.
 *
 * The upload is sent with quantized=false: unlike the transcription result,
 * where the server knows it snapped the notes to a beat grid, there is no way
 * to know how an arbitrary MIDI file's timing was produced — so engraving
 * keeps it as-is and lets MuseScore's MIDI import do the guessing.
 */
export function MidiToSheets() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const { t } = useI18n();
  // The unpacked archive, kept until the dialog is closed — same shape and
  // lifecycle as the transcription-result sheets in OutputBar.
  const [sheets, setSheets] = useState<{
    files: SheetFile[];
    zipBlob: Blob;
    zipFilename: string;
  } | null>(null);

  async function engrave(file: File) {
    track("download", { format: "sheets_upload" });
    setBusy(true);
    try {
      const form = new FormData();
      form.append("midi", file, file.name);
      form.append("quantized", "false");
      const resp = await fetch("/sheets", { method: "POST", body: form });
      if (!resp.ok) throw new Error(await errorDetail(resp));
      const zipBlob = await resp.blob();
      // The members are stored, not deflated, so this unpacking is a copy out
      // of the buffer rather than an inflate of every PDF (see OutputBar).
      const unpacked = unzipSync(new Uint8Array(await zipBlob.arrayBuffer()));
      const files = Object.entries(unpacked).map(([name, bytes]) => ({
        name,
        // Unpacked out of an ArrayBuffer, so never the SharedArrayBuffer that
        // fflate's looser return type leaves open (and that Blob rejects).
        bytes: bytes as Uint8Array<ArrayBuffer>,
      }));
      if (files.length === 0) throw new Error("the server returned an empty archive");
      setSheets({
        files,
        zipBlob,
        zipFilename: file.name.replace(/\.[^.]+$/, "") + "_sheets.zip",
      });
    } catch (e) {
      track("download_error", {
        format: "sheets_upload",
        message: (e as Error).message,
      });
      alert(t("alert_sheets_failed", { message: (e as Error).message }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <input
        type="file"
        accept=".mid,.midi,audio/midi"
        hidden
        ref={inputRef}
        onChange={(e) => {
          const file = e.target.files?.[0];
          // Reset so picking the same file again still fires onChange.
          e.target.value = "";
          if (file) engrave(file);
        }}
      />
      <Button
        kind="ghost"
        className="px-1 py-0.5 text-sm text-muted underline underline-offset-4 hover:bg-transparent enabled:hover:text-content"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        {busy ? t("midi_sheets_busy") : t("midi_sheets_idle")}
      </Button>
      {sheets && (
        <SheetsDialog
          files={sheets.files}
          zipBlob={sheets.zipBlob}
          zipFilename={sheets.zipFilename}
          // No beat-detection story to tell about an uploaded MIDI — the
          // dialog's "bar lines are guesses" banner is transcription-specific.
          quantized={true}
          onClose={() => setSheets(null)}
        />
      )}
    </>
  );
}