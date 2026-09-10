"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartColors, tooltipStyle } from "./chart-theme";

export function GanLossChart({ lossLog }: { lossLog: { step: number; g_loss: number; d_loss: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={lossLog} margin={{ top: 4, right: 12, left: -8, bottom: 0 }}>
        <CartesianGrid stroke={chartColors.grid} strokeDasharray="2 3" vertical={false} />
        <XAxis
          dataKey="step"
          stroke={chartColors.axis}
          tick={{ fontSize: 10, fill: chartColors.text }}
          tickLine={false}
          axisLine={{ stroke: chartColors.grid }}
          label={{ value: "training step", position: "insideBottom", offset: -2, fontSize: 10, fill: chartColors.axis }}
        />
        <YAxis stroke={chartColors.axis} tick={{ fontSize: 10, fill: chartColors.text }} tickLine={false} axisLine={{ stroke: chartColors.grid }} width={40} />
        <Tooltip {...tooltipStyle} formatter={(v) => (typeof v === "number" ? v.toFixed(3) : v)} />
        <Line type="monotone" dataKey="g_loss" stroke={chartColors.synthetic} strokeWidth={1.6} dot={false} name="generator loss" />
        <Line type="monotone" dataKey="d_loss" stroke={chartColors.network} strokeWidth={1.6} dot={false} name="critic loss" />
        <Legend wrapperStyle={{ fontSize: 11, color: chartColors.text }} iconSize={8} />
      </LineChart>
    </ResponsiveContainer>
  );
}
