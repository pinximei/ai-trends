import { motion } from "framer-motion";

export function Aurora() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <motion.div
        className="absolute -left-1/4 top-0 h-[520px] w-[520px] rounded-full bg-gradient-to-br from-rose-500/25 via-fuchsia-500/15 to-transparent blur-3xl"
        animate={{ scale: [1, 1.08, 1], opacity: [0.5, 0.75, 0.5] }}
        transition={{ duration: 10, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute -right-1/4 top-1/3 h-[480px] w-[480px] rounded-full bg-gradient-to-bl from-amber-400/15 via-violet-600/20 to-transparent blur-3xl"
        animate={{ scale: [1.05, 1, 1.05], x: [0, -30, 0] }}
        transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-0 left-1/3 h-[400px] w-[600px] rounded-full bg-cyan-500/10 blur-3xl"
        animate={{ y: [0, -30, 0] }}
        transition={{ duration: 12, repeat: Infinity }}
      />
      <div className="absolute inset-0 bg-grid-fade bg-[length:48px_48px] opacity-30 [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />
    </div>
  );
}
