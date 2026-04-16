import { useEffect, useState } from "react";
import { apiGet } from "@/api";
import { useI18n } from "@/i18n";
import { AlertTriangle, CheckCircle2, Scale, Sigma } from "lucide-react";

export function MethodologyPage() {
  const { lang, t } = useI18n();
  const [summary, setSummary] = useState("");

  useEffect(() => {
    apiGet<{ summary: string }>("/api/v1/meta/methodology", lang).then((d) => setSummary(d.summary));
  }, [lang]);

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <h1 className="text-gradient text-3xl font-bold">{t("methodology")}</h1>
          <p className="mt-3 text-slate-300">
            {lang === "zh"
              ? "这不是纯装饰页面，而是帮助你判断“结论可不可用”的规则层。"
              : "This page is the rule layer that tells you when conclusions are usable."}
          </p>
        </div>
        <div className="rounded-2xl border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-100">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="h-4 w-4" />
            {lang === "zh" ? "使用边界" : "Usage boundary"}
          </div>
          <p className="mt-2 text-amber-50/90">
            {lang === "zh" ? "趋势用于提出假设，不直接替代采购或合规决策。" : "Use trends for hypotheses, not final procurement/compliance decisions."}
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {[
          {
            icon: Sigma,
            title: lang === "zh" ? "评分汇总" : "Score aggregation",
            desc: lang === "zh" ? "多源信号加权后形成趋势分数。" : "Weighted multi-source signals form trend score.",
          },
          {
            icon: Scale,
            title: lang === "zh" ? "置信度评估" : "Confidence estimate",
            desc: lang === "zh" ? "依据样本量、来源多样性与稳定性。" : "Based on sample size, source diversity, and stability.",
          },
          {
            icon: CheckCircle2,
            title: lang === "zh" ? "可追溯" : "Traceable",
            desc: lang === "zh" ? "每条趋势可回溯到证据链与原始链接。" : "Each trend traces back to evidence path and raw links.",
          },
        ].map((card) => (
          <div key={card.title} className="rounded-2xl border border-white/10 bg-white/5 p-5">
            <card.icon className="h-5 w-5 text-cyan-300" />
            <h2 className="mt-3 text-base font-semibold text-white">{card.title}</h2>
            <p className="mt-2 text-sm text-slate-300">{card.desc}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="glass rounded-3xl p-8 leading-relaxed text-slate-300 lg:col-span-7">
          <div className="mb-4 text-xs uppercase tracking-wider text-slate-500">{lang === "zh" ? "核心说明" : "Core statement"}</div>
          {summary || (lang === "zh" ? "正在加载方法论说明…" : "Loading methodology…")}
        </div>
        <div className="rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900/80 to-black/70 p-6 lg:col-span-5">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-cyan-300">{lang === "zh" ? "处理流程" : "Pipeline"}</h3>
          <ol className="mt-4 space-y-3 text-sm text-slate-300">
            <li>1. {lang === "zh" ? "采集公开生态信号" : "Collect public ecosystem signals"}</li>
            <li>2. {lang === "zh" ? "清洗与去重，标准化标签" : "Clean, deduplicate, normalize tags"}</li>
            <li>3. {lang === "zh" ? "计算分数与置信度" : "Compute score and confidence"}</li>
            <li>4. {lang === "zh" ? "生成趋势并持续更新" : "Generate trends and update continuously"}</li>
          </ol>
        </div>
      </div>
    </div>
  );
}
