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
    <div className="mx-auto max-w-7xl px-4 py-6 text-slate-100 sm:px-6 sm:py-8">
      <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4 shadow-[inset_0_0_32px_rgba(0,0,0,0.2)] sm:px-6 sm:py-5">
        <h1 className="text-lg font-semibold tracking-tight text-white sm:text-xl">{t("navDownloads")}</h1>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-slate-500">{t("downloadsPlatform")}</span>
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
              className={`rounded-xl px-3 py-1.5 text-sm font-medium ${
                platform === tab.key
                  ? "bg-gradient-to-r from-emerald-500/35 to-cyan-500/25 text-white ring-1 ring-emerald-400/45"
                  : "bg-white/5 text-slate-300 hover:text-white"
              }`}
            >
              {t(tab.labelKey)}
            </button>
          ))}
        </div>

        <div className="mt-3 border-t border-white/10 pt-4">
          <div className="text-xs uppercase tracking-wider text-slate-500">{t("downloadsAppType")}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setCategorySlug(null)}
              className={`rounded-xl px-3 py-1.5 text-sm font-medium ${
                categorySlug == null
                  ? "bg-fuchsia-500/25 text-white ring-1 ring-fuchsia-400/40"
                  : "bg-white/5 text-slate-300 hover:text-white"
              }`}
            >
              {t("downloadsCategoryAll")}
            </button>
            {categories.map((c) => (
              <button
                key={c.slug}
                type="button"
                onClick={() => setCategorySlug(c.slug)}
                className={`rounded-xl px-3 py-1.5 text-sm font-medium ${
                  categorySlug === c.slug
                    ? "bg-fuchsia-500/25 text-white ring-1 ring-fuchsia-400/40"
                    : "bg-white/5 text-slate-300 hover:text-white"
                }`}
              >
                {c.label}
                <span className="ml-1 font-mono text-[10px] text-slate-500">({c.count})</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {err ? <p className="mt-6 text-sm text-red-400">{err}</p> : null}
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
                className="flex flex-col rounded-2xl border border-white/10 bg-white/[0.04] p-5 shadow-[inset_0_0_36px_rgba(0,0,0,0.18)]"
              >
                <div className="flex items-start gap-3">
                  {row.icon_url ? (
                    <img src={row.icon_url} alt="" className="h-14 w-14 shrink-0 rounded-2xl object-cover ring-1 ring-white/10" />
                  ) : (
                    <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-slate-900/80 ring-1 ring-white/10">
                      <Smartphone className="h-7 w-7 text-slate-400" />
                    </span>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-md px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide ring-1 ${
                          row.platform === "ios"
                            ? "bg-sky-500/15 text-sky-200 ring-sky-500/30"
                            : "bg-lime-500/15 text-lime-100 ring-lime-500/30"
                        }`}
                      >
                        {row.platform}
                      </span>
                      {row.category_label ? (
                        <span className="rounded-md bg-fuchsia-500/15 px-2 py-0.5 text-[10px] text-fuchsia-100 ring-1 ring-fuchsia-500/25">
                          {row.category_label}
                        </span>
                      ) : null}
                    </div>
                    <h2 className="mt-2 text-base font-semibold text-white">{row.title}</h2>
                    {row.summary ? <p className="mt-1 text-sm text-slate-400">{row.summary}</p> : null}
                  </div>
                </div>
                {row.download_mode === "direct" && row.download_url ? (
                  <a
                    href={row.download_url}
                    download
                    className="mt-4 inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-500/20 py-2.5 text-sm font-semibold text-emerald-100 ring-1 ring-emerald-400/35 transition hover:bg-emerald-500/30"
                  >
                    <Download className="h-4 w-4" />
                    {t("downloadsCtaDirect")}
                  </a>
                ) : row.download_mode === "external" && row.download_url ? (
                  <a
                    href={row.download_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-4 inline-flex items-center justify-center gap-2 rounded-xl bg-white/10 py-2.5 text-sm font-semibold text-slate-100 ring-1 ring-white/20 transition hover:bg-white/15"
                  >
                    <Download className="h-4 w-4" />
                    {t("downloadsCtaExternal")}
                  </a>
                ) : (
                  <span className="mt-4 block rounded-xl bg-slate-800/60 py-2.5 text-center text-sm text-slate-500 ring-1 ring-white/10">
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
