/** 全站底层氛围：底部柔光与网格，不阻挡交互 */
export function SiteAmbientBackdrop() {
  return (
    <div
      className="site-ambient-root pointer-events-none fixed inset-0 -z-10 overflow-hidden"
      aria-hidden
    >
      <div className="site-ambient-mesh" />
      <div className="site-ambient-orb site-ambient-orb-a" />
      <div className="site-ambient-orb site-ambient-orb-b" />
      <div className="site-ambient-orb site-ambient-orb-c" />
      <div className="site-ambient-grid" />
      <div className="site-ambient-scanline" />
    </div>
  );
}
