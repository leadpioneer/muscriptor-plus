import clsx from "clsx";
import { useI18n } from "../i18n";

/** The Kyutai + Mirelo logos, shared by the header and the footer. */
export function PartnerLogos({ className }: { className?: string }) {
  return (
    <div className={clsx("flex items-center gap-6", className)}>
      <a
        href="https://kyutai.org/"
        target="_blank"
        rel="noreferrer"
        className="opacity-90 transition-opacity hover:opacity-100"
      >
        <img src="/kyutai-logo.svg" alt="Kyutai" className="h-6 w-auto" />
      </a>
      <a
        href="https://www.mirelo.ai/"
        target="_blank"
        rel="noreferrer"
        className="opacity-90 transition-opacity hover:opacity-100"
      >
        <img src="/mirelo-logo.svg" alt="Mirelo" className="h-6 w-auto mb-1" />
      </a>
    </div>
  );
}

export function Footer() {
  const { t } = useI18n();
  return (
    <footer className="mx-auto mt-4 flex max-w-7xl flex-wrap items-center justify-between gap-6 border-t border-line px-7 py-10 max-[760px]:flex-col max-[760px]:items-start">
      <p className="max-w-md text-muted">
        {t("footer_about_pre")}{" "}
        <a
          href="https://kyutai.org/"
          target="_blank"
          rel="noreferrer"
          className="text-accent underline underline-offset-4 opacity-90 hover:opacity-100"
        >
          Kyutai
        </a>{" "}
        {t("footer_and")}{" "}
        <a
          href="https://www.mirelo.ai/"
          target="_blank"
          rel="noreferrer"
          className="text-accent underline underline-offset-4 opacity-90 hover:opacity-100"
        >
          Mirelo
        </a>
        .
      </p>
      <PartnerLogos />
    </footer>
  );
}
