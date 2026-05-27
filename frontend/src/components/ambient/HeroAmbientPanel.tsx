/** 首页首卡右侧装饰：雷达网格 + 节点连线，纯 CSS/SVG */
export function HeroAmbientPanel({ className = "" }: { className?: string }) {
  return (
    <div
      className={`hero-ambient-panel relative flex items-center justify-center ${className}`.trim()}
      aria-hidden
      data-testid="hero-ambient-panel"
    >
      <div className="hero-ambient-glow" />
      <div className="hero-ambient-ring hero-ambient-ring-1" />
      <div className="hero-ambient-ring hero-ambient-ring-2" />
      <div className="hero-ambient-ring hero-ambient-ring-3" />
      <svg className="hero-ambient-svg" viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="hero-ambient-line" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgb(139 92 246)" stopOpacity="0.5" />
            <stop offset="50%" stopColor="rgb(14 165 233)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="rgb(99 102 241)" stopOpacity="0.2" />
          </linearGradient>
        </defs>
        <circle className="hero-ambient-node" cx="100" cy="100" r="3.5" fill="rgb(139 92 246)" fillOpacity="0.85" />
        <circle className="hero-ambient-node hero-ambient-node-d1" cx="48" cy="62" r="2.5" fill="rgb(14 165 233)" fillOpacity="0.7" />
        <circle className="hero-ambient-node hero-ambient-node-d2" cx="158" cy="72" r="2.5" fill="rgb(99 102 241)" fillOpacity="0.7" />
        <circle className="hero-ambient-node hero-ambient-node-d3" cx="132" cy="148" r="2.5" fill="rgb(167 139 250)" fillOpacity="0.65" />
        <circle className="hero-ambient-node hero-ambient-node-d4" cx="62" cy="138" r="2" fill="rgb(56 189 248)" fillOpacity="0.6" />
        <path
          className="hero-ambient-edge"
          d="M100 100 L48 62 M100 100 L158 72 M100 100 L132 148 M100 100 L62 138 M48 62 L158 72"
          stroke="url(#hero-ambient-line)"
          strokeWidth="1"
          strokeLinecap="round"
        />
        <path
          className="hero-ambient-edge hero-ambient-edge-soft"
          d="M48 62 L62 138 M158 72 L132 148"
          stroke="url(#hero-ambient-line)"
          strokeWidth="0.75"
          strokeLinecap="round"
          opacity="0.45"
        />
      </svg>
      <div className="hero-ambient-chip">多源雷达</div>
    </div>
  );
}
