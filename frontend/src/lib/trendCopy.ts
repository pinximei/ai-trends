/** 已知趋势：内部 key → 展示名 */
const KNOWN: Record<string, string> = {
  "workflow-automation-agent": "工作流自动化智能体",
  "customer-support-agent": "客服与售后智能体",
  "multimodal-content-agent": "多模态内容智能体",
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
  mcp: "模型上下文协议",
  skills: "技能",
  data: "数据",
  security: "安全",
  rag: "检索增强",
  voice: "语音",
  video: "视频",
};

const LIFECYCLE: Record<string, string> = {
  growth: "增长期",
  emerging: "新兴期",
  declining: "衰退期",
  mature: "成熟期",
};

/** 趋势展示：主标题 + 原始系统标识（便于对照） */
export function getTrendDisplay(trendKey: string): { title: string; code: string } {
  const code = trendKey.trim();
  if (!code) return { title: "—", code: "" };

  const known = KNOWN[code];
  if (known) {
    return { title: known, code };
  }

  const parts = code.split("-").filter(Boolean);
  const title = parts.map((p) => TOKENS_ZH[p.toLowerCase()] ?? p).join(" · ");
  return { title: title || code, code };
}

export function getLifecycleLabel(stage: string): string {
  const s = (stage || "").toLowerCase().trim();
  return LIFECYCLE[s] ?? stage || "—";
}

/** 置信度：0–1 → 百分比文案 */
export function formatConfidence(confidence: number): string {
  const pct = Math.round(Math.min(1, Math.max(0, confidence)) * 100);
  return `${pct}%`;
}
