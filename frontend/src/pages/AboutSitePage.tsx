import { useEffect, useState } from "react";
import { Github, Info } from "lucide-react";
import { publicApi } from "@/api/public";
import { useI18n } from "@/i18n";
import { SITE_GITHUB_REPO_URL } from "@/siteLinks";

const HUB_GRID =
  "grid gap-6 lg:grid-cols-[minmax(0,280px)_1fr] lg:items-start lg:gap-8 xl:grid-cols-[minmax(0,300px)_1fr]";

export function AboutSitePage() {
  const { t } = useI18n();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setErr("");
    setLoading(true);
    publicApi
      .page("about")
      .then((p) => {
        if (!cancelled) {
          setTitle(p.title);
          setBody(p.body_md);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setErr(String(e));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const leftStrip = (
    <div className="ui-card relative overflow-hidden p-4 sm:p-5">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-brand-50/45 via-transparent to-slate-50/35" />
      <div className="relative flex flex-row items-start gap-4">
        <div
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-brand-50 shadow-sm sm:h-14 sm:w-14"
          aria-hidden
        >
          <Info className="h-6 w-6 text-brand-600 sm:h-7 sm:w-7" strokeWidth={1.35} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-brand-600/90">{t("navAbout")}</p>
          <h1 className="mt-1 text-lg font-bold leading-snug tracking-tight text-slate-900 sm:text-xl">{t("navAbout")}</h1>
        </div>
      </div>
    </div>
  );

  const leftMeta = (
    <div className="ui-card space-y-4 p-4 text-xs leading-relaxed text-slate-500 sm:p-5">
      <p>{t("aboutPageIntro")}</p>
      <a
        href={SITE_GITHUB_REPO_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition-colors hover:border-violet-200 hover:bg-violet-50 hover:text-violet-800"
      >
        <Github className="h-4 w-4 shrink-0" strokeWidth={2} aria-hidden />
        {t("aboutGithubCta")}
      </a>
    </div>
  );

  const leftRail = (
    <div className="min-w-0 space-y-5 lg:sticky lg:top-24 lg:max-h-[calc(100vh-5.5rem)] lg:overflow-y-auto lg:overscroll-y-contain lg:self-start">
      {leftStrip}
      {leftMeta}
    </div>
  );

  return (
    <div className="w-full px-2 sm:px-4">
      <div className={HUB_GRID}>
        <aside className="min-w-0">{leftRail}</aside>
        <div className="min-w-0 space-y-4">
          {err ? <p className="mt-1 text-sm font-medium text-rose-600 sm:mt-2">{err}</p> : null}
          {loading ? <p className="mt-2 text-sm text-slate-500 sm:mt-3">{t("aboutPageLoading")}</p> : null}

          {!loading && !err && (title || body) ? (
            <div className="ui-card p-5 sm:p-6 lg:p-8">
              {title ? (
                <h2 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">{title}</h2>
              ) : null}
              <div
                className={`max-w-none whitespace-pre-wrap text-sm leading-relaxed text-slate-600 [&_a]:font-medium [&_a]:text-brand-600 hover:[&_a]:underline ${title ? "mt-5" : ""}`}
              >
                {body}
              </div>
            </div>
          ) : null}

          {!loading && !err && !title && !body ? (
            <p className="mt-4 text-center text-sm text-slate-500">{t("homeEmpty")}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
