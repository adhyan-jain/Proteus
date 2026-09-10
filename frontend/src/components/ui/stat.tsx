import { cn } from "@/lib/utils";

export function Stat({
  label,
  value,
  unit,
  tone,
  className,
}: {
  label: string;
  value: string;
  unit?: string;
  tone?: "good" | "warn" | "bad" | "network" | "synthetic";
  className?: string;
}) {
  const toneColor = tone
    ? {
        good: "text-good",
        warn: "text-warn",
        bad: "text-bad",
        network: "text-network",
        synthetic: "text-synthetic",
      }[tone]
    : "text-text-primary";

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <span className="text-[10.5px] font-medium uppercase tracking-[0.1em] text-text-tertiary">
        {label}
      </span>
      <span className={cn("mono text-[22px] font-semibold leading-none", toneColor)}>
        {value}
        {unit && <span className="ml-1 text-[12px] font-normal text-text-tertiary">{unit}</span>}
      </span>
    </div>
  );
}
