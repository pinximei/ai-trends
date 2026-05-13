import type { LucideIcon } from "lucide-react";
import { Download, Home, Info, LayoutGrid, Newspaper } from "lucide-react";

export type TopNavKey = "navHome" | "navApps" | "navNews" | "navDownloads" | "navAbout";

export type TopNavItem = {
  readonly to: string;
  readonly key: TopNavKey;
  readonly icon: LucideIcon;
};

/** 与顶栏 `Layout` 导航一致，供首页轨道等处复用 */
export const TOP_NAV_ITEMS: readonly TopNavItem[] = [
  { to: "/", key: "navHome", icon: Home },
  { to: "/apps", key: "navApps", icon: LayoutGrid },
  { to: "/news", key: "navNews", icon: Newspaper },
  { to: "/downloads", key: "navDownloads", icon: Download },
  { to: "/about", key: "navAbout", icon: Info },
];
