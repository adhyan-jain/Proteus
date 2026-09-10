import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { GateFlow } from "@/components/fidelity/gate-flow";
import { MmdHistoryChart } from "@/components/charts/mmd-history-chart";
import { fmtInt, fmtNum } from "@/lib/utils";

export default async function FidelityGatePage() {
  const gate = await api.gateLog();

  if (!gate.available) {
    return <EmptyState title="NO GATE DATA" reason={gate.reason} className="mt-20" />;
  }

  const allEntries = [...gate.static_gate_log, ...gate.closed_loop_gate_log];
  const latest = allEntries[allEntries.length - 1];
  const admittedCount = allEntries.filter((e) => e.admitted).length;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold text-text-primary">Fidelity Gate</h1>
        <Badge tone="network">{gate.method}</Badge>
      </div>

      <Panel>
        <PanelHeader
          title="Latest Admission Decision"
          subtitle="GENERATED BATCH → MMD TEST → THRESHOLD → ADMIT / REJECT"
        />
        <PanelBody>{latest ? <GateFlow entry={latest} threshold={gate.threshold} /> : <EmptyState reason="No gate decisions yet." />}</PanelBody>
      </Panel>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Panel>
          <PanelBody>
            <div className="flex flex-col gap-1">
              <span className="text-[10.5px] font-medium uppercase tracking-wide text-text-tertiary">Threshold</span>
              <span className="mono text-[20px] font-semibold text-text-primary">{fmtNum(gate.threshold)}</span>
            </div>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <div className="flex flex-col gap-1">
              <span className="text-[10.5px] font-medium uppercase tracking-wide text-text-tertiary">Total decisions</span>
              <span className="mono text-[20px] font-semibold text-text-primary">{fmtInt(allEntries.length)}</span>
            </div>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <div className="flex flex-col gap-1">
              <span className="text-[10.5px] font-medium uppercase tracking-wide text-text-tertiary">Admitted</span>
              <span className="mono text-[20px] font-semibold text-good">{fmtInt(admittedCount)}</span>
            </div>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <div className="flex flex-col gap-1">
              <span className="text-[10.5px] font-medium uppercase tracking-wide text-text-tertiary">Rejected</span>
              <span className="mono text-[20px] font-semibold text-bad">{fmtInt(allEntries.length - admittedCount)}</span>
            </div>
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader
          title="MMD Score History"
          subtitle="Maximum Mean Discrepancy between each generated batch and its real comparison window. Point size = batch size."
        />
        <PanelBody>
          <MmdHistoryChart entries={allEntries} threshold={gate.threshold} />
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Static-Augmentation Gate Log" subtitle="One-shot admission check before the stream begins" />
          <PanelBody>
            <GateTable entries={gate.static_gate_log} />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Closed-Loop Gate Log" subtitle="Admission checks triggered during the simulated stream" />
          <PanelBody>
            <GateTable entries={gate.closed_loop_gate_log} />
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}

function GateTable({ entries }: { entries: { step: number; mmd_score: number; admitted: boolean; n_samples: number }[] }) {
  if (entries.length === 0) return <EmptyState reason="No entries logged." />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[380px] border-collapse text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle text-left text-text-tertiary">
            <th className="py-1.5 pr-3 font-medium">step</th>
            <th className="py-1.5 pr-3 font-medium">MMD score</th>
            <th className="py-1.5 pr-3 font-medium">n samples</th>
            <th className="py-1.5 font-medium">decision</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => (
            <tr key={i} className="mono border-b border-border-subtle/60">
              <td className="py-1.5 pr-3 text-text-primary">{e.step}</td>
              <td className="py-1.5 pr-3 text-text-secondary">{fmtNum(e.mmd_score)}</td>
              <td className="py-1.5 pr-3 text-text-tertiary">{fmtInt(e.n_samples)}</td>
              <td className="py-1.5">
                <Badge tone={e.admitted ? "good" : "bad"}>{e.admitted ? "admit" : "reject"}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
