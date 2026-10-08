"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartColors, tooltipStyle } from "@/components/charts/chart-theme";

export type Series = { key: string; label: string; color: string };

export function StackedBars({
  data,
  series,
  height = 300,
  layout = "vertical",
  nameWidth = 150,
}: {
  data: Record<string, string | number>[];
  series: Series[];
  height?: number;
  layout?: "vertical" | "horizontal";
  nameWidth?: number;
}) {
  const vertical = layout === "vertical";
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={layout} margin={{ top: 4, right: 16, left: vertical ? 0 : -8, bottom: 0 }}>
        <CartesianGrid stroke={chartColors.grid} strokeDasharray="2 3" horizontal={!vertical} vertical={vertical} />
        {vertical ? (
          <>
            <XAxis type="number" stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false} />
            <YAxis type="category" dataKey="name" width={nameWidth} stroke={chartColors.axis}
              tick={{ fontSize: 10.5, fill: chartColors.text }} tickLine={false} />
          </>
        ) : (
          <>
            <XAxis dataKey="name" stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false} />
            <YAxis stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false} width={36} />
          </>
        )}
        <Tooltip {...tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} stackId="a" fill={s.color} isAnimationActive={false} />
        ))}
        <Legend wrapperStyle={{ fontSize: 11, color: chartColors.text }} iconSize={8} />
      </BarChart>
    </ResponsiveContainer>
  );
}
