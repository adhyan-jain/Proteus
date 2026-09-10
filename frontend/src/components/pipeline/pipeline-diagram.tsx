"use client";

import { cn } from "@/lib/utils";

export type StageState = "live" | "idle" | "warning" | "processing" | "completed" | "failed" | "unavailable";

export type Stage = {
  id: string;
  label: string;
  detail: string;
  state: StageState;
};

const STATE_STYLE: Record<StageState, { border: string; text: string; bg: string; dot: string }> = {
  live: { border: "border-network", text: "text-network", bg: "bg-network-dim/30", dot: "bg-network live-dot" },
  processing: { border: "border-synthetic", text: "text-synthetic", bg: "bg-synthetic-dim/30", dot: "bg-synthetic live-dot" },
  completed: { border: "border-good", text: "text-good", bg: "bg-good-dim/25", dot: "bg-good" },
  warning: { border: "border-warn", text: "text-warn", bg: "bg-warn-dim/30", dot: "bg-warn live-dot" },
  failed: { border: "border-bad", text: "text-bad", bg: "bg-bad-dim/30", dot: "bg-bad" },
  idle: { border: "border-border-default", text: "text-text-tertiary", bg: "bg-surface-2", dot: "bg-idle" },
  unavailable: { border: "border-border-subtle", text: "text-text-disabled", bg: "bg-surface-1", dot: "bg-text-disabled" },
};

export function PipelineDiagram({ stages }: { stages: Stage[] }) {
  return (
    <div className="relative">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {stages.map((stage, i) => {
          const style = STATE_STYLE[stage.state];
          return (
            <div key={stage.id} className="relative flex items-stretch gap-2">
              <div
                className={cn(
                  "flex flex-1 flex-col gap-1.5 rounded-md border px-3 py-3 transition-colors",
                  style.border,
                  style.bg
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="mono text-[10px] text-text-disabled">{String(i + 1).padStart(2, "0")}</span>
                  <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} />
                </div>
                <span className="text-[12px] font-semibold text-text-primary">{stage.label}</span>
                <span className={cn("mono text-[10.5px] uppercase tracking-wide", style.text)}>
                  {stage.state}
                </span>
                <p className="text-[11px] leading-snug text-text-tertiary">{stage.detail}</p>
              </div>
              {i < stages.length - 1 && (
                <div className="hidden items-center lg:flex">
                  <ArrowRight active={stage.state !== "idle" && stage.state !== "unavailable"} />
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex items-center gap-2 rounded-md border border-dashed border-border-default px-3 py-2">
        <LoopIcon />
        <span className="text-[11px] text-text-tertiary">
          Model redeployment feeds back into live classification — the loop closes here. Admitted synthetic
          data and freshly retrained weights become the new operating baseline for drift detection.
        </span>
      </div>
    </div>
  );
}

function ArrowRight({ active }: { active: boolean }) {
  return (
    <svg width="20" height="16" viewBox="0 0 20 16" className={active ? "text-network" : "text-border-default"}>
      <line x1="0" y1="8" x2="14" y2="8" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12 3 L18 8 L12 13" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function LoopIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" className="shrink-0 text-text-tertiary">
      <path
        d="M4 8a4 4 0 0 1 4-4h4M12 4l-2-2M12 4l-2 2M12 8a4 4 0 0 1-4 4H4M4 12l2 2M4 12l2-2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
