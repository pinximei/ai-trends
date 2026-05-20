import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

/** 前台固定为中文 */
export type Lang = "zh";

export const UI_LANG: Lang = "zh";

const STRINGS: Record<string, string> = {
  brand: "AI 资讯站",
  tagline: "发现 AI 的无限可能",
  navHome: "首页",
  navApps: "AI 工具",
  navNews: "AI 资讯",
  navDownloads: "软件下载",
  navAbout: "关于我们",
  aboutPageIntro: "以下为管理后台维护的正文，含网站介绍与免责说明等。",
  aboutPageLoading: "加载页面…",
  headerSearchPlaceholder: "搜索 AI 资讯、工具…",
  sidebarNavTitle: "导航",

  /** 首页（设计稿 1.png） */
  homeMainHeroTitle: "洞察 AI 前沿动态 掌握智能未来趋势",
  homeMainHeroDesc:
    "聚合全球模型发布、产品迭代与产业信号，用结构化信息流帮你节省筛选时间，专注真正重要的变化。",
  homeMainHeroCta1: "探索最新资讯",
  homeMainHeroCta2: "发现 AI 工具",
  homeTodayFocus: "今日焦点",
  homeImportantTag: "重要更新",
  homePopularCategories: "热门分类",
  homePopularTools: "热门工具",
  homeAiTrend: "AI 趋势",
  homeTrendChartTitle: "近 14 日入库活跃度",
  homeTrendDataNote: "基于已发布文章统计（非演示数据）",
  homeStatActiveTools: "活跃工具",
  homeStatNoCompare: "暂无环比",
  homeStatNewArticles: "新增资讯",
  homeStatGrowth: "周环比",
  homeSubscribeBarTitle: "订阅每周精选，第一时间获取 AI 前沿简报与工具清单",
  homeSubscribeBarBtn: "订阅",
  homePopularCat1Title: "AI 前沿",
  homePopularCat1Sub: "模型与论文",
  homePopularCat2Title: "工具推荐",
  homePopularCat2Sub: "效率与创作",
  homePopularCat5Title: "软件下载",
  homePopularCat5Sub: "安装包与版本",

  homeViewAll: "查看全部",
  homeLoading: "加载首页…",
  homeEmpty: "暂无内容，请稍后重试或检查后端数据。",

  detailSidebarRelatedTitle: "同类推荐",
  detailSidebarSearchPlaceholder: "搜索推荐标题…",
  detailSidebarNoMatch: "无匹配项，请修改关键词。",
  detailSidebarFeedEmpty: "暂无同类推荐",
  detailTocTitle: "正文目录",
  detailTocEmpty: "暂无小节标题",
  detailBackFeed: "返回列表",
  detailHighlights: "核心要点",
  detailOverview: "总览",
  detailAppMeta: "应用信息",
  detailFeaturedTag: "资讯",

  source: "来源",

  footer: "© AI 资讯站 · 学习参考与信息聚合演示",
  footerAboutFull: "完整说明",
  footerPrivacy: "隐私政策",
  footerTerms: "使用条款",
  footerContact: "联系我们",
  footerIcpNote: "备案及主体信息请以实际上线版本为准",

  newsletterCta: "把握 AI 浪潮，订阅精选更新",
  newsletterPlaceholder: "请输入邮箱",
  newsletterSubscribe: "订阅",
  newsletterThanks: "谢谢！",
  newsletterHint: "邮箱仅用于订阅通讯，可随时退订；提交即表示同意我们按隐私说明处理。",
  newsletterSending: "提交中…",
  newsletterErrorNetwork: "网络异常，请稍后重试。",

  sidebarChartApps: "本栏 · AI 应用",
  sidebarChartNews: "本栏 · AI 资讯",
  sidebarStatNew: "本页",
  sidebarStatCategories: "类别",
  sidebarStatVolume: "合计",
  sidebarCategoryTitle: "类目分布",
  sidebarCategoryEmpty: "暂无类别统计",

  resourcesByDate: "按发布日",
  resourcesByHeat: "按热度",
  resourcesHeatTopHint: "当前时间范围与筛选下，按统一热度排序，至多 100 条（已去重）；每次加载 20 条，滑到底自动继续。",
  resourcesHeatLoadingMore: "正在加载更多…",
  resourcesDisplayMode: "列表方式",
  resourcesListByDate: "按日期分页",
  resourcesListByHeat: "按热度 Top100",
  resourcesSearchLabel: "搜索",
  resourcesSearchPlaceholder: "标题或摘要关键词…",
  resourcesSearchClear: "清除",
  resourcesTimeFilter: "发布时间",
  resourcesDays2: "近两日",
  resourcesTimeAll: "不限",
  resourcesDays7: "近 7 天",
  resourcesDays30: "近 30 天",
  resourcesDays90: "近 90 天",
  resourcesCategoryFilter: "类别",
  resourcesCategoryAll: "全部分类",
  resourcesSourceFilter: "数据源",
  resourcesSourceAll: "全部数据源",
  resourcesLoading: "加载资源…",
  resourcesEmptyTopic: "当前筛选下暂无文章。",
  resourcesEmptySearch: "没有匹配该关键词的文章，可换个词或清空搜索。",
  resourcesFeedNews: "最新 AI 资讯",
  resourcesFeedApps: "最新 AI 应用",
  resourcesFeedDayHint:
    "按世界时日历日分页：每页连续 3 天内的全部文章（列表已去重）。第 1 页为当前筛选下最新的 3 个有内容的日期。可用上一页、下一页或输入页码跳转。",
  resourcesPagePrev: "上一页",
  resourcesPageNext: "下一页",
  resourcesPageGo: "跳转",
  resourcesPageJumpPlaceholder: "页码",
  resourcesPageSummary: "第 {page} / {total} 页",
  resourcesDaysTruncated: "日期列表可能不完整（已扫描文章达到上限）。请缩小时间范围或增加筛选条件。",
  feedCardDescription: "描述",
  feedCardHighlights: "数据支撑",
  feedCardPoints: "数据支撑",
  detailDataSupport: "数据支撑",
  detailSectionDescription: "描述",
  detailSectionData: "数据支撑",
  detailSectionDataPh: "上架数据",
  detailSectionDataHf: "Space 指标",
  detailSectionDataGh: "仓库指标",
  detailSectionDataWire: "报道依据",
  detailSectionDataApi: "能力与来源",
  detailProfileProduct: "产品上架",
  detailProfileRepo: "开源仓库",
  detailProfileSpace: "AI Space",
  detailProfileWire: "资讯快讯",
  detailProfileApi: "平台动态",
  detailProfileNews: "行业资讯",
  detailProfileApp: "AI 应用",
  detailNavDescription: "描述",
  detailNavData: "数据支撑",
  detailMetricStars: "Star",
  detailMetricHeat: "热度指数",
  listViewDetail: "查看",
  feedStarsToday: "+{n} 今日",

  resourceBackList: "返回列表",
  resourceLoadingDetail: "加载文章…",
  resourceTabsHeading: "分栏阅读",

  downloadsPageTitle: "软件下载",
  downloadsIntro:
    "按平台与应用类型筛选；本地上传包为直链下载，仅外链则跳转应用商店。可通过后台「应用分发」或维护脚本上传列表数据。",
  downloadsPlatform: "平台",
  downloadsPlatformAll: "全部平台",
  downloadsPlatformIos: "苹果",
  downloadsPlatformAndroid: "安卓",
  downloadsAppType: "应用类型",
  downloadsCategoryAll: "全部分类",
  downloadsLoading: "加载下载列表…",
  downloadsEmpty: "当前筛选下暂无条目。可在库表新增下载记录或启用演示种子数据。",
  downloadsCtaDirect: "下载安装包",
  downloadsCtaExternal: "前往商店",
  downloadsCtaNone: "暂无下载地址",
};

type Ctx = { lang: Lang; t: (key: string) => string };

const I18nCtx = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const t = useCallback((key: string) => STRINGS[key] ?? key, []);
  const value = useMemo(() => ({ lang: UI_LANG, t }), [t]);
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n() {
  const c = useContext(I18nCtx);
  if (!c) throw new Error("I18nProvider missing");
  return c;
}
