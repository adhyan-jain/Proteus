"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CLASS_COLOR_SEQUENCE, chartColors, tooltipStyle } from "./chart-theme";

export function ClassDistributionChart({ distribution }: { distribution: Record<string, number> }) {
  const data = Object.entries(distribution)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({ name, count }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 26)}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={chartColors.grid} strokeDasharray="2 3" horizontal={false} />
        <XAxis type="number" stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false} axisLine={{ stroke: chartColors.grid }} />
        <YAxis
          type="category"
          dataKey="name"
          stroke={chartColors.axis}
          tick={{ fontSize: 10, fill: chartColors.text }}
          tickLine={false}
          axisLine={{ stroke: chartColors.grid }}
          width={140}
        />
        <Tooltip {...tooltipStyle} formatter={(v) => (typeof v === "number" ? v.toLocaleString("en-US") : v)} />
        <Bar dataKey="count" radius={[0, 3, 3, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={CLASS_COLOR_SEQUENCE[i % CLASS_COLOR_SEQUENCE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
