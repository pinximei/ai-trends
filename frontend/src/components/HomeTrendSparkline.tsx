import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function HomeTrendSparkline({ data }: { data: { d: string; s: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data}>
        <defs>
          <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.55} />
            <stop offset="100%" stopColor="#a855f7" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="d" stroke="#475569" fontSize={11} tickLine={false} />
        <YAxis stroke="#475569" fontSize={11} tickLine={false} width={36} domain={["auto", "auto"]} />
        <Tooltip
          contentStyle={{
            background: "rgba(15,23,42,0.95)",
            border: "1px solid rgba(34,211,238,0.25)",
            borderRadius: "12px",
          }}
        />
        <Area type="monotone" dataKey="s" stroke="#22d3ee" strokeWidth={2} fill="url(#g1)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
