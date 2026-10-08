"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartColors, tooltipStyle } from "@/components/charts/chart-theme";

export type Curve = { name: string; label: string; mean: number[]; color: string; dashed?: boolean };

export function CurvesChart({ curves, firstWindow }: { curves: Curve[]; firstWindow: number }) {
  const n = Math.max(...curves.map((c) => c.mean.length));
  const data = Array.from({ length: n }, (_, i) => {
    const row: Record<string, number | null> = { t: firstWindow + i };
    for (const c of curves) row[c.name] = Number.isFinite(c.mean[i]) ? c.mean[i] : null;
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 6, right: 14, left: -8, bottom: 0 }}>
        <CartesianGrid stroke={chartColors.grid} strokeDasharray="2 3" vertical={false} />
        <XAxis dataKey="t" stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false}
          axisLine={{ stroke: chartColors.grid }}
          label={{ value: "post-drift window t", position: "insideBottom", offset: -2, fontSize: 10, fill: chartColors.axis }} />
        <YAxis domain={[0, 1]} stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false}
          axisLine={{ stroke: chartColors.grid }} width={38} />
        <Tooltip {...tooltipStyle} formatter={(v) => (typeof v === "number" ? v.toFixed(3) : v)} />
        {curves.map((c) => (
          <Line key={c.name} type="monotone" dataKey={c.name} name={c.label} stroke={c.color} strokeWidth={c.dashed ? 1.5 : 2}
            strokeDasharray={c.dashed ? "4 3" : undefined} dot={{ r: 2 }} isAnimationActive={false} connectNulls />
        ))}
        <Legend wrapperStyle={{ fontSize: 11, color: chartColors.text }} iconSize={8} />
      </LineChart>
    </ResponsiveContainer>
  );
}
