import { cn } from "@/lib/utils";
import { fmtInt, fmtNum } from "@/lib/utils";
import type { GateEntry } from "@/lib/api";

export function GateFlow({ entry, threshold }: { entry: GateEntry; threshold: number }) {
  const admitted = entry.admitted;
  return (
    <div className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[1fr_auto_1fr_auto_1fr]">
      <FlowBox label="Generated Batch" tone="synthetic">
        <span className="mono text-[11px] text-text-tertiary">n={fmtInt(entry.n_samples)} · step {entry.step}</span>
      </FlowBox>
      <Connector />
      <FlowBox label="MMD Test" tone="network">
        <span className="mono text-[16px] font-semibold text-text-primary">{fmtNum(entry.mmd_score)}</span>
        <span className="mono text-[10px] text-text-tertiary">vs threshold {fmtNum(threshold)}</span>
      </FlowBox>
      <Connector />
      <FlowBox label="Decision" tone={admitted ? "good" : "bad"}>
        <span className={cn("mono text-[13px] font-bold uppercase tracking-wide", admitted ? "text-good" : "text-bad")}>
          {admitted ? "Admit" : "Reject"}
        </span>
      </FlowBox>
    </div>
  );
}

function Connector() {
  return (
    <div className="hidden justify-center sm:flex">
      <svg width="24" height="16" viewBox="0 0 24 16">
        <line x1="0" y1="8" x2="16" y2="8" stroke="var(--border-strong)" strokeWidth="1.5" />
        <path d="M14 3 L22 8 L14 13" fill="none" stroke="var(--border-strong)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

function FlowBox({
  label,
  tone,
  children,
}: {
  label: string;
  tone: "synthetic" | "network" | "good" | "bad";
  children: React.ReactNode;
}) {
  const toneClass = {
    synthetic: "border-synthetic/40 bg-synthetic-dim/20",
    network: "border-network/40 bg-network-dim/20",
    good: "border-good/50 bg-good-dim/25",
    bad: "border-bad/50 bg-bad-dim/25",
  }[tone];
  return (
    <div className={cn("flex flex-col items-center gap-1 rounded-md border px-3 py-3 text-center", toneClass)}>
      <span className="text-[10.5px] font-medium uppercase tracking-wide text-text-tertiary">{label}</span>
      {children}
    </div>
  );
}
