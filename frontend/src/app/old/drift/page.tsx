import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { Stat } from "@/components/ui/stat";
import { DriftStatisticChart } from "@/components/charts/drift-statistic-chart";
import { fmtNum } from "@/lib/utils";

export default async function DriftPage() {
  const drift = await api.driftEvents();

  if (!drift.available) {
    return <EmptyState title="NO DRIFT DATA" reason={drift.reason} className="mt-20" />;
  }

  const lastEvent = drift.events[drift.events.length - 1];
  const firedCount = drift.events.filter((e) => e.fired).length;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold text-text-primary">Drift Monitor</h1>
        <Badge tone="network">{drift.method}</Badge>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Panel>
          <PanelBody>
            <Stat
              label="Current statistic"
              value={fmtNum(lastEvent.statistic)}
              tone={lastEvent.fired ? "bad" : "good"}
            />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <Stat label="Significance (α)" value={fmtNum(lastEvent.alpha)} />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <Stat label="p-value (last)" value={fmtNum(lastEvent.p_value)} tone={lastEvent.fired ? "bad" : "good"} />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <Stat label="Firings this run" value={`${firedCount} / ${drift.events.length}`} tone={firedCount > 0 ? "warn" : "good"} />
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader
          title="Two-Sample Kolmogorov-Smirnov Test — Confidence Distribution Drift"
          subtitle="Each bar is one timestep; bars under the dashed α line fire drift"
          why="Tests whether the classifier's confidence on new traffic still looks like its confidence on clean test data. A significant difference means the traffic has shifted, so the model should be retrained."
        />
        <PanelBody>
          <DriftStatisticChart events={drift.events} />
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader
          title="Drift Events"
          subtitle="Only the timesteps where drift fired"
          why="The statistical evidence behind each retrain: a small p-value (below α) is why the loop acted at that step."
        />
        <PanelBody>
          {drift.events.some((e) => e.fired) ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] border-collapse text-[12px]">
                <thead>
                  <tr className="border-b border-border-subtle text-left text-text-tertiary">
                    <th className="py-1.5 pr-4 font-medium">timestep</th>
                    <th className="py-1.5 pr-4 font-medium">KS statistic</th>
                    <th className="py-1.5 pr-4 font-medium">p-value</th>
                    <th className="py-1.5 pr-4 font-medium">α</th>
                    <th className="py-1.5 font-medium">outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {drift.events
                    .filter((e) => e.fired)
                    .map((e) => (
                      <tr key={e.timestep} className="mono border-b border-border-subtle/60">
                        <td className="py-1.5 pr-4 text-text-primary">t={e.timestep}</td>
                        <td className="py-1.5 pr-4 text-text-secondary">{fmtNum(e.statistic)}</td>
                        <td className="py-1.5 pr-4 text-text-secondary">{fmtNum(e.p_value)}</td>
                        <td className="py-1.5 pr-4 text-text-tertiary">{fmtNum(e.alpha)}</td>
                        <td className="py-1.5">
                          <Badge tone="warn">drift fired → retrain triggered</Badge>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState reason="No drift events fired during this run." />
          )}
        </PanelBody>
      </Panel>
    </div>
  );
}
