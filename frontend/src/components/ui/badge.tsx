import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export type Tone = "good" | "warn" | "bad" | "network" | "synthetic" | "idle" | "neutral";

const toneClasses: Record<Tone, string> = {
  good: "text-good bg-good-dim/40 border-good/30",
  warn: "text-warn bg-warn-dim/40 border-warn/30",
  bad: "text-bad bg-bad-dim/40 border-bad/30",
  network: "text-network bg-network-dim/40 border-network/30",
  synthetic: "text-synthetic bg-synthetic-dim/40 border-synthetic/30",
  idle: "text-text-tertiary bg-surface-2 border-border-default",
  neutral: "text-text-secondary bg-surface-2 border-border-default",
};

export function Badge({
  tone = "neutral",
  children,
  className,
  dot,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-[10.5px] font-medium uppercase tracking-wide",
        toneClasses[tone],
        className
      )}
    >
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full", dotColor[tone])} />}
      {children}
    </span>
  );
}

const dotColor: Record<Tone, string> = {
  good: "bg-good",
  warn: "bg-warn",
  bad: "bg-bad",
  network: "bg-network",
  synthetic: "bg-synthetic",
  idle: "bg-idle",
  neutral: "bg-text-tertiary",
};
