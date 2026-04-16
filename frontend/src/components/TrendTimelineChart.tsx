import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function TrendTimelineChart({ data }: { data: { x: string; y: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <XAxis dataKey="x" stroke="#64748b" fontSize={11} />
        <YAxis stroke="#64748b" fontSize={11} width={40} />
        <Tooltip
          contentStyle={{
            background: "rgba(15,23,42,0.95)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "12px",
          }}
        />
        <Line type="monotone" dataKey="y" stroke="#a78bfa" strokeWidth={3} dot={{ fill: "#c4b5fd" }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
