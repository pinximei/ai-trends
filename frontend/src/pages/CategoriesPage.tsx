import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { apiGet } from "@/api";
import { useI18n } from "@/i18n";
import { ArrowUpRight, Hexagon, Layers, Radar } from "lucide-react";
import { PageHero } from "@/components/PageHero";

export function CategoriesPage() {
  const { lang, t } = useI18n();
  const [items, setItems] = useState<string[]>([]);

  useEffect(() => {
    apiGet<{ items: string[] }>("/api/v1/categories", lang).then((d) => setItems(d.items));
  }, [lang]);

  const palette = [
    "from-fuchsia-500/25 to-rose-500/10",
    "from-cyan-500/25 to-blue-500/10",
    "from-amber-500/25 to-orange-500/10",
    "from-violet-500/25 to-purple-500/10",
  ];
  const categoryItems = items.length ? items : Array.from({ length: 6 }, (_, i) => `category-${i + 1}`);

  return (
    <div className="space-y-8">
      <PageHero
        title={t("categories")}
        subtitle={lang === "zh" ? "按主题浏览 Agent 方向，快速聚焦你关心的赛道。" : "Browse by topic to quickly focus on tracks you care about."}
        visual={
          <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-slate-300">
            <Layers className="h-4 w-4 text-cyan-300" />
            {lang === "zh" ? "专题视图" : "Topic view"}
          </div>
        }
      />
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-4">
          <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-200/70">{lang === "zh" ? "分类总数" : "categories"}</div>
          <div className="mt-1 text-2xl font-bold text-white">{items.length || "—"}</div>
        </div>
        <div className="rounded-2xl border border-fuchsia-500/20 bg-fuchsia-500/10 p-4">
          <div className="text-[10px] font-mono uppercase tracking-widest text-fuchsia-200/70">{lang === "zh" ? "推荐入口" : "suggested path"}</div>
          <div className="mt-1 text-sm text-slate-200">{lang === "zh" ? "先灵感后趋势" : "Inspiration first, then trends"}</div>
        </div>
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">
          <div className="text-[10px] font-mono uppercase tracking-widest text-amber-200/70">{lang === "zh" ? "更新节奏" : "update rhythm"}</div>
          <div className="mt-1 text-sm text-slate-200">{lang === "zh" ? "按日/周/月切换观察" : "Observe by day/week/month"}</div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {categoryItems.map((c, i) => (
          <motion.div
            key={c}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            whileHover={{ y: -4 }}
            className={`glass glass-hover rounded-2xl border border-white/10 bg-gradient-to-br ${palette[i % palette.length]} p-5`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/20 px-2 py-1 text-xs text-slate-300">
                <Hexagon className="h-3.5 w-3.5 text-violet-300" />
                {items.length ? c : <span className="animate-pulse">{lang === "zh" ? "采集中" : "collecting"}</span>}
              </div>
              <Radar className="h-4 w-4 text-cyan-300/80" />
            </div>
            <p className="mt-4 text-sm text-slate-300">
              {lang === "zh"
                ? "从该分类快速查看新信号与已验证趋势，减少跨页面搜索成本。"
                : "Jump into fresh signals and validated trends for this category with fewer navigation steps."}
            </p>
            <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-black/25">
              <div className="h-full rounded-full bg-gradient-to-r from-cyan-300 to-fuchsia-400" style={{ width: `${48 + (i % 5) * 10}%` }} />
            </div>
            <div className="mt-4 flex items-center justify-between text-xs">
              <span className="text-slate-400">{lang === "zh" ? "热度指数" : "heat index"} {56 + i * 3}</span>
              <Link to="/trends" className="inline-flex items-center gap-1 text-cyan-300 hover:underline">
                {lang === "zh" ? "查看趋势" : "View trends"} <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
