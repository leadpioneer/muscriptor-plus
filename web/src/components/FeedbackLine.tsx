import { useEffect, useState } from "react";
import clsx from "clsx";
import { useI18n } from "../i18n";

/**
 * "Feedback, question, bug?" line under the output bar. Held back for a few
 * seconds and then typed out left to right, so it catches the eye of someone
 * who has already settled into watching the progress bar.
 */
export function FeedbackLine({ className }: { className?: string }) {
  const { t } = useI18n();
  const segments: { text: string; href?: string }[] = [
    { text: t("feedback_intro") },
    { text: t("feedback_email"), href: "mailto:muscriptor@kyutai.org" },
    { text: t("feedback_or") },
    {
      text: t("feedback_issue"),
      href: "https://github.com/muscriptor/muscriptor/issues/new/choose",
    },
  ];
  const total = segments.reduce((n, s) => n + s.text.length, 0);
  const [shown, setShown] = useState(0);

  useEffect(() => {
    let id: ReturnType<typeof setInterval>;
    const start = setTimeout(() => {
      id = setInterval(() => {
        setShown((n) => {
          if (n >= total) {
            clearInterval(id);
            return n;
          }
          return n + 1;
        });
      }, 35);
    }, 3000);
    return () => {
      clearTimeout(start);
      clearInterval(id);
    };
  }, [total]);

  let cut = shown;
  return (
    <p className={clsx("text-xs text-muted", className)} aria-live="polite">
      {segments.map((seg, i) => {
        const text = seg.text.slice(0, Math.max(0, cut));
        cut -= seg.text.length;
        if (!text) return null;
        return seg.href ? (
          <a
            key={i}
            href={seg.href}
            target={seg.href.startsWith("http") ? "_blank" : undefined}
            rel="noreferrer"
            className="text-accent underline underline-offset-4 opacity-90 hover:opacity-100"
          >
            {text}
          </a>
        ) : (
          <span key={i}>{text}</span>
        );
      })}
    </p>
  );
}
