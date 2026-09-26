/**
 * FAQ below the welcome screen. Mostly for SEO: the questions are the phrasings
 * people actually search for, and native <details> keeps collapsed answers in
 * the DOM where crawlers still see them — that's where the value is.
 *
 * The FAQPage JSON-LD is a bonus, not the point: Google stopped showing FAQ
 * rich results for general sites in 2023 (government/health domains only), so
 * it buys nothing there. Other engines and AI crawlers still read it, and it's
 * generated from the same strings, so it costs ~8 lines and can't go stale.
 */

import { track } from "../analytics";
import { useI18n } from "../i18n";

/** `[label](href)` or `code`. */
const TOKEN = /\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`/g;

/** Answer text → React nodes, with the two inline forms above marked up. */
function renderAnswer(a: string) {
  const out = [];
  let last = 0;
  for (const m of a.matchAll(TOKEN)) {
    if (m.index > last) out.push(a.slice(last, m.index));
    out.push(
      m[1] ? (
        <a
          key={m.index}
          href={m[2]}
          target="_blank"
          rel="noreferrer"
          className="text-accent underline underline-offset-4"
        >
          {m[1]}
        </a>
      ) : (
        <code key={m.index} className="font-mono text-[0.9em] text-content">
          {m[3]}
        </code>
      ),
    );
    last = m.index + m[0].length;
  }
  out.push(a.slice(last));
  return out;
}

/** Same text with the markup stripped, for the JSON-LD. */
const plainText = (a: string) =>
  a.replace(TOKEN, (_m, label, _href, code) => label ?? code);

export function Faq() {
  const { t, faq } = useI18n();
  return (
    <section className="mx-auto max-w-3xl px-7 pb-16">
      <h2 className="mb-4 text-3xl font-bold leading-none text-white">
        {t("faq_title")}
      </h2>
      <div className="border-t border-line">
        {faq.map(({ q, a }) => (
          <details
            key={q}
            className="group border-b border-line"
            onToggle={(e) => {
              if (e.currentTarget.open) track("faq_open", { question: q });
            }}
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-4 text-base font-semibold text-content marker:content-none hover:text-accent">
              <h3 className="m-0 text-base font-semibold">{q}</h3>
              <span
                className="shrink-0 text-muted transition-transform group-open:rotate-90"
                aria-hidden="true"
              >
                ›
              </span>
            </summary>
            <p className="m-0 pb-4 pr-8 text-base leading-relaxed text-muted">
              {renderAnswer(a)}
            </p>
          </details>
        ))}
      </div>
      <script
        type="application/ld+json"
        // Static, locally-authored strings — no user input reaches this.
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            mainEntity: faq.map(({ q, a }) => ({
              "@type": "Question",
              name: q,
              acceptedAnswer: { "@type": "Answer", text: plainText(a) },
            })),
          }),
        }}
      />
    </section>
  );
}
