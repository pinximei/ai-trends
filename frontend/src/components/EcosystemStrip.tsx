import { motion } from "framer-motion";
import { Github, Globe, Layers, Radio } from "lucide-react";

const items = [
  { icon: Github, label: "代码协作" },
  { icon: Layers, label: "模型社区" },
  { icon: Radio, label: "技术聚类" },
  { icon: Globe, label: "产品发现" },
];

/** 生态来源条（图标示意，名称已中文化） */
export function EcosystemStrip() {
  return (
    <div className="rounded-2xl border border-white/5 bg-white/[0.02] px-6 py-8">
      <p className="mb-6 text-center font-mono text-[10px] tracking-[0.2em] text-slate-500">开放生态 · 多源汇聚</p>
      <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-8">
        {items.map(({ icon: Icon, label }, i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.06 }}
            className="group flex items-center gap-2 rounded-full border border-white/10 bg-night-900/80 px-4 py-2.5 text-sm text-slate-400 shadow-lg transition hover:border-cyan-500/30 hover:text-cyan-200"
          >
            <Icon className="h-4 w-4 opacity-70 transition group-hover:opacity-100" />
            <span>{label}</span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
