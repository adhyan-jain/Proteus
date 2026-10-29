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
          subtitle="Generated batch → MMD test → threshold → admit / reject"
          why="Before synthetic samples are used for training, this check measures how different they are from real traffic. Too different (above the threshold) means rejected."
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
          subtitle="MMD of each generated batch; lower is more realistic"
          why="Each point is one batch. Points under the threshold line were admitted, points above were rejected."
        />
        <PanelBody>
          <MmdHistoryChart entries={allEntries} threshold={gate.threshold} />
        </PanelBody>
      </Panel>

    </div>
  );
}
