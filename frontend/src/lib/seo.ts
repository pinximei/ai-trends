import { useEffect } from "react";

/** 与 README / 邮件配置默认一致；构建时可设 VITE_PUBLIC_SITE_URL */
export const SITE_PUBLIC_URL = (
  import.meta.env.VITE_PUBLIC_SITE_URL || "https://www.ai-trends.news"
)
  .trim()
  .replace(/\/$/, "");

export const SITE_NAME = "AI 资讯站";
export const SITE_DEFAULT_DESCRIPTION =
  "聚合 Product Hunt、GitHub Trending、Hacker News 等源的 AI 应用与资讯，按变现价值评估与排序。";

export type PageSeo = {
  title?: string;
  description?: string;
  /** 站内路径，如 /news；用于 canonical 与 og:url */
  path?: string;
  image?: string | null;
  /** 默认 index,follow */
  robots?: string;
};

function upsertMeta(attr: "name" | "property", key: string, content: string) {
  if (!content) return;
  let el = document.head.querySelector(`meta[${attr}="${key}"]`) as HTMLMetaElement | null;
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel: string, href: string) {
  if (!href) return;
  let el = document.head.querySelector(`link[rel="${rel}"]`) as HTMLLinkElement | null;
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

export function applyPageSeo(seo: PageSeo) {
  const title = (seo.title || SITE_NAME).trim();
  const description = (seo.description || SITE_DEFAULT_DESCRIPTION).trim();
  const path = (seo.path || window.location.pathname || "/").split("?")[0] || "/";
  const canonical = `${SITE_PUBLIC_URL}${path.startsWith("/") ? path : `/${path}`}`;
  const image = (seo.image || "").trim();
  const robots = (seo.robots || "index,follow").trim();

  document.title = title;
  upsertMeta("name", "description", description);
  upsertMeta("name", "robots", robots);
  upsertLink("canonical", canonical);

  upsertMeta("property", "og:type", "website");
  upsertMeta("property", "og:site_name", SITE_NAME);
  upsertMeta("property", "og:title", title);
  upsertMeta("property", "og:description", description);
  upsertMeta("property", "og:url", canonical);
  upsertMeta("property", "og:locale", "zh_CN");
  if (image) upsertMeta("property", "og:image", image);

  upsertMeta("name", "twitter:card", image ? "summary_large_image" : "summary");
  upsertMeta("name", "twitter:title", title);
  upsertMeta("name", "twitter:description", description);
  if (image) upsertMeta("name", "twitter:image", image);
}

export function usePageSeo(seo: PageSeo) {
  useEffect(() => {
    applyPageSeo(seo);
  }, [seo.title, seo.description, seo.path, seo.image, seo.robots]);
}
