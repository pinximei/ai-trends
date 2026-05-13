import { useState, type FormEvent } from "react";
import { Bell, Mail } from "lucide-react";
import { useI18n } from "@/i18n";

export function NewsletterBar() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setSent(true);
    setEmail("");
    window.setTimeout(() => setSent(false), 3200);
  };

  return (
    <div className="pointer-events-none fixed bottom-6 left-1/2 z-[70] w-[min(100%,42rem)] -translate-x-1/2 px-4">
      <form
        onSubmit={onSubmit}
        className="pointer-events-auto flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-md backdrop-blur-xl sm:flex-nowrap sm:px-5"
      >
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand-600 ring-1 ring-brand-100">
            <Bell className="h-5 w-5" strokeWidth={2} />
          </span>
          <p className="min-w-0 text-sm font-medium leading-snug text-slate-800">{t("newsletterCta")}</p>
        </div>
        <div className="flex w-full min-w-0 flex-1 items-center gap-2 sm:w-auto sm:max-w-xs">
          <div className="relative min-w-0 flex-1">
            <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("newsletterPlaceholder")}
              className="w-full rounded-md border border-slate-200 bg-white py-2.5 pl-10 pr-3 text-sm text-slate-800 outline-none ring-brand-500/15 placeholder:text-slate-400 focus:border-brand-400 focus:ring-2"
              autoComplete="email"
            />
          </div>
          <button type="submit" className="btn-accent shrink-0 whitespace-nowrap px-4 py-2 text-xs sm:text-sm">
            {sent ? t("newsletterThanks") : t("newsletterSubscribe")}
          </button>
        </div>
      </form>
      <p className="pointer-events-auto mt-2 text-center text-[10px] text-slate-500">{t("newsletterHint")}</p>
    </div>
  );
}
