import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { fmtInt, fmtNum } from "@/lib/utils";

const STAGES = [
  "Drift Detected",
  "Recent Traffic Buffered",
  "Generator Resumed",
  "Samples Generated",
  "Fidelity Check",
  "Admitted Data",
  "Classifier Retrained",
  "Model Deployed",
];

export default async function AdaptationPage() {
  const adapt = await api.adaptationEvents();

  if (!adapt.available) {
    return <EmptyState title="NO ADAPTATION DATA" reason={adapt.reason} className="mt-20" />;
  }

  const successful = adapt.retrain_events.filter((e): e is Extract<typeof e, { f1_after: number }> => "f1_after" in e);
  const failed = adapt.retrain_events.filter((e) => "error" in e);
  const improved = successful.filter((e) => e.f1_after >= e.f1_before);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold text-text-primary">Adaptation / Retraining</h1>
        <Badge tone={successful.length > 0 ? "good" : "idle"}>
          {successful.length} retrain event{successful.length === 1 ? "" : "s"} this run
        </Badge>
      </div>

      <Panel>
        <PanelHeader title="Adaptation Mechanism" subtitle="Every drift firing walks this chain before a new model is deployed" />
        <PanelBody>
          <div className="flex flex-wrap items-center gap-1.5">
            {STAGES.map((s, i) => (
              <div key={s} className="flex items-center gap-1.5">
                <span className="rounded border border-border-default bg-surface-2 px-2.5 py-1.5 text-[11px] text-text-secondary">
                  {s}
                </span>
                {i < STAGES.length - 1 && (
                  <svg width="16" height="10" viewBox="0 0 16 10" className="text-text-disabled">
                    <line x1="0" y1="5" x2="10" y2="5" stroke="currentColor" strokeWidth="1.3" />
                    <path d="M9 1 L14 5 L9 9" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>
            ))}
          </div>
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Panel>
          <PanelBody>
            <div className="flex flex-col gap-1">
              <span className="text-[10.5px] font-medium uppercase tracking-wide text-text-tertiary">Retrains triggered</span>
              <span className="mono text-[20px] font-semibold text-text-primary">{fmtInt(adapt.retrain_events.length)}</span>
            </div>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <div className="flex flex-col gap-1">
              <span className="text-[10.5px] font-medium uppercase tracking-wide text-text-tertiary">Improved F1</span>
              <span className="mono text-[20px] font-semibold text-good">{fmtInt(improved.length)} / {fmtInt(successful.length)}</span>
            </div>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <div className="flex flex-col gap-1">
              <span className="text-[10.5px] font-medium uppercase tracking-wide text-text-tertiary">Failed retrains</span>
              <span className="mono text-[20px] font-semibold text-bad">{fmtInt(failed.length)}</span>
            </div>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelBody>
            <div className="flex flex-col gap-1">
              <span className="text-[10.5px] font-medium uppercase tracking-wide text-text-tertiary">Total samples admitted</span>
              <span className="mono text-[20px] font-semibold text-synthetic">
                {fmtInt(successful.reduce((s, e) => s + e.n_admitted, 0))}
              </span>
            </div>
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Before / After Macro-F1 per Retrain Event" subtitle="Measured on the same batch that triggered the retrain, immediately before and after" />
        <PanelBody>
          {successful.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] border-collapse text-[12px]">
                <thead>
                  <tr className="border-b border-border-subtle text-left text-text-tertiary">
                    <th className="py-1.5 pr-4 font-medium">timestep</th>
                    <th className="py-1.5 pr-4 font-medium">F1 before</th>
                    <th className="py-1.5 pr-4 font-medium">F1 after</th>
                    <th className="py-1.5 pr-4 font-medium">Δ</th>
                    <th className="py-1.5 font-medium">synthetic admitted</th>
                  </tr>
                </thead>
                <tbody>
                  {successful.map((e) => {
                    const delta = e.f1_after - e.f1_before;
                    return (
                      <tr key={e.timestep} className="mono border-b border-border-subtle/60">
                        <td className="py-1.5 pr-4 text-text-primary">t={e.timestep}</td>
                        <td className="py-1.5 pr-4 text-text-secondary">{fmtNum(e.f1_before)}</td>
                        <td className="py-1.5 pr-4 text-text-secondary">{fmtNum(e.f1_after)}</td>
                        <td className={`py-1.5 pr-4 font-semibold ${delta >= 0 ? "text-good" : "text-bad"}`}>
                          {delta >= 0 ? "+" : ""}
                          {fmtNum(delta)}
                        </td>
                        <td className="py-1.5 text-text-tertiary">{fmtInt(e.n_admitted)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState reason="No successful retrain events recorded." />
          )}
        </PanelBody>
      </Panel>

      {failed.length > 0 && (
        <Panel className="border-bad/40">
          <PanelHeader title="Failed Retrain Attempts" />
          <PanelBody className="flex flex-col gap-2">
            {failed.map((e) => (
              <div key={e.timestep} className="mono text-[12px] text-bad">
                t={e.timestep}: {"error" in e ? e.error : ""}
              </div>
            ))}
          </PanelBody>
        </Panel>
      )}
    </div>
  );
}
