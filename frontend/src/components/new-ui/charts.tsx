"use client";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export type Series = { key: string; name: string; color: string };
type Row = Record<string, string | number | null>;

const tip = { contentStyle: { background: "#111827", border: "1px solid #334155", borderRadius: 8, color: "#f1f5f9", fontSize: 12 }, cursor: { fill: "rgba(255,255,255,0.05)" } };

export function Bars({ data, series, xKey = "name", log = false, height = 300, decimals = 1, horizontal = false, cellColors }: {
  data: Row[]; series: Series[]; xKey?: string; log?: boolean; height?: number; decimals?: number; horizontal?: boolean; cellColors?: string[];
}) {
  const fmt = (v: unknown) => (typeof v === "number" ? (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(decimals)) : "");
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 22, right: 56, left: horizontal ? 40 : 0, bottom: 4 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={horizontal} horizontal={!horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" scale={log ? "log" : "auto"} domain={log ? [1, "auto"] : [0, "auto"]} stroke="#94a3b8" fontSize={11} />
              <YAxis type="category" dataKey={xKey} stroke="#94a3b8" fontSize={11} width={150} />
            </>
          ) : (
            <>
              <XAxis dataKey={xKey} stroke="#94a3b8" fontSize={11} interval={0} />
              <YAxis scale={log ? "log" : "auto"} domain={log ? [1, "auto"] : [0, "auto"]} stroke="#94a3b8" fontSize={11} tickFormatter={fmt} />
            </>
          )}
          <Tooltip {...tip} formatter={(v) => fmt(v)} />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {cellColors && data.map((_, i) => <Cell key={i} fill={cellColors[i] ?? s.color} />)}
              <LabelList dataKey={s.key} position={horizontal ? "right" : "top"} formatter={(v) => fmt(v)} fill="#e2e8f0" fontSize={11} />
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
