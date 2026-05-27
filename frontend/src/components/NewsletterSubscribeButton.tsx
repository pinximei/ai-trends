import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Mail, X } from "lucide-react";
import { useNewsletterSubscribe } from "@/hooks/useNewsletterSubscribe";
import { useI18n } from "@/i18n";

type Props = {
  className?: string;
};

export function NewsletterSubscribeButton({ className = "" }: Props) {
  const { t } = useI18n();
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const { email, setEmail, sent, submitting, subscribeErr, clearError, onSubscribe } = useNewsletterSubscribe();

  useEffect(() => {
    if (!open) return;
    const onDoc = (ev: MouseEvent) => {
      if (!rootRef.current?.contains(ev.target as Node)) setOpen(false);
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const handleSubmit = async (e: FormEvent) => {
    await onSubscribe(e);
  };

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200/90 bg-white text-slate-600 shadow-sm transition-colors hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700 data-[open=true]:border-violet-300 data-[open=true]:bg-violet-50 data-[open=true]:text-violet-700"
        title={t("newsletterHeaderBtn")}
        aria-label={t("newsletterHeaderBtn")}
        aria-expanded={open}
        aria-controls={panelId}
        data-open={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Mail className="h-4 w-4" strokeWidth={2} aria-hidden />
      </button>

      {open ? (
        <div
          id={panelId}
          role="dialog"
          aria-labelledby={`${panelId}-title`}
          className="absolute right-0 top-[calc(100%+0.5rem)] z-[60] w-[min(20rem,calc(100vw-2rem))] overflow-hidden rounded-xl border border-slate-200/90 bg-white p-4 shadow-xl shadow-slate-900/10 ring-1 ring-slate-900/5"
        >
          <div className="mb-3 flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p id={`${panelId}-title`} className="text-sm font-bold text-slate-900">
                {t("newsletterPopoverTitle")}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-slate-500">{t("newsletterPopoverDesc")}</p>
            </div>
            <button
              type="button"
              className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label={t("newsletterClose")}
              onClick={() => setOpen(false)}
            >
              <X className="h-4 w-4" strokeWidth={2} aria-hidden />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-2">
            <input
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (subscribeErr) clearError();
              }}
              placeholder={t("newsletterPlaceholder")}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-violet-400 focus:ring-2 focus:ring-violet-500/20"
              autoComplete="email"
              autoFocus
            />
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-gradient-to-r from-violet-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:from-violet-700 hover:to-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? t("newsletterSending") : sent ? t("newsletterThanks") : t("newsletterSubscribe")}
            </button>
          </form>

          {subscribeErr ? (
            <p className="mt-2 text-xs font-medium text-rose-600" role="alert">
              {subscribeErr}
            </p>
          ) : null}
          <p className="mt-2 text-[10px] leading-snug text-slate-400">{t("newsletterHint")}</p>
        </div>
      ) : null}
    </div>
  );
}
