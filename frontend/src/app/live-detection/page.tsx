import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { fmtNum } from "@/lib/utils";

export default async function LiveDetectionPage() {
  const [conditions, drift, gate] = await Promise.all([
    api.experimentsConditions(),
    api.driftEvents(),
    api.gateLog(),
  ]);

  if (!conditions.available) {
    return <EmptyState title="NO STREAM DATA" reason="No experiment run available." className="mt-20" />;
  }

  const closedLoop = conditions.conditions.closed_loop;
  const rows = closedLoop.macro_f1.map((f1, t) => {
    const driftEvent = drift.available ? drift.events.find((e) => e.timestep === t) : undefined;
    const gateEvents = gate.available ? gate.closed_loop_gate_log.filter((e) => e.step === t) : [];
    return { t, f1, drift: driftEvent, gateEvents };
  });

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold text-text-primary">Live Detection</h1>
        <Badge tone="idle" dot>
          no live traffic feed — replaying recorded stream
        </Badge>
      </div>

      <Panel>
        <PanelBody className="text-[12px] leading-relaxed text-text-tertiary">
          No live SDN traffic source is connected in this build (see Topology). What follows is a
          timestep-by-timestep replay of the closed-loop classifier&apos;s recorded performance on the
          simulated evaluation stream from the last experiment run — every value traces back to
          <span className="mono text-text-secondary"> results/results.pkl</span>.
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Detection Timeline — Closed-Loop Classifier" subtitle="Per-timestep macro-F1, drift firings, and gate decisions" />
        <PanelBody>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-[12px]">
              <thead>
                <tr className="border-b border-border-subtle text-left text-text-tertiary">
                  <th className="py-1.5 pr-4 font-medium">timestep</th>
                  <th className="py-1.5 pr-4 font-medium">macro-F1</th>
                  <th className="py-1.5 pr-4 font-medium">drift</th>
                  <th className="py-1.5 font-medium">gate activity</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.t} className="mono border-b border-border-subtle/60">
                    <td className="py-1.5 pr-4 text-text-primary">t={r.t}</td>
                    <td className="py-1.5 pr-4 text-text-secondary">{fmtNum(r.f1)}</td>
                    <td className="py-1.5 pr-4">
                      {r.drift?.fired ? (
                        <Badge tone="warn">fired · p={fmtNum(r.drift.p_value)}</Badge>
                      ) : (
                        <span className="text-text-disabled">—</span>
                      )}
                    </td>
                    <td className="py-1.5">
                      {r.gateEvents.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {r.gateEvents.map((g, i) => (
                            <Badge key={i} tone={g.admitted ? "good" : "bad"}>
                              MMD {fmtNum(g.mmd_score)}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <span className="text-text-disabled">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </PanelBody>
      </Panel>
    </div>
  );
}
