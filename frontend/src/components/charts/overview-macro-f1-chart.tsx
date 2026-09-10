"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chartColors, tooltipStyle } from "./chart-theme";
import type { ExperimentConditions } from "@/lib/api";

export function OverviewMacroF1Chart({ conditions }: { conditions: Extract<ExperimentConditions, { available: true }> }) {
  const baseline = conditions.conditions.baseline?.macro_f1 ?? [];
  const closedLoop = conditions.conditions.closed_loop?.macro_f1 ?? [];
  const staticAug = conditions.conditions.static_augmentation?.macro_f1 ?? [];

  const data = baseline.map((_, i) => ({
    t: i,
    baseline: baseline[i],
    static_augmentation: staticAug[i],
    closed_loop: closedLoop[i],
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={chartColors.grid} strokeDasharray="2 3" vertical={false} />
        <XAxis
          dataKey="t"
          stroke={chartColors.axis}
          tick={{ fontSize: 10, fill: chartColors.text }}
          tickLine={false}
          axisLine={{ stroke: chartColors.grid }}
          label={{ value: "timestep", position: "insideBottom", offset: -2, fontSize: 10, fill: chartColors.axis }}
        />
        <YAxis
          domain={[0, 1]}
          stroke={chartColors.axis}
          tick={{ fontSize: 10, fill: chartColors.text }}
          tickLine={false}
          axisLine={{ stroke: chartColors.grid }}
          width={34}
        />
        <Tooltip {...tooltipStyle} formatter={(v) => (typeof v === "number" ? v.toFixed(3) : v)} />
        {conditions.drift_schedule.map((t) => (
          <ReferenceLine key={t} x={t} stroke={chartColors.bad} strokeDasharray="3 3" strokeOpacity={0.6} />
        ))}
        {conditions.retrain_timesteps.map((t) => (
          <ReferenceLine key={`r${t}`} x={t} stroke={chartColors.synthetic} strokeDasharray="1 2" strokeOpacity={0.5} />
        ))}
        <Line type="monotone" dataKey="baseline" stroke={chartColors.idle} strokeWidth={1.5} dot={false} name="baseline" isAnimationActive={false} />
        <Line
          type="monotone"
          dataKey="static_augmentation"
          stroke={chartColors.warn}
          strokeWidth={1.5}
          dot={false}
          name="static augmentation"
         isAnimationActive={false} />
        <Line type="monotone" dataKey="closed_loop" stroke={chartColors.good} strokeWidth={2} dot={false} name="closed loop (proteus)" isAnimationActive={false} />
        <Legend wrapperStyle={{ fontSize: 11, color: chartColors.text }} iconSize={8} />
      </LineChart>
    </ResponsiveContainer>
  );
}
