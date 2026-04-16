import type { Lang } from "@/i18n";

/** 已知趋势：内部 key → 展示名 */
const KNOWN: Record<string, { zh: string; en: string }> = {
  "workflow-automation-agent": { zh: "工作流自动化 Agent", en: "Workflow automation agents" },
  "customer-support-agent": { zh: "客服与售后 Agent", en: "Customer support agents" },
  "multimodal-content-agent": { zh: "多模态内容 Agent", en: "Multimodal content agents" },
};

/** 片段词义（用于未知 key 的拼接） */
const TOKENS_ZH: Record<string, string> = {
  workflow: "工作流",
  automation: "自动化",
  customer: "客户",
  support: "支持",
  multimodal: "多模态",
  content: "内容",
  coding: "编程",
  agent: "智能体",
  mcp: "MCP",
  skills: "技能",
  data: "数据",
  security: "安全",
  rag: "检索增强",
  voice: "语音",
  video: "视频",
};

const TOKENS_EN: Record<string, string> = {
  workflow: "Workflow",
  automation: "Automation",
  customer: "Customer",
  support: "Support",
  multimodal: "Multimodal",
  content: "Content",
  coding: "Coding",
  agent: "Agents",
  mcp: "MCP",
  skills: "Skills",
  data: "Data",
  security: "Security",
  rag: "RAG",
  voice: "Voice",
  video: "Video",
};

const LIFECYCLE: Record<string, { zh: string; en: string }> = {
  growth: { zh: "增长期", en: "Growth" },
  emerging: { zh: "新兴期", en: "Emerging" },
  declining: { zh: "衰退期", en: "Declining" },
  mature: { zh: "成熟期", en: "Mature" },
};

/** 趋势展示：主标题（本地化）+ 原始系统标识（便于对照） */
export function getTrendDisplay(trendKey: string, lang: Lang): { title: string; code: string } {
  const code = trendKey.trim();
  if (!code) return { title: "—", code: "" };

  const known = KNOWN[code];
  if (known) {
    return { title: lang === "zh" ? known.zh : known.en, code };
  }

  const parts = code.split("-").filter(Boolean);
  if (lang === "zh") {
    const title = parts.map((p) => TOKENS_ZH[p.toLowerCase()] ?? p).join(" · ");
    return { title: title || code, code };
  }
  const title = parts
    .map((p) => {
      const low = p.toLowerCase();
      if (TOKENS_EN[low]) return TOKENS_EN[low];
      return p.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    })
    .join(" · ");
  return { title: title || code, code };
}

export function getLifecycleLabel(stage: string, lang: Lang): string {
  const s = (stage || "").toLowerCase().trim();
  const row = LIFECYCLE[s];
  if (row) return lang === "zh" ? row.zh : row.en;
  return stage || "—";
}

/** 置信度：0–1 → 百分比文案 */
export function formatConfidence(confidence: number, lang: Lang): string {
  const pct = Math.round(Math.min(1, Math.max(0, confidence)) * 100);
  return lang === "zh" ? `${pct}%` : `${pct}%`;
}
