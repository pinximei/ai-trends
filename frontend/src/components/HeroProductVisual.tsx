import { motion } from "framer-motion";

/** 参考 Linear / Vercel：右侧「产品画板」式抽象视觉 */
export function HeroProductVisual() {
  const bars = [
    { bg: "linear-gradient(180deg, rgba(34,211,238,0.55), rgba(34,211,238,0.05))", h: 72 },
    { bg: "linear-gradient(180deg, rgba(217,70,239,0.5), rgba(217,70,239,0.05))", h: 55 },
    { bg: "linear-gradient(180deg, rgba(251,191,36,0.5), rgba(251,191,36,0.05))", h: 88 },
  ];

  return (
    <motion.div
      className="relative mx-auto w-full max-w-xl lg:max-w-none"
      initial={{ opacity: 0, y: 24, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="absolute -inset-4 rounded-[2rem] bg-gradient-to-tr from-cyan-500/20 via-fuchsia-600/15 to-amber-500/10 blur-2xl" />
      <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-b from-white/[0.08] to-night-950/90 shadow-2xl shadow-black/50 ring-1 ring-white/5">
        <div className="flex items-center gap-2 border-b border-white/5 px-4 py-3">
          <div className="flex gap-1.5">
            <span className="h-3 w-3 rounded-full bg-red-500/80" />
            <span className="h-3 w-3 rounded-full bg-amber-500/80" />
            <span className="h-3 w-3 rounded-full bg-emerald-500/80" />
          </div>
          <div className="ml-4 flex-1 rounded-md border border-white/5 bg-black/30 px-3 py-1 text-center font-mono text-[10px] text-slate-500">
            aisoul.app / radar
          </div>
        </div>
        <div className="grid gap-0 md:grid-cols-12">
          <div className="border-b border-white/5 p-4 md:col-span-3 md:border-b-0 md:border-r">
            {[65, 48, 82, 55].map((w, i) => (
              <motion.div
                key={i}
                className="mb-2 h-2 rounded-full bg-gradient-to-r from-slate-500/40 to-slate-700/20"
                initial={{ width: 0 }}
                animate={{ width: `${w}%` }}
                transition={{ delay: 0.4 + i * 0.1, duration: 0.5 }}
              />
            ))}
            <div className="mt-4 h-24 rounded-lg bg-gradient-to-br from-cyan-500/25 to-violet-600/15 ring-1 ring-white/10" />
          </div>
          <div className="relative col-span-6 min-h-[220px] p-6 md:col-span-6">
            <svg className="absolute inset-0 h-full w-full" viewBox="0 0 400 220" fill="none" aria-hidden>
              <defs>
                <linearGradient id="hvLine" x1="0" y1="0" x2="400" y2="0" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#22d3ee" stopOpacity="0.55" />
                  <stop offset="1" stopColor="#a855f7" stopOpacity="0.35" />
                </linearGradient>
                <filter id="glow">
                  <feGaussianBlur stdDeviation="2.5" result="b" />
                  <feMerge>
                    <feMergeNode in="b" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              <motion.path
                d="M 20 160 Q 100 40 200 100 T 380 60"
                stroke="url(#hvLine)"
                strokeWidth="2.5"
                fill="none"
                filter="url(#glow)"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1.4, ease: "easeInOut" }}
              />
              {[
                [40, 150],
                [120, 90],
                [200, 100],
                [280, 70],
                [350, 65],
              ].map(([x, y], i) => (
                <motion.circle
                  key={i}
                  cx={x}
                  cy={y}
                  r="5"
                  fill="#f1f5f9"
                  filter="url(#glow)"
                  initial={{ opacity: 0, scale: 0 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.8 + i * 0.1 }}
                />
              ))}
            </svg>
            <div className="relative z-10 flex h-full min-h-[180px] flex-col justify-end">
              <p className="font-mono text-[10px] uppercase tracking-widest text-cyan-400/80">live signal</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-white">78.2</p>
              <p className="truncate text-xs text-slate-500">workflow-automation-agent</p>
            </div>
          </div>
          <div className="border-t border-white/5 p-4 md:col-span-3 md:border-l md:border-t-0">
            <div className="flex gap-2 md:hidden">
              {bars.map((b, i) => (
                <motion.div
                  key={i}
                  className="h-2 flex-1 rounded-full"
                  style={{ background: b.bg }}
                  initial={{ opacity: 0, scaleX: 0.2 }}
                  animate={{ opacity: 1, scaleX: 1 }}
                  transition={{ delay: 0.6 + i * 0.08 }}
                />
              ))}
            </div>
            <div className="hidden flex-col justify-end gap-3 md:flex">
              {bars.map((b, i) => (
                <motion.div
                  key={i}
                  className="w-full rounded-xl"
                  style={{ background: b.bg, height: `${b.h}px` }}
                  initial={{ opacity: 0, x: 12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.6 + i * 0.08 }}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
