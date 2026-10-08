import type { CI } from "@/lib/research";
import { chartColors } from "@/components/charts/chart-theme";
import { fx } from "@/lib/research-format";

export type CiRow = {
  label: string;
  sub?: string;
  ci: CI;
  color?: string;
  bold?: boolean;
};

// Horizontal dot-and-whisker plot (forest plot). Pure SVG so it renders on the server and is
// exact: the whisker is the artifact's t-interval, the dot its mean, nothing is smoothed.
export function CiPlot({
  rows,
  zero = true,
  labelWidth = 210,
  rowHeight = 28,
  digits = 3,
  axisLabel,
}: {
  rows: CiRow[];
  zero?: boolean;
  labelWidth?: number;
  rowHeight?: number;
  digits?: number;
  axisLabel?: string;
}) {
  const W = 860;
  const valueCol = 170;
  const plotL = labelWidth + 8;
  const plotR = W - valueCol;
  const finite = rows.flatMap((r) => [r.ci.lo, r.ci.hi, r.ci.mean]).filter((v): v is number => v !== null && Number.isFinite(v));
  if (finite.length === 0) {
    return <p className="text-[12px] text-text-tertiary">No finite estimates in this artifact.</p>;
  }
  let lo = Math.min(...finite, zero ? 0 : Infinity);
  let hi = Math.max(...finite, zero ? 0 : -Infinity);
  const pad = (hi - lo || 1) * 0.06;
  lo -= pad;
  hi += pad;
  const x = (v: number) => plotL + ((v - lo) / (hi - lo)) * (plotR - plotL);
  const H = rows.length * rowHeight + 34;
  const ticks = Array.from({ length: 6 }, (_, i) => lo + ((hi - lo) * i) / 5);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="confidence interval plot">
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={x(t)} x2={x(t)} y1={6} y2={H - 26} stroke={chartColors.grid} strokeDasharray="2 3" />
          <text x={x(t)} y={H - 12} fontSize={10} textAnchor="middle" fill={chartColors.axis}>
            {t.toFixed(2)}
          </text>
        </g>
      ))}
      {zero && lo < 0 && hi > 0 && (
        <line x1={x(0)} x2={x(0)} y1={6} y2={H - 26} stroke={chartColors.bad} strokeOpacity={0.7} />
      )}
      {axisLabel && (
        <text x={(plotL + plotR) / 2} y={H - 1} fontSize={10} textAnchor="middle" fill={chartColors.axis}>
          {axisLabel}
        </text>
      )}
      {rows.map((r, i) => {
        const y = 14 + i * rowHeight;
        const c = r.color ?? chartColors.network;
        const has = r.ci.mean !== null && r.ci.lo !== null && r.ci.hi !== null;
        return (
          <g key={r.label}>
            <text x={0} y={y + 3} fontSize={11.5} fill={r.bold ? "#e7e9ec" : chartColors.text} fontWeight={r.bold ? 600 : 400}>
              {r.label}
            </text>
            {r.sub && (
              <text x={0} y={y + 14} fontSize={9.5} fill={chartColors.axis}>
                {r.sub}
              </text>
            )}
            {has ? (
              <>
                <line x1={x(r.ci.lo!)} x2={x(r.ci.hi!)} y1={y} y2={y} stroke={c} strokeWidth={2} />
                <line x1={x(r.ci.lo!)} x2={x(r.ci.lo!)} y1={y - 4} y2={y + 4} stroke={c} />
                <line x1={x(r.ci.hi!)} x2={x(r.ci.hi!)} y1={y - 4} y2={y + 4} stroke={c} />
                <circle cx={x(r.ci.mean!)} cy={y} r={4} fill={c} />
              </>
            ) : (
              <text x={plotL} y={y + 3} fontSize={10.5} fill={chartColors.axis}>
                not measurable
              </text>
            )}
            <text x={W} y={y + 3} fontSize={10.5} textAnchor="end" fill={chartColors.text} fontFamily="var(--font-geist-mono)">
              {has ? `${fx(r.ci.mean, digits)} [${fx(r.ci.lo, digits)}, ${fx(r.ci.hi, digits)}]` : "—"}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
