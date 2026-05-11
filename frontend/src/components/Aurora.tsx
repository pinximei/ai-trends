import { motion } from "framer-motion";

/** 浅色环境光斑 */
export function Aurora() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <motion.div
        className="absolute -left-1/4 top-0 h-[420px] w-[420px] rounded-full bg-gradient-to-br from-fuchsia-200/50 via-violet-100/30 to-transparent blur-3xl"
        animate={{ scale: [1, 1.06, 1], opacity: [0.45, 0.65, 0.45] }}
        transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute -right-1/4 top-1/4 h-[380px] w-[380px] rounded-full bg-gradient-to-bl from-sky-200/45 via-indigo-100/25 to-transparent blur-3xl"
        animate={{ scale: [1.04, 1, 1.04], x: [0, -20, 0] }}
        transition={{ duration: 16, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="absolute inset-0 bg-grid-fade bg-[length:64px_64px] opacity-[0.35] [mask-image:radial-gradient(ellipse_at_center,black,transparent_78%)]" />
    </div>
  );
}
