import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { OverviewMacroF1Chart } from "@/components/charts/overview-macro-f1-chart";
import { ReportTable } from "@/components/experiments/report-table";
import { fmtNum } from "@/lib/utils";

const CONDITION_LABEL: Record<string, string> = {
  baseline: "Baseline",
  static_augmentation: "Static Augmentation",
  closed_loop: "Closed-Loop (Proteus)",
};

export default async function ExperimentsPage() {
  const [conditions, finalReports] = await Promise.all([
    api.experimentsConditions(),
    api.experimentsFinalReports(),
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
          subtitle="Three strategies on the same simulated stream"
          why="Compares doing nothing (baseline), one-off synthetic augmentation (static) and the adaptive loop (closed-loop). Dashed red = drift injected, dashed violet = retrain."
        />
        <PanelBody>
          {conditions.available ? (
            <OverviewMacroF1Chart conditions={conditions} />
          ) : (
            <EmptyState reason={conditions.available ? "" : (conditions as { reason: string }).reason} />
          )}
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader
          title="Final Held-Out Classification Reports"
          subtitle="Per-class scores at the end of each run"
          why="Shows which attack classes each strategy still gets wrong. Low recall on a rare class means attacks of that type slip through."
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

    </div>
  );
}
