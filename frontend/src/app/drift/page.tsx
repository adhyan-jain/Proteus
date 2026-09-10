import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { Stat } from "@/components/ui/stat";
import { DriftStatisticChart } from "@/components/charts/drift-statistic-chart";
import { fmtNum } from "@/lib/utils";

export default async function DriftPage() {
  const [drift, exp] = await Promise.all([api.driftEvents(), api.experimentsLatest()]);

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
          subtitle="Compares the closed-loop classifier's per-batch confidence distribution against a reference distribution captured on held-out test data. Bars below α (dashed) fire a drift event."
        />
        <PanelBody>
          <DriftStatisticChart events={drift.events} />
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader
          title="Drift Events"
          subtitle="Every timestep the detector fired, with the statistical evidence behind the decision"
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Drift Schedule (Injected)" subtitle="Timesteps where the simulated stream deliberately injected distribution shift" />
          <PanelBody>
            {exp.available ? (
              <div className="flex flex-wrap gap-2">
                {exp.drift_schedule.map((t) => (
                  <Badge key={t} tone="bad">
                    t={t}
                  </Badge>
                ))}
              </div>
            ) : (
              <EmptyState reason="No experiment run available." />
            )}
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Detection Method" />
          <PanelBody className="flex flex-col gap-2 text-[12px] text-text-secondary">
            <p>
              Proteus monitors the closed-loop classifier&apos;s prediction-confidence distribution over each
              incoming batch and compares it against a reference distribution captured on held-out test data
              using a two-sample Kolmogorov-Smirnov test.
            </p>
            <p>
              When the resulting p-value falls below α, the null hypothesis (same distribution) is rejected —
              Proteus concludes the traffic distribution has shifted and triggers the adaptation pipeline
              (generator resume → fidelity check → retrain).
            </p>
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}
