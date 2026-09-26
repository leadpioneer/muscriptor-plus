/** Fullscreen overlay shown (via the `body.drag` class) while a file is dragged. */
import { useI18n } from "../i18n";

export function DropOverlay() {
  const { t } = useI18n();
  return (
    <div
      className="drop-overlay pointer-events-none fixed inset-0 z-[200] flex items-center justify-center bg-[rgba(11,12,16,0.78)] opacity-0 backdrop-blur-sm transition-opacity duration-150 ease-fluid"
      aria-hidden="true"
    >
      <div className="flex flex-col items-center gap-3.5 rounded-card border-2 border-dashed border-accent bg-surface px-16 py-11 text-center shadow-overlay">
        <div className="wave-mark h-16 w-32 bg-accent" aria-hidden="true" />
        <p className="m-0 text-base text-muted">
          {t("drop_to_transcribe_intro")}{" "}
          <strong className="font-semibold text-content">{t("drop_to_transcribe_strong")}</strong>{" "}
          {t("drop_to_transcribe_tail")}
        </p>
      </div>
    </div>
  );
}
