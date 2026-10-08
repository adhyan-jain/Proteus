import { research, isOk } from "@/lib/research";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { CiPlot } from "@/components/research/ci-plot";
import { armLabel, ciStr, fmtSec } from "@/lib/research-format";

export const dynamic = "force-dynamic";

export default async function AblationsPage() {
  const r = await research.p1();
  if (!isOk(r)) return <EmptyState title="P1 NOT RUN" reason={r.reason} />;
  const d = r.doc;
  const abl = Object.entries(d.ablations);
  const refs = Object.entries(d.references);
  const table = d.arm_table;
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-[15px] font-semibold text-text-primary">Ablations, negative controls and references</h1>
      <p className="max-w-4xl text-[12.5px] leading-relaxed text-text-secondary">
        Each ablation removes exactly one component of the controller. They are descriptive (paired differences with t-intervals, no hypothesis test): they show which parts the
        result depends on, not that any part “works”. References are upper bounds or reproductions and never carry a claim.
      </p>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Ablations vs the full controller (CTRL-SMOTE)" subtitle="Paired difference in R-recovery; negative = removing the component hurt" />
          <PanelBody><CiPlot axisLabel="R-recovery difference vs CTRL-SMOTE" rows={abl.map(([a, v]) => ({ label: armLabel(a), ci: v.vs_ctrl_smote.diff }))} /></PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Ablations vs real-only adaptation" subtitle="Does any variant of the controller beat simply adapting on real labels?" />
          <PanelBody><CiPlot axisLabel="R-recovery difference vs REAL_ONLY" rows={abl.map(([a, v]) => ({ label: armLabel(a), ci: v.vs_real_only.diff, color: "#9d7de8" }))} /></PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="References (never claims)" subtitle="All-labels positive control from P0; oracle dose is scored on the next window’s E and never deployed" />
        <PanelBody>
          <CiPlot axisLabel="R-recovery difference vs REAL_ONLY" rows={[
            ...refs.map(([a, v]) => ({ label: armLabel(a), ci: v.vs_real_only.diff, color: "#7ec9e0" })),
          ]} />
          <p className="mt-2 text-[11px] text-text-tertiary">
            Oracle best-fixed-dose candidate quality (R-recovery, matched windows): {ciStr(table.ORACLE_DOSE?.shadow_candidate)} · real-only candidate: {ciStr(table.REAL_ONLY?.shadow_real_only_candidate)}
          </p>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Cost" subtitle="Wall-clock and model fits per arm (all seeds, this machine)" />
        <PanelBody>
          <table className="mono w-full text-[11.5px]">
            <thead><tr className="text-left text-text-tertiary"><th className="pb-1 font-normal">arm</th><th className="font-normal">R-recovery [95% CI]</th><th className="font-normal">wall-clock</th><th className="font-normal">candidate fits</th><th className="font-normal">promotions</th></tr></thead>
            <tbody>
              {Object.entries(table).map(([a, t]) => (
                <tr key={a} className="border-t border-border-subtle text-text-secondary">
                  <td className="py-1 font-sans">{armLabel(a)} {t.promotions.canary_checks === 0 && a.startsWith("ABL-NO-CANARY") && <Badge tone="idle">no canary</Badge>}</td>
                  <td>{ciStr(t.r_recovery)}</td><td>{fmtSec(t.wall_clock_s)}</td><td>{t.candidate_fits}</td><td>{t.promotions.star + t.promotions.real_only}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PanelBody>
      </Panel>
    </div>
  );
}
