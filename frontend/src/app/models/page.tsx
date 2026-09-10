import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { Stat } from "@/components/ui/stat";
import { ClassDistributionChart } from "@/components/charts/class-distribution-chart";
import { fmtInt } from "@/lib/utils";

export default async function ModelsPage() {
  const [models, datasets] = await Promise.all([api.models(), api.datasetsSummary()]);

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-[15px] font-semibold text-text-primary">Models & Datasets</h1>

      <Panel>
        <PanelHeader title="Demo-Scale Model" subtitle="Trained inside the single results.pkl experiment run" />
        <PanelBody>
          {models.demo_model ? (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat label="Trained on" value={models.demo_model.trained_on} />
              <Stat label="Features" value={fmtInt(models.demo_model.n_features)} />
              <Stat label="Classes" value={String(models.demo_model.class_names.length)} />
              <Stat label="Conditions trained" value={models.demo_model.conditions_trained.join(", ")} />
            </div>
          ) : (
            <EmptyState reason="No demo model trained yet." />
          )}
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Full-Scale Model (CICIDS2017/InSDN)" />
          <PanelBody>
            <EmptyState title="NOT AVAILABLE" reason={models.full_scale_model.reason} />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="InSDN-Trained Model" />
          <PanelBody>
            <EmptyState title="NOT AVAILABLE" reason={models.insdn_model.reason} />
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader
          title="Datasets"
          subtitle="Precomputed from proteus/data_full.py — full class distributions, row counts, and provenance"
        />
        <PanelBody>
          {datasets.available ? (
            <div className="flex flex-col gap-8">
              {datasets.datasets.map((d) => (
                <div key={d.name} className="flex flex-col gap-3">
                  <div className="flex items-center justify-between">
                    <h4 className="mono text-[12px] font-semibold text-text-primary">{d.name}</h4>
                    <Badge tone={d.available ? "good" : "bad"}>{d.available ? "loaded" : "unavailable"}</Badge>
                  </div>
                  {d.available ? (
                    <>
                      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                        <Stat label="Total rows" value={fmtInt(d.n_rows_total)} />
                        <Stat label="Features" value={fmtInt(d.n_features)} />
                        <Stat
                          label="Split (train/val/test)"
                          value={`${fmtInt(d.split_sizes?.train)} / ${fmtInt(d.split_sizes?.val)} / ${fmtInt(d.split_sizes?.test)}`}
                        />
                        <Stat label="Load time" value={`${d.load_seconds ?? "—"} s`} />
                      </div>
                      {d.class_distribution && <ClassDistributionChart distribution={d.class_distribution} />}
                    </>
                  ) : (
                    <EmptyState reason={d.error ?? "Dataset unavailable."} />
                  )}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="NOT PRECOMPUTED"
              reason={(datasets as { reason: string }).reason}
            />
          )}
        </PanelBody>
      </Panel>
    </div>
  );
}
