import { motion } from "framer-motion";
import { GitBranch, LineChart, ShieldCheck } from "lucide-react";

/** 参考 Linear 三栏特性：大图块图标 + 短标题 + 一句说明 */
export function FeatureColumns({ lang }: { lang: "zh" | "en" }) {
  const cols = [
    {
      icon: LineChart,
      title: lang === "zh" ? "实时趋势雷达" : "Live trend radar",
      desc:
        lang === "zh"
          ? "分数、周期、样本量一屏对齐，像看盘一样读 Agent 动向。"
          : "Score, horizon, and sample size aligned—read agent motion like a dashboard.",
      grad: "from-cyan-500/40 to-blue-600/20",
    },
    {
      icon: GitBranch,
      title: lang === "zh" ? "证据链下钻" : "Evidence drill-down",
      desc:
        lang === "zh"
          ? "从趋势点到原始信号，可追溯、可复核，而不是一句结论。"
          : "From trend to raw signal—traceable, reviewable, not a one-liner.",
      grad: "from-fuchsia-500/40 to-violet-700/20",
    },
    {
      icon: ShieldCheck,
      title: lang === "zh" ? "合规与透明" : "Compliance aware",
      desc:
        lang === "zh"
          ? "删除与纠错入口直达，方法论与数据来源公开可查。"
          : "Removal & correction paths, methodology and sources disclosed.",
      grad: "from-amber-500/35 to-orange-600/20",
    },
  ];

  return (
    <div className="grid gap-6 md:grid-cols-3">
      {cols.map((c, i) => (
        <motion.article
          key={c.title}
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-40px" }}
          transition={{ delay: i * 0.1, duration: 0.5 }}
          className="group relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-b from-white/[0.06] to-transparent p-8 transition hover:border-white/20"
        >
          <div
            className={`mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br ${c.grad} shadow-lg ring-1 ring-white/10`}
          >
            <c.icon className="h-7 w-7 text-white" strokeWidth={1.5} />
          </div>
          <h3 className="text-lg font-semibold text-white">{c.title}</h3>
          <p className="mt-3 text-sm leading-relaxed text-slate-400">{c.desc}</p>
          <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-white/5 blur-2xl transition group-hover:bg-white/10" />
        </motion.article>
      ))}
    </div>
  );
}
