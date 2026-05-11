/** 浅色版氛围：柔和网格 + 轻渐变（与 docs/assets/111.png 设计稿一致） */
export function TechAtmosphere() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-[5] overflow-hidden">
      <div
        className="absolute inset-0 opacity-[0.5]"
        style={{
          backgroundImage: `
            linear-gradient(rgba(148,163,184,0.07) 1px, transparent 1px),
            linear-gradient(90deg, rgba(148,163,184,0.07) 1px, transparent 1px)
          `,
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse 85% 75% at 50% 25%, black 15%, transparent 70%)",
        }}
      />
      <div className="absolute -left-[20%] top-[-10%] h-[70vmin] w-[70vmin] rounded-full bg-gradient-to-br from-violet-200/40 via-transparent to-transparent blur-3xl" />
      <div className="absolute -right-[15%] top-[20%] h-[55vmin] w-[55vmin] rounded-full bg-gradient-to-bl from-sky-200/35 via-transparent to-transparent blur-3xl" />
    </div>
  );
}
