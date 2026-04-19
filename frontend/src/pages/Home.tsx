import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, BookOpen, LineChart } from "lucide-react";
import { useI18n } from "@/i18n";
import { publicApi } from "@/lib/publicApi";

export function Home() {
  const { t } = useI18n();
  const [hotAt, setHotAt] = useState<string | null>(null);

  useEffect(() => {
    publicApi.hot().then((h) => setHotAt(h.generated_at)).catch(() => {});
  }, []);

  return (
    <div className="relative mx-auto max-w-5xl px-4 py-16 text-slate-100">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="text-center">
        <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">{t("brand")}</h1>
        <p className="mt-3 text-slate-400">{t("tagline")}</p>
        {hotAt ? <p className="mt-2 text-xs text-cyan-500/80">热门快照：{hotAt}</p> : null}
      </motion.div>

      <div className="mt-14 grid gap-6 sm:grid-cols-3">
        <Link to="/trends" className="group rounded-2xl border border-white/10 bg-white/[0.04] p-6 transition hover:border-cyan-500/40">
          <LineChart className="h-8 w-8 text-cyan-400" />
          <h2 className="mt-4 text-lg font-semibold text-white">{t("navTrends")}</h2>
          <p className="mt-2 text-sm text-slate-400">指标与序列 · `/api/public/v1`</p>
        </Link>
        <Link to="/resources" className="group rounded-2xl border border-white/10 bg-white/[0.04] p-6 transition hover:border-fuchsia-500/40">
          <BookOpen className="h-8 w-8 text-fuchsia-400" />
          <h2 className="mt-4 text-lg font-semibold text-white">{t("navResources")}</h2>
          <p className="mt-2 text-sm text-slate-400">文章列表 · 热门/最新</p>
        </Link>
        <Link to="/about" className="group rounded-2xl border border-white/10 bg-white/[0.04] p-6 transition hover:border-amber-500/40">
          <Activity className="h-8 w-8 text-amber-400" />
          <h2 className="mt-4 text-lg font-semibold text-white">{t("navAbout")}</h2>
          <p className="mt-2 text-sm text-slate-400">介绍与免责声明</p>
        </Link>
      </div>
    </div>
  );
}
