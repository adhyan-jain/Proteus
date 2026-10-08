import { Badge, type Tone } from "@/components/ui/badge";

// The four evidence labels used throughout the research docs, plus result states that are
// derived mechanically from artifacts (never typed in by hand).
export type EvidenceKind =
  | "PROVEN"
  | "IMPLEMENTED"
  | "HYPOTHESIS"
  | "FUTURE"
  | "SUPPORTED"
  | "NOT_SUPPORTED"
  | "NOT_RUN";

const MAP: Record<EvidenceKind, { text: string; tone: Tone }> = {
  PROVEN: { text: "PROVEN", tone: "good" },
  IMPLEMENTED: { text: "IMPLEMENTED · NOT YET VALIDATED", tone: "warn" },
  HYPOTHESIS: { text: "PROPOSED / HYPOTHESIS", tone: "network" },
  FUTURE: { text: "FUTURE WORK", tone: "idle" },
  SUPPORTED: { text: "TESTED · SUPPORTED", tone: "good" },
  NOT_SUPPORTED: { text: "TESTED · NOT SUPPORTED", tone: "bad" },
  NOT_RUN: { text: "NOT RUN", tone: "idle" },
};

export function EvidenceLabel({ kind, className }: { kind: EvidenceKind; className?: string }) {
  const m = MAP[kind];
  return (
    <Badge tone={m.tone} className={className}>
      {m.text}
    </Badge>
  );
}
