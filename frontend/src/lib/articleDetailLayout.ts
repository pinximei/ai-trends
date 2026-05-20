import type { ArticleDetail } from "@/api/public";

export type DetailProfileId =
  | "product_launch"
  | "ai_space"
  | "open_source"
  | "news_wire"
  | "platform_api"
  | "news_article"
  | "app_product";

export type DetailHeroVariant = "product" | "repo" | "news" | "wire" | "platform";

export type DetailSectionKind = "description" | "data";

export type DetailLayoutConfig = {
  profile: DetailProfileId;
  heroVariant: DetailHeroVariant;
  descriptionTitleKey: keyof DetailLayoutI18nKeys;
  dataTitleKey: keyof DetailLayoutI18nKeys;
  showMetrics: boolean;
  metricsMode: "stars" | "heat" | "none";
  sectionOrder: DetailSectionKind[];
  heroAccent: string;
  dataPanelClass: string;
};

/** i18n keys used by layout (subset of full i18n dict) */
export type DetailLayoutI18nKeys = {
  detailSectionDescription: string;
  detailSectionData: string;
  detailSectionDataPh: string;
  detailSectionDataHf: string;
  detailSectionDataGh: string;
  detailSectionDataWire: string;
  detailSectionDataApi: string;
  detailProfileProduct: string;
  detailProfileRepo: string;
  detailProfileSpace: string;
  detailProfileWire: string;
  detailProfileApi: string;
  detailProfileNews: string;
  detailProfileApp: string;
  detailNavDescription: string;
  detailNavData: string;
  detailMetricStars: string;
  detailMetricHeat: string;
};

const PROFILES: Record<DetailProfileId, DetailLayoutConfig> = {
  product_launch: {
    profile: "product_launch",
    heroVariant: "product",
    descriptionTitleKey: "detailSectionDescription",
    dataTitleKey: "detailSectionDataPh",
    showMetrics: true,
    metricsMode: "heat",
    sectionOrder: ["description", "data"],
    heroAccent: "from-orange-500/90 via-rose-500/85 to-brand-600/90",
    dataPanelClass: "border-orange-100/80 bg-gradient-to-b from-orange-50/40 to-white",
  },
  ai_space: {
    profile: "ai_space",
    heroVariant: "product",
    descriptionTitleKey: "detailSectionDescription",
    dataTitleKey: "detailSectionDataHf",
    showMetrics: true,
    metricsMode: "heat",
    sectionOrder: ["description", "data"],
    heroAccent: "from-amber-400/90 via-yellow-500/85 to-violet-600/90",
    dataPanelClass: "border-amber-100/80 bg-gradient-to-b from-amber-50/35 to-white",
  },
  open_source: {
    profile: "open_source",
    heroVariant: "repo",
    descriptionTitleKey: "detailSectionDescription",
    dataTitleKey: "detailSectionDataGh",
    showMetrics: true,
    metricsMode: "stars",
    sectionOrder: ["description", "data"],
    heroAccent: "from-slate-700/95 via-slate-800/90 to-slate-900/95",
    dataPanelClass: "border-slate-200 bg-slate-50/50",
  },
  news_wire: {
    profile: "news_wire",
    heroVariant: "wire",
    descriptionTitleKey: "detailSectionDescription",
    dataTitleKey: "detailSectionDataWire",
    showMetrics: false,
    metricsMode: "none",
    sectionOrder: ["description", "data"],
    heroAccent: "",
    dataPanelClass: "border-brand-100/80 bg-brand-50/25",
  },
  platform_api: {
    profile: "platform_api",
    heroVariant: "platform",
    descriptionTitleKey: "detailSectionDescription",
    dataTitleKey: "detailSectionDataApi",
    showMetrics: false,
    metricsMode: "heat",
    sectionOrder: ["description", "data"],
    heroAccent: "",
    dataPanelClass: "border-violet-100/80 bg-violet-50/20",
  },
  news_article: {
    profile: "news_article",
    heroVariant: "news",
    descriptionTitleKey: "detailSectionDescription",
    dataTitleKey: "detailSectionData",
    showMetrics: false,
    metricsMode: "none",
    sectionOrder: ["description", "data"],
    heroAccent: "",
    dataPanelClass: "border-slate-100 bg-slate-50/30",
  },
  app_product: {
    profile: "app_product",
    heroVariant: "product",
    descriptionTitleKey: "detailSectionDescription",
    dataTitleKey: "detailSectionData",
    showMetrics: true,
    metricsMode: "heat",
    sectionOrder: ["description", "data"],
    heroAccent: "from-brand-500/90 via-brand-600/88 to-indigo-600/90",
    dataPanelClass: "border-brand-100/80 bg-brand-50/25",
  },
};

const PROFILE_BY_SOURCE: Record<string, DetailProfileId> = {
  product_hunt: "product_launch",
  huggingface_spaces: "ai_space",
  github: "open_source",
  newsapi: "news_wire",
  finnhub: "news_wire",
  youtube_data: "news_wire",
  mapbox: "news_wire",
  openai: "platform_api",
  google_gemini: "platform_api",
  mcp_skills: "platform_api",
};

export function resolveDetailProfile(article: Pick<ArticleDetail, "detail_profile" | "admin_source_key" | "feed_kind">): DetailProfileId {
  const fromApi = (article.detail_profile || "").trim() as DetailProfileId;
  if (fromApi && fromApi in PROFILES) return fromApi;
  const key = (article.admin_source_key || "").trim().toLowerCase();
  if (key && PROFILE_BY_SOURCE[key]) return PROFILE_BY_SOURCE[key];
  return article.feed_kind === "apps" ? "app_product" : "news_article";
}

export function getDetailLayout(article: Pick<ArticleDetail, "detail_profile" | "admin_source_key" | "feed_kind">): DetailLayoutConfig {
  return PROFILES[resolveDetailProfile(article)];
}

export function profileBadgeI18nKey(profile: DetailProfileId): keyof DetailLayoutI18nKeys {
  const map: Record<DetailProfileId, keyof DetailLayoutI18nKeys> = {
    product_launch: "detailProfileProduct",
    ai_space: "detailProfileSpace",
    open_source: "detailProfileRepo",
    news_wire: "detailProfileWire",
    platform_api: "detailProfileApi",
    news_article: "detailProfileNews",
    app_product: "detailProfileApp",
  };
  return map[profile];
}

export function sectionDomId(kind: DetailSectionKind): string {
  return kind === "description" ? "detail-section-desc" : "detail-section-data";
}
