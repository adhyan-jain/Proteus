import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { fmtNum } from "@/lib/utils";
import type { AdaptationEvents, DriftEvents, GateLog } from "@/lib/api";

type Event = {
  timestep: number;
  kind: "drift" | "gate" | "retrain";
  tone: "bad" | "warn" | "good" | "network";
  text: string;
};

export function EventStream({
  drift,
  gate,
  adapt,
}: {
  drift: DriftEvents;
  gate: GateLog;
  adapt: AdaptationEvents;
}) {
  const events: Event[] = [];

  if (drift.available) {
    for (const e of drift.events) {
      if (e.fired) {
        events.push({
          timestep: e.timestep,
          kind: "drift",
          tone: "warn",
          text: `Drift detected — KS statistic ${fmtNum(e.statistic)}, p=${fmtNum(e.p_value)} (α=${e.alpha})`,
        });
      }
    }
  }
  if (gate.available) {
    for (const e of gate.closed_loop_gate_log) {
      events.push({
        timestep: e.step,
        kind: "gate",
        tone: e.admitted ? "good" : "bad",
        text: `Fidelity gate ${e.admitted ? "admitted" : "rejected"} batch — MMD ${fmtNum(e.mmd_score)}, n=${e.n_samples}`,
      });
    }
  }
  if (adapt.available) {
    for (const e of adapt.retrain_events) {
      if ("error" in e) {
        events.push({ timestep: e.timestep, kind: "retrain", tone: "bad", text: `Retrain failed — ${e.error}` });
      } else {
        events.push({
          timestep: e.timestep,
          kind: "retrain",
          tone: "network",
          text: `Closed-loop retrain — macro-F1 ${fmtNum(e.f1_before)} → ${fmtNum(e.f1_after)}, ${e.n_admitted} synthetic samples admitted`,
        });
      }
    }
  }

  events.sort((a, b) => a.timestep - b.timestep);

  if (events.length === 0) {
    return <EmptyState reason="No drift, gate, or retrain events recorded in this run." />;
  }

  return (
    <ol className="flex flex-col divide-y divide-border-subtle">
      {events
        .slice()
        .reverse()
        .map((e, i) => (
          <li key={i} className="flex items-center gap-3 py-2">
            <span className="mono w-10 shrink-0 text-[11px] text-text-disabled">t={e.timestep}</span>
            <Badge tone={e.tone} dot className="shrink-0">
              {e.kind}
            </Badge>
            <span className="text-[12px] text-text-secondary">{e.text}</span>
          </li>
        ))}
    </ol>
  );
}
