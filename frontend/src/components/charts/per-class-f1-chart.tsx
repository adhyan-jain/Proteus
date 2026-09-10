"use client";

import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CLASS_COLOR_SEQUENCE, chartColors, tooltipStyle } from "./chart-theme";

export function PerClassF1Chart({
  perClassF1,
  classNames,
  driftSchedule,
}: {
  perClassF1: number[][];
  classNames: string[];
  driftSchedule: number[];
}) {
  const data = perClassF1.map((row, t) => {
    const point: Record<string, number> = { t };
    classNames.forEach((name, ci) => {
      point[name] = row[ci];
    });
    return point;
  });

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={chartColors.grid} strokeDasharray="2 3" vertical={false} />
        <XAxis dataKey="t" stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false} axisLine={{ stroke: chartColors.grid }} />
        <YAxis domain={[0, 1]} stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false} axisLine={{ stroke: chartColors.grid }} width={34} />
        <Tooltip {...tooltipStyle} formatter={(v) => (typeof v === "number" ? v.toFixed(3) : v)} />
        {driftSchedule.map((t) => (
          <ReferenceLine key={t} x={t} stroke={chartColors.bad} strokeDasharray="3 3" strokeOpacity={0.5} />
        ))}
        {classNames.map((name, i) => (
          <Line
            key={name}
            type="monotone"
            dataKey={name}
            stroke={CLASS_COLOR_SEQUENCE[i % CLASS_COLOR_SEQUENCE.length]}
            strokeWidth={1.6}
            dot={false}
          />
        ))}
        <Legend wrapperStyle={{ fontSize: 11, color: chartColors.text }} iconSize={8} />
      </LineChart>
    </ResponsiveContainer>
  );
}
