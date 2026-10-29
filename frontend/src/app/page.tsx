import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { Stat } from "@/components/ui/stat";
import { EmptyState } from "@/components/ui/empty-state";
import { PipelineDiagram, type Stage, type StageState } from "@/components/pipeline/pipeline-diagram";
import { fmtInt, fmtNum } from "@/lib/utils";
import { OverviewMacroF1Chart } from "@/components/charts/overview-macro-f1-chart";
import { EventStream } from "@/components/overview/event-stream";

export default async function OverviewPage() {
  const [exp, drift, gan, gate, adapt, conditions, metrics] = await Promise.all([
    api.experimentsLatest(),
    api.driftEvents(),
    api.ganLoss(),
    api.gateLog(),
    api.adaptationEvents(),
    api.experimentsConditions(),
    api.metricsFinal(),
  ]);

  if (!exp.available) {
    return (
      <div className="mx-auto max-w-2xl pt-20">
        <EmptyState
          title="NO EXPERIMENT RUN"
          reason="results/results.pkl was not found. Run `.venv/bin/python run_pipeline.py` from the repo root, then reload."
        />
      </div>
    );
  }

  const lastDrift = drift.available ? drift.events[drift.events.length - 1] : null;
  const anyDriftFired = drift.available ? drift.events.some((e) => e.fired) : false;
  const lastGateEntry =
    gate.available && gate.closed_loop_gate_log.length > 0
      ? gate.closed_loop_gate_log[gate.closed_loop_gate_log.length - 1]
      : null;
  const lastRetrain =
    adapt.available && adapt.retrain_events.length > 0
      ? adapt.retrain_events[adapt.retrain_events.length - 1]
      : null;
  const lastRetrainOk = lastRetrain && "f1_after" in lastRetrain ? lastRetrain : null;
  const closedLoopF1 = conditions.available ? conditions.conditions.closed_loop?.macro_f1 : undefined;
  const finalClosedLoopF1 = closedLoopF1 ? closedLoopF1[closedLoopF1.length - 1] : undefined;

  const ganState: StageState = exp.gan_degraded ? "failed" : "completed";
  const driftState: StageState = anyDriftFired ? "warning" : "completed";
  const gateState: StageState = lastGateEntry ? (lastGateEntry.admitted ? "completed" : "warning") : "idle";
  const retrainState: StageState = lastRetrainOk ? "completed" : "idle";

  const stages: Stage[] = [
    {
      id: "traffic",
      label: "Live SDN Traffic",
      detail: "No live controller connected. Recorded Mininet/Ryu testbed runs are shown under Topology and Controller Telemetry.",
      state: "unavailable",
    },
    {
      id: "ingestion",
      label: "Flow Ingestion",
      detail: `Simulated stream: ${exp.n_timesteps} timesteps from ${exp.data_source}.`,
      state: "completed",
    },
    {
      id: "classify",
      label: "IDS Classification",
      detail: metrics.available
        ? `Baseline held-out macro-F1 ${fmtNum(metrics.macro_f1)}.`
        : "Awaiting baseline evaluation.",
      state: metrics.available ? "completed" : "idle",
    },
    {
      id: "drift",
      label: "Drift Detection",
      detail: lastDrift
        ? `KS statistic ${fmtNum(lastDrift.statistic)}, p=${fmtNum(lastDrift.p_value)} at t=${lastDrift.timestep}.`
        : "Awaiting drift events.",
      state: driftState,
    },
    {
      id: "gan",
      label: "WGAN-GP Generation",
      detail: exp.gan_degraded
        ? `Degraded: ${exp.gan_error ?? "generator training failed"}.`
        : gan.available
        ? `${gan.loss_log.length} training steps logged over rare classes: ${exp.rare_classes.join(", ")}.`
        : "No loss log.",
      state: ganState,
    },
    {
      id: "gate",
      label: "Fidelity Gate",
      detail: lastGateEntry
        ? `MMD ${fmtNum(lastGateEntry.mmd_score)} vs threshold 0.25 — ${
            lastGateEntry.admitted ? "admitted" : "rejected"
          }.`
        : "No gate decisions logged yet.",
      state: gateState,
    },
    {
      id: "retrain",
      label: "Closed-Loop Retraining",
      detail: lastRetrainOk
        ? `F1 ${fmtNum(lastRetrainOk.f1_before)} → ${fmtNum(lastRetrainOk.f1_after)}, ${lastRetrainOk.n_admitted} synthetic samples admitted.`
        : "No retrain triggered yet.",
      state: retrainState,
    },
    {
      id: "deploy",
      label: "Model Redeployment",
      detail: lastRetrainOk
        ? "Retrained closed-loop classifier is the active model for the next timestep."
        : "No redeployment has occurred.",
      state: lastRetrainOk ? "completed" : "idle",
    },
  ];

  const systemState = exp.gan_degraded
    ? { label: "GAN DEGRADED", tone: "bad" as const }
    : anyDriftFired
    ? { label: "ADAPTING TO DRIFT", tone: "warn" as const }
    : { label: "OPERATIONAL", tone: "good" as const };

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded border border-warn/40 bg-warn-dim/20 px-4 py-2.5 text-[12px] text-text-secondary">
        <strong className="text-warn">DEMO SCALE.</strong> Single-seed console. Its “closed-loop vs baseline” gain is driven by oracle labels on
        most of every window and is <strong>not</strong> evidence that synthetic data helps.
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-[15px] font-semibold text-text-primary">System Overview</h1>
          <Badge tone={systemState.tone} dot>
            {systemState.label}
          </Badge>
        </div>
        <span className="mono text-[11px] text-text-tertiary">
          data source: {exp.data_source} · {fmtInt(exp.n_features)} features · single-seed run
        </span>
      </div>

      <Panel>
        <PanelHeader
          title="Closed-Loop Pipeline"
          subtitle="Traffic → classify → detect drift → generate → gate → retrain → redeploy"
          why="The loop the system runs when traffic changes. Green stages ran in this demo run, amber stages need attention, grey stages have no live source."
        />
        <PanelBody>
          <PipelineDiagram stages={stages} />
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <Panel className="lg:col-span-1">
          <PanelHeader title="Detector Performance" why="Baseline is the classifier before any drift. Closed-loop is the same classifier after the loop retrained it; the gap shows whether adapting helped." />
          <PanelBody className="flex flex-col gap-4">
            <Stat label="Baseline macro-F1" value={metrics.available ? fmtNum(metrics.macro_f1) : "—"} tone="network" />
            <Stat
              label="Closed-loop macro-F1 (final)"
              value={finalClosedLoopF1 !== undefined ? fmtNum(finalClosedLoopF1) : "—"}
              tone="good"
            />
            <Stat label="Rare classes tracked" value={exp.rare_classes.join(", ") || "none"} />
          </PanelBody>
        </Panel>

        <Panel className="lg:col-span-3">
          <PanelHeader
            title="Macro-F1 Over Time — Baseline vs. Closed-Loop"
            subtitle="Simulated stream, drift marked"
            why="Quality (macro-F1) at each timestep. A dip after a dashed line is the model degrading when the traffic shifts; recovery is the adaptation working."
          />
          <PanelBody>
            {conditions.available ? (
              <OverviewMacroF1Chart conditions={conditions} />
            ) : (
              <EmptyState reason="No per-timestep condition data available." />
            )}
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Latest Events" why="The last few things the loop did: drift detected, synthetic batch accepted or rejected, model retrained. Full list is in Audit Log." />
        <PanelBody>
          <EventStream drift={drift} gate={gate} adapt={adapt} limit={5} />
        </PanelBody>
      </Panel>
    </div>
  );
}
