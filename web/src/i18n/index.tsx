import {
  createContext,
  useContext,
  useState,
  type ReactNode,
} from "react";
import { EN, FAQ_EN, type Dict } from "./en";
import { RU, FAQ_RU } from "./ru";

export type Lang = "en" | "ru";
export type FaqPair = { q: string; a: string };

const STORAGE_KEY = "lang";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "ru") return saved;
  } catch {
    /* storage unavailable */
  }
  return navigator.language?.toLowerCase().startsWith("ru") ? "ru" : "en";
}

const DICTS: Record<Lang, Dict> = { en: EN, ru: RU };
const FAQS: Record<Lang, FaqPair[]> = { en: FAQ_EN, ru: FAQ_RU };

type I18n = {
  lang: Lang;
  setLang: (lang: Lang) => void;
  /** Translate `key`, interpolating `{param}` placeholders from `params`. */
  t: (key: string, params?: Record<string, string | number>) => string;
  /** Localized instrument display name (falls back to the id with spaces). */
  instrumentLabel: (id: string) => string;
  /** The FAQ pairs for the active language. */
  faq: FaqPair[];
};

const I18nContext = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = (next: Lang) => {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable */
    }
    setLangState(next);
  };

  const t: I18n["t"] = (key, params) => {
    let s = DICTS[lang][key] ?? EN[key] ?? key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        s = s.replaceAll(`{${k}}`, String(v));
      }
    }
    return s;
  };

  const instrumentLabel: I18n["instrumentLabel"] = (id) =>
    DICTS[lang][`instr_${id}`] ?? EN[`instr_${id}`] ?? id.replace(/_/g, " ");

  return (
    <I18nContext.Provider value={{ lang, setLang, t, instrumentLabel, faq: FAQS[lang] }}>
      {children}
    </I18nContext.Provider>
  );
}

/** Access the active language, `t()`, instrument labels and the FAQ. */
export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}

/** EN | RU toggle, shown in the header on both screens. */
export function LanguageSwitcher({ className }: { className?: string }) {
  const { lang, setLang } = useI18n();
  return (
    <div
      role="group"
      aria-label="Language"
      className={className ?? "flex shrink-0 items-center gap-0.5 rounded-lg border border-line-strong bg-surface-2 p-0.5"}
    >
      {(["en", "ru"] as const).map((l) => (
        <button
          key={l}
          type="button"
          aria-pressed={lang === l}
          onClick={() => setLang(l)}
          className={
            "cursor-pointer rounded-md px-2.5 py-1 font-mono text-xs uppercase transition-colors duration-150 " +
            (lang === l
              ? "bg-accent text-white"
              : "text-muted hover:text-content")
          }
        >
          {l}
        </button>
      ))}
    </div>
  );
}