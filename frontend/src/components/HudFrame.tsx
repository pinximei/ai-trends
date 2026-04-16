import { motion } from "framer-motion";
import type { ReactNode } from "react";

/** HUD 角标 + 可选动态描边 */
export function HudFrame({
  children,
  className = "",
  label,
}: {
  children: ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    <div className={`relative ${className}`}>
      {/* 四角 */}
      <span className="pointer-events-none absolute -left-px -top-px h-6 w-6 border-l-2 border-t-2 border-cyan-400/50" />
      <span className="pointer-events-none absolute -right-px -top-px h-6 w-6 border-r-2 border-t-2 border-cyan-400/50" />
      <span className="pointer-events-none absolute -bottom-px -left-px h-6 w-6 border-b-2 border-l-2 border-fuchsia-400/40" />
      <span className="pointer-events-none absolute -bottom-px -right-px h-6 w-6 border-b-2 border-r-2 border-fuchsia-400/40" />
      {label && (
        <motion.span
          className="absolute -top-3 left-4 bg-night-950 px-2 font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-400/90"
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
        >
          {label}
        </motion.span>
      )}
      {children}
    </div>
  );
}
