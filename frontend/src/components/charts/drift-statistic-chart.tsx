"use client";

import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartColors, tooltipStyle } from "./chart-theme";
import type { DriftEvent } from "@/lib/api";

export function DriftStatisticChart({ events }: { events: DriftEvent[] }) {
  const alpha = events[0]?.alpha ?? 0.05;
  const data = events.map((e) => ({ t: e.timestep, p_value: e.p_value, statistic: e.statistic, fired: e.fired }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={chartColors.grid} strokeDasharray="2 3" vertical={false} />
        <XAxis dataKey="t" stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false} axisLine={{ stroke: chartColors.grid }} />
        <YAxis stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false} axisLine={{ stroke: chartColors.grid }} width={34} />
        <Tooltip
          {...tooltipStyle}
          formatter={(v, name) => [typeof v === "number" ? v.toFixed(4) : v, name]}
          labelFormatter={(t) => `timestep ${t}`}
        />
        <ReferenceLine
          y={alpha}
          stroke={chartColors.warn}
          strokeDasharray="4 3"
          label={{ value: `α=${alpha}`, fontSize: 10, fill: chartColors.warn, position: "insideTopRight" }}
        />
        <Bar dataKey="p_value" name="p-value" radius={[2, 2, 0, 0]} isAnimationActive={false}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.fired ? chartColors.bad : chartColors.network} fillOpacity={d.fired ? 0.9 : 0.5} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
