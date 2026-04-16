import { motion } from "framer-motion";
import { Github, Globe, Layers, Radio } from "lucide-react";

const items = [
  { icon: Github, label: "GitHub" },
  { icon: Layers, label: "Hugging Face" },
  { icon: Radio, label: "Hacker News" },
  { icon: Globe, label: "Product Hunt" },
];

/** 参考 Stripe / Vercel：生态来源条，带图标 */
export function EcosystemStrip({ lang }: { lang: "zh" | "en" }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-white/[0.02] px-6 py-8">
      <p className="mb-6 text-center font-mono text-[10px] uppercase tracking-[0.25em] text-slate-500">
        {lang === "zh" ? "开放生态 · 多源汇聚" : "Open ecosystem · multi-source"}
      </p>
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
