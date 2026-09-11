"use client";

import { useState } from "react";
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

// Plain-language "what does this stage do" copy, independent of live run data — this is what
// renders when a viewer clicks a stage, so it stays accurate to the pipeline's real mechanism
// regardless of what a given run's telemetry looked like. See ARCHITECTURE.md for the mechanism
// each of these summarizes.
const STAGE_EXPLANATION: Record<string, string> = {
  traffic:
    "Raw network traffic flowing through the SDN — the entry point for everything downstream. In this build there's no live Mininet/Ryu controller wired in, so this stage is simulated rather than a real capture.",
  ingestion:
    "Network flows are read into the pipeline as a stream of timesteps, in the order they'd arrive from the network, and handed to the classifier and the drift monitor.",
  classify:
    "The deployed IDS classifier scores each flow as benign or as a specific attack type. Its confidence on each prediction is also the signal the drift detector watches.",
  drift:
    "A Kolmogorov-Smirnov (KS) statistical test compares the classifier's current confidence distribution against its distribution at training time. A statistically significant shift means the traffic pattern has moved away from what the model learned.",
  gan:
    "When drift fires, a WGAN-GP (Wasserstein GAN with gradient penalty) generates new synthetic examples of the rare or drifted attack pattern, so there's fresh data to retrain on without waiting to collect more real attacks.",
  gate:
    "An MMD (Maximum Mean Discrepancy) check compares each synthetic batch against real data. Batches that don't look realistic enough are rejected here, before they can reach retraining.",
  retrain:
    "Synthetic samples that passed the fidelity gate, combined with real data, are used to retrain the classifier so it can recognize the new attack pattern.",
  deploy:
    "The freshly retrained classifier becomes the active model for the next timestep — closing the loop back into live classification.",
};

export function PipelineDiagram({ stages }: { stages: Stage[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedStage = stages.find((s) => s.id === selectedId) ?? null;
  const explanation = selectedStage
    ? STAGE_EXPLANATION[selectedStage.id] ?? "No description available for this stage."
    : null;

  return (
    <div className="relative">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {stages.map((stage, i) => {
          const style = STATE_STYLE[stage.state];
          const isSelected = stage.id === selectedId;
          return (
            <div key={stage.id} className="relative flex items-stretch gap-2">
              <button
                type="button"
                aria-pressed={isSelected}
                onClick={() => setSelectedId((current) => (current === stage.id ? null : stage.id))}
                className={cn(
                  "flex flex-1 cursor-pointer flex-col gap-1.5 rounded-md border px-3 py-3 text-left transition-colors",
                  "hover:border-text-tertiary focus:outline-none focus-visible:ring-1 focus-visible:ring-network",
                  style.border,
                  style.bg,
                  isSelected && "ring-1 ring-network"
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
              </button>
              {i < stages.length - 1 && (
                <div className="hidden items-center lg:flex">
                  <ArrowRight active={stage.state !== "idle" && stage.state !== "unavailable"} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-2 flex items-start gap-2 rounded-md border border-network/50 bg-network-dim/10 px-3 py-2.5">
        <InfoIcon />
        <div className="flex flex-col gap-0.5">
          <span className="mono text-[10px] uppercase tracking-wide text-network">
            {selectedStage ? selectedStage.label : "stage info"}
          </span>
          <p className="text-[11.5px] leading-snug text-text-secondary">
            {explanation ?? "Click a stage above to see what it does, in plain language."}
          </p>
        </div>
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

function InfoIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" className="mt-0.5 shrink-0 text-network">
      <circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <line x1="8" y1="7.2" x2="8" y2="11.3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      <circle cx="8" cy="4.9" r="0.9" fill="currentColor" />
    </svg>
  );
}
