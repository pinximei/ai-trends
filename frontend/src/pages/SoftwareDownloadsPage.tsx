import { useEffect, useMemo, useState } from "react";
import { Download, Smartphone } from "lucide-react";
import { publicApi } from "@/api/public";
import { useI18n } from "@/i18n";

type PlatformFilter = "all" | "ios" | "android";

type CatRow = { slug: string; label: string; count: number };

type DownRow = {
  id: number;
  title: string;
  summary: string;
  platform: string;
  category_slug: string;
  category_label: string;
  store_url: string;
  download_url: string;
  download_mode: "direct" | "external" | "none";
  icon_url: string | null;
  sort_order: number;
};

const HUB_GRID =
  "grid gap-6 lg:grid-cols-[minmax(0,280px)_1fr] lg:items-start lg:gap-8 xl:grid-cols-[minmax(0,300px)_1fr]";

export function SoftwareDownloadsPage() {
  const { t } = useI18n();
  const [platform, setPlatform] = useState<PlatformFilter>("all");
  const [categorySlug, setCategorySlug] = useState<string | null>(null);
  const [categories, setCategories] = useState<CatRow[]>([]);
  const [items, setItems] = useState<DownRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  const platformLabel = useMemo(() => {
    if (platform === "ios") return t("downloadsPlatformIos");
    if (platform === "android") return t("downloadsPlatformAndroid");
    return t("downloadsPlatformAll");
  }, [platform, t]);

  useEffect(() => {
    let cancelled = false;
    publicApi
      .softwareCategories()
      .then((rows) => {
        if (!cancelled) setCategories(rows ?? []);
      })
      .catch(() => {
        if (!cancelled) setCategories([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr("");
    publicApi
      .softwareDownloads({
        platform,
        category_slug: categorySlug ?? undefined,
        limit: 200,
      })
      .then((rows) => {
        if (!cancelled) {
          setItems(rows ?? []);
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
  }, [platform, categorySlug]);

  const leftStrip = (
    <div className="ui-card relative overflow-hidden p-4 sm:p-5">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-brand-50/45 via-transparent to-slate-50/35" />
      <div className="relative flex flex-row items-start gap-4">
        <div
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-brand-50 shadow-sm sm:h-14 sm:w-14"
          aria-hidden
        >
          <Download className="h-6 w-6 text-brand-600 sm:h-7 sm:w-7" strokeWidth={1.35} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-brand-600/90">{t("navDownloads")}</p>
          <h1 className="mt-1 text-lg font-bold leading-snug tracking-tight text-slate-900 sm:text-xl">{t("downloadsPageTitle")}</h1>
        </div>
      </div>
    </div>
  );

  const leftFilters = (
    <div className="min-w-0 space-y-5">
      <div className="ui-card p-4 sm:p-5">
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{t("downloadsPlatform")}</span>
        <div className="mt-3 flex flex-wrap gap-2">
          {(
            [
              { key: "all" as const, labelKey: "downloadsPlatformAll" },
              { key: "ios" as const, labelKey: "downloadsPlatformIos" },
              { key: "android" as const, labelKey: "downloadsPlatformAndroid" },
            ] as const
          ).map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setPlatform(tab.key)}
              className={`rounded-full px-3.5 py-2 text-sm font-medium transition ${
                platform === tab.key ? "pill-active shadow-md" : "pill-idle"
              }`}
            >
              {t(tab.labelKey)}
            </button>
          ))}
        </div>
      </div>

      <div className="ui-card p-4 sm:p-4">
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{t("downloadsAppType")}</span>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setCategorySlug(null)}
            className={`rounded-full px-3.5 py-2 text-sm font-medium transition ${
              categorySlug == null ? "pill-active shadow-md" : "pill-idle"
            }`}
          >
            {t("downloadsCategoryAll")}
          </button>
          {categories.map((c) => (
            <button
              key={c.slug}
              type="button"
              onClick={() => setCategorySlug(c.slug)}
              className={`rounded-full px-3.5 py-2 text-sm font-medium transition ${
                categorySlug === c.slug ? "pill-active shadow-md" : "pill-idle"
              }`}
            >
              {c.label}
              <span className="ml-1 font-mono text-[10px] text-slate-500">({c.count})</span>
            </button>
          ))}
        </div>
      </div>

      <div className="ui-card p-4 text-xs leading-relaxed text-slate-500">{t("downloadsIntro")}</div>
    </div>
  );

  const leftRail = (
    <div className="min-w-0 space-y-5 lg:sticky lg:top-24 lg:max-h-[calc(100vh-5.5rem)] lg:overflow-y-auto lg:overscroll-y-contain lg:self-start">
      {leftStrip}
      {leftFilters}
    </div>
  );

  return (
    <div className="w-full px-2 sm:px-4">
      <div className={HUB_GRID}>
        <aside className="min-w-0">{leftRail}</aside>
        <div className="min-w-0 space-y-4">
          {err ? <p className="mt-1 text-sm font-medium text-rose-600 sm:mt-2">{err}</p> : null}
          {loading ? <p className="mt-2 text-sm text-slate-500 sm:mt-3">{t("downloadsLoading")}</p> : null}

          {!loading ? (
            <>
              <p className="mt-1 text-xs text-slate-500 sm:mt-2">
                {platformLabel}
                {categorySlug ? ` · ${categories.find((c) => c.slug === categorySlug)?.label ?? categorySlug}` : ""}
              </p>
              <div className="grid gap-5 sm:grid-cols-2 sm:gap-6 lg:grid-cols-3 xl:grid-cols-4">
                {items.map((row) => (
                  <div
                    key={row.id}
                    className="ui-card group relative flex flex-col overflow-hidden transition hover:border-brand-300 hover:shadow-lg"
                  >
                    <div
                      className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-brand-500 opacity-0 transition-opacity group-hover:opacity-100"
                      aria-hidden
                    />
                    <div className="relative flex flex-1 flex-col p-5">
                      <div className="flex items-start gap-3">
                        {row.icon_url ? (
                          <img
                            src={row.icon_url}
                            alt=""
                            className="h-14 w-14 shrink-0 rounded-2xl object-cover ring-1 ring-slate-200"
                          />
                        ) : (
                          <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-slate-100 ring-1 ring-slate-200">
                            <Smartphone className="h-7 w-7 text-slate-400" />
                          </span>
                        )}
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-lg px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide ring-1 ${
                                row.platform === "ios"
                                  ? "bg-sky-50 text-sky-800 ring-sky-100"
                                  : "bg-lime-50 text-lime-800 ring-lime-100"
                              }`}
                            >
                              {row.platform}
                            </span>
                            {row.category_label ? (
                              <span className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-700">
                                {row.category_label}
                              </span>
                            ) : null}
                          </div>
                          <h2 className="mt-2 text-base font-bold text-slate-900">{row.title}</h2>
                          {row.summary ? <p className="mt-1 text-sm text-slate-600">{row.summary}</p> : null}
                        </div>
                      </div>
                      {row.download_mode === "direct" && row.download_url ? (
                        <a
                          href={row.download_url}
                          download
                          className="mt-4 inline-flex items-center justify-center gap-2 rounded-full bg-emerald-600 py-2.5 text-sm font-semibold text-white shadow-md transition hover:bg-emerald-700"
                        >
                          <Download className="h-4 w-4" />
                          {t("downloadsCtaDirect")}
                        </a>
                      ) : row.download_mode === "external" && row.download_url ? (
                        <a
                          href={row.download_url}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-4 inline-flex items-center justify-center gap-2 rounded-full border border-slate-200 bg-white py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:bg-slate-50"
                        >
                          <Download className="h-4 w-4" />
                          {t("downloadsCtaExternal")}
                        </a>
                      ) : (
                        <span className="mt-4 block rounded-2xl border border-slate-200 bg-slate-50 py-2.5 text-center text-sm text-slate-500">
                          {t("downloadsCtaNone")}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {items.length === 0 ? (
                <p className="mt-6 text-center text-sm text-slate-500 sm:mt-8">{t("downloadsEmpty")}</p>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
