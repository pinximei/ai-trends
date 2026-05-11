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

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <div className="glass-light p-5 sm:p-6">
        <h1 className="text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">{t("navDownloads")}</h1>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <span className="w-full text-xs font-semibold uppercase tracking-wider text-slate-500 sm:w-auto sm:mr-1">
            {t("downloadsPlatform")}
          </span>
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

        <div className="mt-4 border-t border-slate-100 pt-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">{t("downloadsAppType")}</div>
          <div className="mt-2 flex flex-wrap gap-2">
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

        <p className="mt-4 text-[11px] leading-relaxed text-slate-500">{t("downloadsIntro")}</p>
      </div>

      {err ? <p className="mt-6 text-sm font-medium text-rose-600">{err}</p> : null}
      {loading ? <p className="mt-8 text-sm text-slate-500">{t("downloadsLoading")}</p> : null}

      {!loading ? (
        <>
          <p className="mt-6 text-xs text-slate-500">
            {platformLabel}
            {categorySlug ? ` · ${categories.find((c) => c.slug === categorySlug)?.label ?? categorySlug}` : ""}
          </p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((row) => (
              <div
                key={row.id}
                className="group relative flex flex-col overflow-hidden rounded-3xl border border-slate-200/90 bg-white p-5 shadow-card transition hover:-translate-y-0.5 hover:border-violet-200 hover:shadow-ui"
              >
                <div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-gradient-to-br from-violet-100 to-sky-100 opacity-70 blur-2xl transition group-hover:opacity-100" />
                <div className="relative flex items-start gap-3">
                  {row.icon_url ? (
                    <img src={row.icon_url} alt="" className="h-14 w-14 shrink-0 rounded-2xl object-cover ring-1 ring-slate-200" />
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
                        <span className="rounded-lg bg-violet-50 px-2 py-0.5 text-[10px] font-semibold text-violet-900 ring-1 ring-violet-100">
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
                    className="relative mt-4 inline-flex items-center justify-center gap-2 rounded-full bg-emerald-600 py-2.5 text-sm font-semibold text-white shadow-md transition hover:bg-emerald-700"
                  >
                    <Download className="h-4 w-4" />
                    {t("downloadsCtaDirect")}
                  </a>
                ) : row.download_mode === "external" && row.download_url ? (
                  <a
                    href={row.download_url}
                    target="_blank"
                    rel="noreferrer"
                    className="relative mt-4 inline-flex items-center justify-center gap-2 rounded-full border border-slate-200 bg-white py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:bg-slate-50"
                  >
                    <Download className="h-4 w-4" />
                    {t("downloadsCtaExternal")}
                  </a>
                ) : (
                  <span className="relative mt-4 block rounded-2xl border border-slate-200 bg-slate-50 py-2.5 text-center text-sm text-slate-500">
                    {t("downloadsCtaNone")}
                  </span>
                )}
              </div>
            ))}
          </div>
          {items.length === 0 ? <p className="mt-10 text-center text-sm text-slate-500">{t("downloadsEmpty")}</p> : null}
        </>
      ) : null}
    </div>
  );
}
