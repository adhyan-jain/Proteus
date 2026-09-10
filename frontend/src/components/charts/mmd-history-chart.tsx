"use client";

import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { chartColors, tooltipStyle } from "./chart-theme";
import type { GateEntry } from "@/lib/api";

export function MmdHistoryChart({ entries, threshold }: { entries: GateEntry[]; threshold: number }) {
  const data = entries.map((e) => ({ x: e.step, y: e.mmd_score, n: e.n_samples, admitted: e.admitted }));
  const admitted = data.filter((d) => d.admitted);
  const rejected = data.filter((d) => !d.admitted);

  return (
    <ResponsiveContainer width="100%" height={220}>
      <ScatterChart margin={{ top: 4, right: 12, left: -8, bottom: 0 }}>
        <CartesianGrid stroke={chartColors.grid} strokeDasharray="2 3" />
        <XAxis
          dataKey="x"
          type="number"
          stroke={chartColors.axis}
          tick={{ fontSize: 10, fill: chartColors.text }}
          tickLine={false}
          axisLine={{ stroke: chartColors.grid }}
          label={{ value: "step", position: "insideBottom", offset: -2, fontSize: 10, fill: chartColors.axis }}
        />
        <YAxis dataKey="y" stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false} axisLine={{ stroke: chartColors.grid }} width={36} />
        <ZAxis dataKey="n" range={[40, 160]} />
        <Tooltip {...tooltipStyle} formatter={(v) => (typeof v === "number" ? v.toFixed(3) : v)} />
        <ReferenceLine y={threshold} stroke={chartColors.warn} strokeDasharray="4 3" label={{ value: "threshold", fontSize: 10, fill: chartColors.warn }} />
        <Scatter data={admitted} fill={chartColors.good} name="admitted" />
        <Scatter data={rejected} fill={chartColors.bad} name="rejected" />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
