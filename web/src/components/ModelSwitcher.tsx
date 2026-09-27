import { useEffect, useState } from "react";
import { useI18n } from "../i18n";

/**
 * Model size picker in the header. Reads GET /model on mount and polls while a
 * swap is in flight; POST /model starts the load server-side (weights download
 * + first load take a while, so the control disables itself until it's ready).
 * The server answers 501 when it can't swap models (e.g. started from a local
 * weights file), in which case the picker quietly hides itself.
 */
export function ModelSwitcher() {
  const { t } = useI18n();
  const [available, setAvailable] = useState(true);
  const [size, setSize] = useState<string | null>(null);
  const [status, setStatus] = useState<
    "ready" | "loading" | "error" | "unloaded"
  >("ready");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch("/model");
        if (!r.ok) {
          if (!cancelled) setAvailable(false);
          return;
        }
        const data = (await r.json()) as {
          model: string;
          status: "ready" | "loading" | "error" | "unloaded";
          error: string | null;
        };
        if (cancelled) return;
        setAvailable(true);
        setSize(data.model);
        setStatus(data.status);
        setError(data.error);
      } catch {
        if (!cancelled) setAvailable(false);
      }
    };
    poll();
    // While loading, poll fast so the picker unlocks promptly; "unloaded"
    // (auto-unloaded while idle) reloads transparently on the next request,
    // but the label should catch a manual unload/load quickly too.
    const id = setInterval(
      poll,
      status === "loading" || status === "unloaded" ? 2000 : 15000,
    );
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [status]);

  async function change(next: string) {
    // "error" stays switchable: a failed load (e.g. HuggingFace access granted
    // afterwards) must not wedge the picker — the server refuses only while a
    // load is actually in flight.
    if (status === "loading") return;
    if (next === size && status === "ready") return;
    if (next === "unload" && status === "unloaded") return;
    try {
      const form = new FormData();
      form.append("size", next);
      const r = await fetch("/model", { method: "POST", body: form });
      if (!r.ok) {
        const text = await r.text();
        let detail = text;
        try {
          detail = JSON.parse(text).detail ?? text;
        } catch {
          /* raw body */
        }
        setError(detail);
        return;
      }
      setStatus(next === "unload" ? "unloaded" : "loading");
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!available || size === null) return null;

  return (
    <label className="flex shrink-0 items-center gap-2 rounded-lg border border-line-strong bg-surface-2 px-2.5 py-1 text-sm text-muted">
      <span>{t("model_label")}</span>
      <select
        className="cursor-pointer border-none bg-transparent text-content outline-none"
        value={size}
        disabled={status === "loading"}
        onChange={(e) => change(e.target.value)}
      >
        {["small", "medium", "large"].map((s) => (
          <option key={s} value={s} className="bg-surface text-content">
            {s}
          </option>
        ))}
      </select>
      {status === "loading" && (
        <span className="text-xs text-faint" role="status">
          {t("model_loading")}
        </span>
      )}
      {status === "unloaded" && (
        <>
          <span className="text-xs text-faint" role="status">
            {t("model_unloaded")}
          </span>
          <button
            type="button"
            className="shrink-0 cursor-pointer rounded-md border border-line-strong px-1.5 py-0.5 text-xs text-content outline-none transition-colors duration-150 hover:border-accent hover:text-accent"
            title={t("model_load_title")}
            onClick={() => change(size)}
          >
            {t("model_load")}
          </button>
        </>
      )}
      {status === "ready" && (
        <button
          type="button"
          className="shrink-0 cursor-pointer rounded-md border border-line-strong px-1.5 py-0.5 text-xs text-muted outline-none transition-colors duration-150 hover:border-accent hover:text-accent"
          title={t("model_unload_title")}
          onClick={() => change("unload")}
        >
          {t("model_unload")}
        </button>
      )}
      {status === "error" && (
        <>
          <span
            className="text-xs text-red"
            role="alert"
            title={error ?? ""}
          >
            {t("model_error")}
          </span>
          <button
            type="button"
            className="shrink-0 cursor-pointer rounded-md border border-line-strong px-1.5 py-0.5 text-xs text-content outline-none transition-colors duration-150 hover:border-accent hover:text-accent"
            title={error ?? ""}
            onClick={() => change(size)}
          >
            {t("model_retry")}
          </button>
        </>
      )}
    </label>
  );
}