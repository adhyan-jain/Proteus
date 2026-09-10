import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { OverviewMacroF1Chart } from "@/components/charts/overview-macro-f1-chart";
import { PerClassF1Chart } from "@/components/charts/per-class-f1-chart";
import { ReportTable } from "@/components/experiments/report-table";
import { fmtNum } from "@/lib/utils";

const CONDITION_LABEL: Record<string, string> = {
  baseline: "Baseline",
  static_augmentation: "Static Augmentation",
  closed_loop: "Closed-Loop (Proteus)",
};

export default async function ExperimentsPage() {
  const [conditions, finalReports, exp] = await Promise.all([
    api.experimentsConditions(),
    api.experimentsFinalReports(),
    api.experimentsLatest(),
  ]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold text-text-primary">Experiments</h1>
        <Badge tone="idle">single-seed run — no confidence intervals available</Badge>
      </div>

      <Panel>
        <PanelHeader
          title="Macro-F1 Over Time"
          subtitle="Baseline vs. static augmentation vs. closed-loop, on the identical simulated stream. Dashed red = drift-injected timestep, dashed violet = closed-loop retrain."
        />
        <PanelBody>
          {conditions.available ? (
            <OverviewMacroF1Chart conditions={conditions} />
          ) : (
            <EmptyState reason={conditions.available ? "" : (conditions as { reason: string }).reason} />
          )}
        </PanelBody>
      </Panel>

      {conditions.available && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {Object.entries(conditions.conditions).map(([name, series]) => (
            <Panel key={name}>
              <PanelHeader title={CONDITION_LABEL[name] ?? name} subtitle="Per-class F1 over time" />
              <PanelBody>
                <PerClassF1Chart
                  perClassF1={series.per_class_f1}
                  classNames={conditions.class_names}
                  driftSchedule={conditions.drift_schedule}
                />
              </PanelBody>
            </Panel>
          ))}
        </div>
      )}

      <Panel>
        <PanelHeader
          title="Final Held-Out Classification Reports"
          subtitle="Precision / recall / F1 / support per class, evaluated once at the end of each condition's run"
        />
        <PanelBody>
          {finalReports.available ? (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              {Object.entries(finalReports.final_reports).map(([name, report]) => (
                <div key={name}>
                  <h4 className="mb-2 text-[11.5px] font-semibold text-text-secondary">
                    {CONDITION_LABEL[name] ?? name}
                    {"macro avg" in report && (
                      <span className="mono ml-2 text-text-tertiary">
                        macro-F1 {fmtNum(report["macro avg"]?.["f1-score"])}
                      </span>
                    )}
                  </h4>
                  <ReportTable report={report} classNames={finalReports.class_names} />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState reason="No final classification reports available." />
          )}
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel>
          <PanelHeader title="Inference Latency" />
          <PanelBody>
            <EmptyState
              title="NOT AVAILABLE"
              reason="The demo pipeline does not instrument per-request inference latency. Would require timing instrumentation in proteus/pipeline.py."
            />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Controller CPU" />
          <PanelBody>
            <EmptyState
              title="NOT AVAILABLE"
              reason="No live Ryu controller is deployed in this build — CPU telemetry has no source yet."
            />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Confidence Intervals" />
          <PanelBody>
            <EmptyState
              title="NOT AVAILABLE"
              reason={`This run is single-seed (data source: ${exp.available ? exp.data_source : "unknown"}). Confidence intervals require multi-seed reruns, which haven't been executed.`}
            />
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}
