/** 多层科技感背景：六边形纹理、慢旋锥光、底部数据流 */
export function TechAtmosphere() {
  const hex = encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="49" viewBox="0 0 28 49"><path fill="none" stroke="%2322d3ee" stroke-opacity="0.35" d="M14 0L28 8.5v17L14 34 0 25.5v-17L14 0z"/></svg>`
  );

  return (
    <div className="pointer-events-none fixed inset-0 -z-[5] overflow-hidden">
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage: `url("data:image/svg+xml,${hex}")`,
          backgroundSize: "28px 49px",
          maskImage: "radial-gradient(ellipse 80% 70% at 50% 40%, black 20%, transparent 70%)",
        }}
      />

      <div className="absolute left-1/2 top-[-30%] -translate-x-1/2">
        <div className="h-[100vmin] w-[100vmin] animate-spin-slow rounded-full opacity-25 blur-3xl [background:conic-gradient(from_180deg,transparent,rgba(34,211,238,0.12),transparent,rgba(168,85,247,0.1),transparent)]" />
      </div>

      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent" />
      <div className="animate-data-stream absolute bottom-0 left-[10%] right-[10%] h-[1px] bg-gradient-to-r from-transparent via-cyan-300/70 to-transparent" />
    </div>
  );
}
