import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { Stat } from "@/components/ui/stat";
import { GanLossChart } from "@/components/charts/gan-loss-chart";
import { fmtInt, fmtNum } from "@/lib/utils";

export default async function SyntheticLabPage() {
  const [gan, gate, exp] = await Promise.all([api.ganLoss(), api.gateLog(), api.experimentsLatest()]);

  if (!gan.available) {
    return <EmptyState title="NO GAN DATA" reason={gan.reason} className="mt-20" />;
  }

  const lastLoss = gan.loss_log[gan.loss_log.length - 1];
  const totalGenerated = gate.available
    ? [...gate.static_gate_log, ...gate.closed_loop_gate_log].reduce((s, e) => s + e.n_samples, 0)
    : 0;
  const totalAdmitted = gate.available
    ? [...gate.static_gate_log, ...gate.closed_loop_gate_log].filter((e) => e.admitted).reduce((s, e) => s + e.n_samples, 0)
    : 0;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold text-text-primary">Synthetic Lab — WGAN-GP</h1>
        <Badge tone={gan.degraded ? "bad" : "synthetic"} dot>
          {gan.degraded ? "generator degraded" : "generator / critic trained"}
        </Badge>
      </div>

      {gan.degraded && (
        <Panel className="border-bad/40">
          <PanelBody>
            <p className="text-[12px] text-bad">Training error: {gan.error}</p>
          </PanelBody>
        </Panel>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Panel>
          <PanelBody>
            <Stat label="Training steps logged" value={fmtInt(gan.loss_log.length)} tone="synthetic" />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <Stat label="Generator loss (last)" value={lastLoss ? fmtNum(lastLoss.g_loss) : "—"} tone="synthetic" />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <Stat label="Critic loss (last)" value={lastLoss ? fmtNum(lastLoss.d_loss) : "—"} tone="network" />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <Stat label="Target rare classes" value={gan.rare_classes.join(", ")} />
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader
          title="Generator / Critic Loss"
          subtitle="Training progress of the synthetic-attack generator"
          why="The generator learns to make fake attack records and the critic learns to tell them from real ones. Losses that settle (not diverging) mean training is stable."
        />
        <PanelBody>
          <GanLossChart lossLog={gan.loss_log} />
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Synthetic Sample Throughput" why="How many fake samples were made and how many passed the quality gate. 0% admitted means none were trusted enough to train on." />
          <PanelBody className="flex flex-col gap-4">
            <Stat label="Total samples generated" value={fmtInt(totalGenerated)} tone="synthetic" />
            <Stat label="Total admitted by fidelity gate" value={fmtInt(totalAdmitted)} tone="good" />
            <Stat
              label="Admission rate"
              value={totalGenerated > 0 ? `${((totalAdmitted / totalGenerated) * 100).toFixed(1)}%` : "—"}
            />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Rare-Class Context" why="Rare attack types have too few real examples, so the generator targets them." />
          <PanelBody className="flex flex-col gap-2 text-[12px] text-text-secondary">
            <p>
              Classes below {exp.available ? "3%" : ""} of the training distribution (with at least 5 samples)
              are flagged as rare and become the WGAN-GP&apos;s generation targets.
            </p>
            {exp.available && (
              <ul className="mono flex flex-col gap-1 text-text-tertiary">
                {gan.rare_classes.map((c) => (
                  <li key={c}>
                    {c}: {fmtInt(exp.class_distribution[c])} training samples
                  </li>
                ))}
              </ul>
            )}
          </PanelBody>
        </Panel>
      </div>

      {gan.degraded && (
        <Panel>
          <PanelHeader title="Generator degraded" />
          <PanelBody>
            <EmptyState title="GENERATOR DEGRADED" reason={gan.error ?? "Training raised an exception."} />
          </PanelBody>
        </Panel>
      )}
    </div>
  );
}
