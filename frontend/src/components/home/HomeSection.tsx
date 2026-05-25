import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

type Props = {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  action?: { label: string; to: string; state?: Record<string, unknown> };
  children: ReactNode;
  className?: string;
};

export function HomeSection({ title, subtitle, icon, action, children, className = "" }: Props) {
  return (
    <section className={className}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-base font-bold tracking-tight text-slate-900 sm:text-lg">
            {icon ? <span className="shrink-0 text-violet-600">{icon}</span> : null}
            {title}
          </h2>
          {subtitle ? <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-500 sm:text-sm">{subtitle}</p> : null}
        </div>
        {action ? (
          <Link
            to={action.to}
            state={action.state}
            className="inline-flex shrink-0 items-center gap-1 text-sm font-semibold text-violet-600 hover:underline"
          >
            {action.label}
            <ChevronRight className="h-4 w-4" strokeWidth={2} />
          </Link>
        ) : null}
      </div>
      {children}
    </section>
  );
}
