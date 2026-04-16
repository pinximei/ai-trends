import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type Lang = "zh" | "en";

const STRINGS: Record<Lang, Record<string, string>> = {
  zh: {
    brand: "AISoul",
    tagline: "Agent 用途雷达 · 灵感与趋势",
    navHome: "首页",
    navTrends: "趋势",
    navInspirations: "灵感",
    navBriefing: "情报文章",
    navCategories: "分类",
    navMethodology: "方法论",
    navAdmin: "后台",
    navLegal: "合规",
    kpiActive: "活跃用例",
    kpiApps: "新增应用",
    kpiEmerging: "新兴趋势",
    kpiUpdated: "更新时间",
    topTrends: "热门趋势",
    score: "分数",
    confidence: "置信度",
    sample: "样本",
    lifecycle: "周期",
    lifecyclePhase: "生命周期阶段",
    trendCodeLabel: "系统标识",
    trendListHint: "主标题为中文说明；小字为接口中的英文标识，便于检索。",
    relatedTrend: "关联趋势",
    explore: "探索更多",
    ctaTrends: "查看实时趋势",
    ctaSignals: "看灵感信号",
    ctaBriefing: "读事实文章",
    trendsTracked: "追踪趋势",
    updatedAgo: "最近更新",
    sampling: "采集中",
    timeline: "时间线",
    nextStep: "建议下一步",
    evidence: "证据",
    source: "来源",
    link: "链接",
    trace: "追溯链",
    categories: "分类分布",
    methodology: "方法论说明",
    removalTitle: "删除 / 纠错申请",
    removalHint: "提交后请保存工单号与令牌以查询状态。",
    contact: "联系方式",
    targetId: "目标 signal ID",
    reason: "原因",
    submit: "提交",
    ticketCreated: "已创建工单",
    copyToken: "令牌（请妥善保存）",
    footer: "公共生态估计 · 非合规或采购结论",
  },
  en: {
    brand: "AISoul",
    tagline: "Agent radar · inspiration & trends",
    navHome: "Home",
    navTrends: "Trends",
    navInspirations: "Inspiration",
    navBriefing: "Briefing",
    navCategories: "Categories",
    navMethodology: "Methodology",
    navAdmin: "Admin",
    navLegal: "Legal",
    kpiActive: "Active use cases",
    kpiApps: "New apps",
    kpiEmerging: "Emerging",
    kpiUpdated: "Updated",
    topTrends: "Top trends",
    score: "Score",
    confidence: "Confidence",
    sample: "Sample",
    lifecycle: "Stage",
    lifecyclePhase: "Lifecycle",
    trendCodeLabel: "System id",
    trendListHint: "Title is localized; small text is the internal key for APIs.",
    relatedTrend: "Related trend",
    explore: "Explore",
    ctaTrends: "View live trends",
    ctaSignals: "View inspiration signals",
    ctaBriefing: "Read briefing",
    trendsTracked: "Trends tracked",
    updatedAgo: "Last update",
    sampling: "Collecting",
    timeline: "Timeline",
    nextStep: "Suggested next step",
    evidence: "Evidence",
    source: "Source",
    link: "URL",
    trace: "Trace",
    categories: "Categories",
    methodology: "Methodology",
    removalTitle: "Removal / correction",
    removalHint: "Save your ticket id and token to check status.",
    contact: "Contact",
    targetId: "Target signal id",
    reason: "Reason",
    submit: "Submit",
    ticketCreated: "Ticket created",
    copyToken: "Token (keep safe)",
    footer: "Ecosystem estimate · not legal or procurement advice",
  },
};

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (key: string) => string };

const I18nCtx = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(() => {
    const s = localStorage.getItem("lang");
    return s === "en" ? "en" : "zh";
  });
  const set = useCallback((l: Lang) => {
    setLang(l);
    localStorage.setItem("lang", l);
  }, []);
  const t = useCallback(
    (key: string) => STRINGS[lang][key] ?? STRINGS.zh[key] ?? key,
    [lang]
  );
  const value = useMemo(() => ({ lang, setLang: set, t }), [lang, set, t]);
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n() {
  const c = useContext(I18nCtx);
  if (!c) throw new Error("I18nProvider missing");
  return c;
}
