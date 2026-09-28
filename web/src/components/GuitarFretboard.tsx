/**
 * SVG fretboard for the Guitar Arranger Lab.
 *
 * String 1 (highest) is drawn on top — the y coordinate is computed from the
 * user-facing string number, never from the open_pitches array index. Only
 * the selected note's legal positions are rendered: the current spot as a
 * filled marker with the finger number, the alternatives as focusable
 * buttons (role="button" + tabIndex so SVG stays keyboard accessible).
 */
import { useI18n } from "../i18n";
import {
  fingeringsAt,
  pitchName,
  type ArrangedNote,
  type GuitarArrangement,
} from "../guitar-arrangement";

const INLAY_FRETS = [3, 5, 7, 9, 12, 15, 17, 19, 21, 24];
const DOUBLE_INLAYS = new Set([12, 24]);

const OPEN_WIDTH = 34;
const FRET_WIDTH = 42;
const STRING_GAP = 30;
const PAD_TOP = 18;
const PAD_BOTTOM = 34;

export function GuitarFretboard(props: {
  arrangement: GuitarArrangement;
  note: ArrangedNote;
  /** The whole onset event: every chord note stays visible on the neck. */
  chordNotes?: ArrangedNote[];
  /** Barre annotations of the current event (drawn as a bracket line). */
  barres?: {
    finger: number;
    fret: number;
    from_string: number;
    to_string: number;
  }[];
  disabled: boolean;
  onSelect: (noteId: string, string: number, fret: number) => void;
}) {
  const { arrangement, note, chordNotes = [], barres = [], disabled, onSelect } = props;
  const { t } = useI18n();
  const { max_fret, open_pitches } = arrangement.instrument;
  const stringCount = open_pitches.length;
  const width = OPEN_WIDTH + max_fret * FRET_WIDTH + 16;
  const height = PAD_TOP + PAD_BOTTOM + (stringCount - 1) * STRING_GAP;

  const stringY = (s: number) => PAD_TOP + (s - 1) * STRING_GAP;
  const fretX = (f: number) => OPEN_WIDTH + f * FRET_WIDTH;
  const fretCenter = (f: number) => fretX(f - 1) + FRET_WIDTH / 2;

  const handStart = note.hand_position;
  const handEnd = handStart + 3;
  const alternatives = note.legal_positions.filter(
    (p) => !(p.string === note.string && p.fret === note.fret),
  );

  function describe(p: { string: number; fret: number }): string {
    const combos = fingeringsAt(note, p.string, p.fret);
    const pitch = pitchName(note.pitch);
    if (combos.length === 1) {
      const { hand_position, finger } = combos[0];
      return t("guitar_aria_position", {
        note: pitch,
        s: p.string,
        f: p.fret,
        hp: hand_position,
        fg: finger,
      });
    }
    const hand = combos.map((c) => c.hand_position).join(", ");
    return t("guitar_aria_position_multi", {
      note: pitch,
      s: p.string,
      f: p.fret,
      hp: hand,
    });
  }

  /** Tooltip text: every hand_position/finger pair that can play this spot. */
  function tooltip(p: { string: number; fret: number }): string {
    return fingeringsAt(note, p.string, p.fret)
      .map((c) => t("guitar_fingering_combo", { hp: c.hand_position, fg: c.finger }))
      .join("; ");
  }

  function activate(e: React.KeyboardEvent, string: number, fret: number) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(note.id, string, fret);
    }
  }


  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        className="max-w-none"
        role="img"
        aria-label={t("guitar_fretboard_aria", {
          note: pitchName(note.pitch),
          s: note.string,
          f: note.fret,
        })}
      >
        <title>{t("guitar_fretboard_title")}</title>

        {/* Fretboard plate + fret wires */}
        <rect
          x={fretX(0)}
          y={PAD_TOP - 10}
          width={max_fret * FRET_WIDTH}
          height={height - PAD_TOP - PAD_BOTTOM + 20}
          className="fill-[#2a2620] stroke-none"
        />
        {Array.from({ length: max_fret + 1 }, (_, f) => (
          <line
            key={f}
            x1={fretX(f)}
            x2={fretX(f)}
            y1={PAD_TOP - 10}
            y2={height - PAD_BOTTOM + 10}
            className={f === 0 ? "stroke-[#d8cfc0]" : "stroke-[#8b8577]"}
            strokeWidth={f === 0 ? 4 : 1.5}
          />
        ))}
        {/* Fret numbers */}
        {Array.from({ length: max_fret }, (_, i) => i + 1).map((f) => (
          <text
            key={f}
            x={fretCenter(f)}
            y={height - PAD_BOTTOM + 26}
            textAnchor="middle"
            className="fill-faint font-mono text-[10px]"
          >
            {f}
          </text>
        ))}
        {/* Inlay markers — double dots on 12 and 24 */}
        {INLAY_FRETS.filter((f) => f <= max_fret).map((f) => {
          const midY = PAD_TOP + ((stringCount - 1) * STRING_GAP) / 2;
          const cx = fretCenter(f);
          const cy = DOUBLE_INLAYS.has(f)
            ? [midY - STRING_GAP / 2, midY + STRING_GAP / 2]
            : [midY];
          return cy.map((y, i) => (
            <circle
              key={`${f}-${i}`}
              cx={cx}
              cy={y}
              r={4.5}
              className="fill-[#c9bfa8]/60"
              aria-hidden
            />
          ));
        })}

        {/* Strings — 1 on top */}
        {Array.from({ length: stringCount }, (_, i) => i + 1).map((s) => (
          <g key={s}>
            <line
              data-string={s}
              x1={0}
              x2={width - 8}
              y1={stringY(s)}
              y2={stringY(s)}
              className="stroke-[#b8b2a4]"
              strokeWidth={1 + (stringCount - s) * 0.25}
            />
            <text x={2} y={stringY(s) - 6} className="fill-faint font-mono text-[9px]">
              {s}
            </text>
          </g>
        ))}

        {/* Hand position band: frets hand_position .. hand_position + 3 */}
        <rect
          x={fretX(handStart - 1)}
          y={PAD_TOP - 8}
          width={(handEnd - handStart + 1) * FRET_WIDTH}
          height={height - PAD_TOP - PAD_BOTTOM + 16}
          className="fill-accent/10 pointer-events-none"
          aria-hidden
        />

        {/* Open-string marker in front of the nut */}
        {note.fret === 0 && (
          <g aria-hidden>
            <circle
              cx={OPEN_WIDTH / 2}
              cy={stringY(note.string)}
              r={11}
              className="fill-accent"
            />
            <text
              x={OPEN_WIDTH / 2}
              y={stringY(note.string) + 4}
              textAnchor="middle"
              className="fill-white font-mono text-[11px] font-bold"
            >
              0
            </text>
          </g>
        )}

        {/* Barre brackets of the current event. */}
        {barres.map((barre) => {
          const top = stringY(Math.min(barre.from_string, barre.to_string));
          const bottom = stringY(Math.max(barre.from_string, barre.to_string));
          return (
            <rect
              key={`barre-${barre.finger}-${barre.fret}`}
              x={fretCenter(barre.fret) - 6}
              y={top - 4}
              width={12}
              height={bottom - top + 8}
              rx={5}
              className="fill-accent/25 stroke-accent/60 pointer-events-none"
              aria-hidden
            />
          );
        })}

        {/* The other notes of the current chord: filled but quiet markers,
            so the whole shape stays readable while only the selected note
            shows its alternatives. Open strings sit in front of the nut. */}
        {chordNotes
          .filter((n) => n.id !== note.id)
          .map((chordNote) => (
            <g
              key={chordNote.id}
              data-chord-note={chordNote.id}
              aria-label={t("guitar_note_aria", {
                note: pitchName(chordNote.pitch),
                s: chordNote.string,
                f: chordNote.fret,
              })}
            >
              <circle
                cx={
                  chordNote.fret === 0
                    ? OPEN_WIDTH / 2
                    : fretCenter(chordNote.fret)
                }
                cy={stringY(chordNote.string)}
                r={9}
                className="fill-accent/45"
              />
              <text
                x={
                  chordNote.fret === 0
                    ? OPEN_WIDTH / 2
                    : fretCenter(chordNote.fret)
                }
                y={stringY(chordNote.string) + 3.5}
                textAnchor="middle"
                className="pointer-events-none fill-white font-mono text-[10px] font-semibold"
              >
                {chordNote.finger ?? "?"}
              </text>
              {chordNote.locked && (
                <circle
                  cx={
                    chordNote.fret === 0
                      ? OPEN_WIDTH / 2
                      : fretCenter(chordNote.fret)
                  }
                  cy={stringY(chordNote.string)}
                  r={13}
                  fill="none"
                  strokeDasharray="3 2"
                  className="stroke-[#e0b25a] stroke-[1.5px]"
                />
              )}
            </g>
          ))}

        {/* Alternative legal positions — focusable lock targets */}
        {alternatives.map((p) => (
          <circle
            key={`${p.string}-${p.fret}`}
            cx={p.fret === 0 ? OPEN_WIDTH / 2 : fretCenter(p.fret)}
            cy={stringY(p.string)}
            r={11}
            role="button"
            tabIndex={disabled ? -1 : 0}
            aria-label={describe(p)}
            className="cursor-pointer fill-transparent stroke-[#e0b25a] stroke-[2px] hover:fill-[#e0b25a]/25 focus-visible:outline-2 focus-visible:outline-accent"
            onClick={() => !disabled && onSelect(note.id, p.string, p.fret)}
            onKeyDown={(e) => !disabled && activate(e, p.string, p.fret)}
          >
            <title>{tooltip(p)}</title>
          </circle>
        ))}

        {/* Current position of the selected note */}
        <g role="button" tabIndex={-1} aria-pressed="true" aria-label={describe(note)}>
          <title>{tooltip(note)}</title>
          <circle
            cx={note.fret === 0 ? OPEN_WIDTH / 2 : fretCenter(note.fret)}
            cy={stringY(note.string)}
            r={13}
            className="fill-accent stroke-white stroke-[2px]"
          />
          {note.locked && (
            <circle
              cx={note.fret === 0 ? OPEN_WIDTH / 2 : fretCenter(note.fret)}
              cy={stringY(note.string)}
              r={17}
              fill="none"
              strokeDasharray="4 3"
              className="stroke-[#e0b25a] stroke-[2px]"
            />
          )}
          <text
            x={note.fret === 0 ? OPEN_WIDTH / 2 : fretCenter(note.fret)}
            y={stringY(note.string) + 4}
            textAnchor="middle"
            className="pointer-events-none fill-white font-mono text-[12px] font-bold"
          >
            {note.finger}
          </text>
        </g>
      </svg>
    </div>
  );
}
