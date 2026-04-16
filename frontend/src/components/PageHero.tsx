import type { ReactNode } from "react";

type PageHeroProps = {
  title: ReactNode;
  subtitle: ReactNode;
  /** Optional icon or small visual on the right */
  visual?: ReactNode;
};

export function PageHero({ title, subtitle, visual }: PageHeroProps) {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900/90 via-slate-950/80 to-black/90 p-8 md:p-10">
      <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-fuchsia-500/15 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-16 left-1/4 h-48 w-48 rounded-full bg-cyan-500/10 blur-3xl" />
      <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight md:text-4xl">
            <span className="text-gradient">{title}</span>
          </h1>
          <div className="mt-3 max-w-xl text-sm leading-relaxed text-slate-400 md:text-base">{subtitle}</div>
        </div>
        {visual ? <div className="shrink-0 md:pl-6">{visual}</div> : null}
      </div>
      <div className="mt-6 h-px w-full bg-gradient-to-r from-transparent via-white/15 to-transparent" />
    </div>
  );
}
