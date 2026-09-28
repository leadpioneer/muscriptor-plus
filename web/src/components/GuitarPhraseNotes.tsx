/**
 * Compact note sequence of the selected phrase, next to the fretboard.
 *
 * Pure HTML buttons (not SVG) so keyboard focus, names and the lock state
 * come for free from the platform. Lock state is never conveyed by color
 * alone: locked rows show a padlock glyph and say so in their accessible name.
 */
import clsx from "clsx";
import { useI18n } from "../i18n";
import { pitchName, type ArrangedNote } from "../guitar-arrangement";

function LockGlyph() {
  return (
    <svg
      viewBox="0 0 12 12"
      width={10}
      height={10}
      aria-hidden
      className="inline-block shrink-0"
    >
      <rect x={2} y={5} width={8} height={6} rx={1} className="fill-[#e0b25a]" />
      <path
        d="M4 5V3.5a2 2 0 1 1 4 0V5"
        fill="none"
        className="stroke-[#e0b25a]"
        strokeWidth={1.5}
      />
    </svg>
  );
}

export function GuitarPhraseNotes(props: {
  notes: ArrangedNote[];
  selectedNoteId: string | null;
  disabled: boolean;
  onSelect: (noteId: string) => void;
}) {
  const { notes, selectedNoteId, disabled, onSelect } = props;
  const { t } = useI18n();

  return (
    <ul className="m-0 flex max-h-72 list-none flex-col gap-0.5 overflow-y-auto p-0">
      {notes.map((note) => {
        const selected = note.id === selectedNoteId;
        return (
          <li key={note.id}>
            <button
              type="button"
              disabled={disabled}
              aria-current={selected ? "true" : undefined}
              aria-label={t("guitar_note_aria", {
                note: pitchName(note.pitch),
                s: note.string,
                f: note.fret,
              })}
              title={t("guitar_midi_pitch", { pitch: note.pitch })}
              onClick={() => onSelect(note.id)}
              className={clsx(
                "flex w-full items-center gap-2 rounded-md border px-2 py-1 text-left font-mono text-[12px]",
                "focus-visible:outline-2 focus-visible:outline-accent",
                selected
                  ? "border-accent bg-accent/15 text-content"
                  : "border-line text-muted hover:bg-surface-2",
                note.locked && "border-l-2 border-l-[#e0b25a]",
              )}
            >
              <span className="min-w-9 font-semibold text-content">
                {pitchName(note.pitch)}
              </span>
              <span>
                {t("guitar_string_fret", { s: note.string, f: note.fret })}
              </span>
              <span className="text-faint">
                {t("guitar_finger_short", {
                  n: note.finger ?? t("guitar_finger_unknown"),
                })}
              </span>
              {note.locked && (
                <span className="ml-auto flex items-center gap-1 text-[#e0b25a]">
                  <LockGlyph />
                  {t("guitar_locked")}
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
