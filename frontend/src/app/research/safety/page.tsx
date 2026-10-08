import { research, isOk } from "@/lib/research";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { Stat } from "@/components/ui/stat";
import { EmptyState } from "@/components/ui/empty-state";
import { CiPlot } from "@/components/research/ci-plot";
import { armLabel, fx } from "@/lib/research-format";

export const dynamic = "force-dynamic";
const EPS_S = 0.01;
const EPS_FPR = 0.005;

export default async function SafetyPage() {
  const r = await research.p1();
  if (!isOk(r)) return <EmptyState title="P1 NOT RUN" reason={r.reason} />;
  const d = r.doc;
  const h4 = d.hypotheses.H4;
  const arms = Object.keys(d.arm_table).filter((a) => !["FROZEN"].includes(a));
  const nc = Object.entries(d.negative_controls);
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[15px] font-semibold text-text-primary">Safety, stability, canary and rollback</h1>
        <Badge tone={h4.passed ? "good" : h4.safe_by_inaction ? "warn" : "bad"}>{h4.passed ? "H4 passed" : h4.safe_by_inaction ? "safe by inaction" : "envelope breached"}</Badge>
      </div>
      <p className="max-w-4xl text-[12.5px] leading-relaxed text-text-secondary">
        Safety is a constraint, not a weight. A promoted model must keep the stable-class macro-F1 drop ≤ ε_S = {EPS_S} and the benign false-positive-rate rise ≤ ε_FPR = {EPS_FPR} against the fixed anchor
        (UCB-tested at the gate); after promotion the canary re-checks it on labels that arrive later. “Safe by inaction” means no breach because (almost) nothing was ever promoted.
      </p>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Panel><PanelBody><Stat label="S_report breaches · CTRL-SMOTE" value={String(h4.s_report_breaches)} tone={h4.s_report_breaches ? "bad" : "good"} /><p className="mt-2 text-[11px] text-text-tertiary">held-out stable traffic, point estimate</p></PanelBody></Panel>
        <Panel><PanelBody><Stat label="seeds with a promoted synthetic candidate" value={`${h4.seeds_with_star_promotion}/${d.provenance.seeds_present.length}`} tone={h4.passed ? "good" : "warn"} /><p className="mt-2 text-[11px] text-text-tertiary">activity needs ≥ {h4.activity_required}/10</p></PanelBody></Panel>
        <Panel><PanelBody><Stat label="canary checks · rollbacks (CTRL-SMOTE)" value={`${d.arm_table["CTRL-SMOTE"].promotions.canary_checks} · ${d.arm_table["CTRL-SMOTE"].promotions.rollbacks}`} /><p className="mt-2 text-[11px] text-text-tertiary">F4 fires above 20% of promotions</p></PanelBody></Panel>
        <Panel><PanelBody><Stat label="pre-drift windows probed (NC5)" value={`${d.pre_drift_probe.windows}`} tone={d.pre_drift_probe.nonempty_region || d.pre_drift_probe.promoted ? "bad" : "good"} /><p className="mt-2 text-[11px] text-text-tertiary">non-empty region: {d.pre_drift_probe.nonempty_region} · promoted: {d.pre_drift_probe.promoted}</p></PanelBody></Panel>
      </div>

      <Panel>
        <PanelHeader title="Held-out stable-traffic cost of every deployed model" subtitle="Worst observed point estimates on S_report across seeds, vs the preregistered envelope. Only windows with a non-base model deployed are counted." />
        <PanelBody>
          <table className="mono w-full text-[11.5px]">
            <thead><tr className="text-left text-text-tertiary"><th className="pb-1 font-normal">arm</th><th className="font-normal">non-base windows</th><th className="font-normal">worst stable-F1 drop</th><th className="font-normal">worst benign-FPR rise</th><th className="font-normal">breaches</th><th className="font-normal">promotions (star / real)</th><th className="font-normal">canary checks / rollbacks</th></tr></thead>
            <tbody>
              {arms.map((a) => { const t = d.arm_table[a]; return (
                <tr key={a} className="border-t border-border-subtle text-text-secondary">
                  <td className="py-1 font-sans">{armLabel(a)}</td><td>{t.safety.nonbase_windows}</td>
                  <td className={t.safety.worst_stable_f1_drop > EPS_S ? "text-warn" : ""}>{fx(t.safety.worst_stable_f1_drop, 4)}</td>
                  <td className={t.safety.worst_benign_fpr_increase > EPS_FPR ? "text-warn" : ""}>{fx(t.safety.worst_benign_fpr_increase, 5)}</td>
                  <td className={t.safety.breaches ? "text-bad" : "text-good"}>{t.safety.breaches}</td>
                  <td>{t.promotions.star} / {t.promotions.real_only}</td><td>{t.promotions.canary_checks} / {t.promotions.rollbacks}</td>
                </tr>); })}
            </tbody>
          </table>
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Negative controls vs real-only" subtitle="Wrong-class, Gaussian and shuffled rows, and a placebo dose. A control that beats real-only would mean gains are not class-specific." />
          <PanelBody>
            {nc.length ? <CiPlot axisLabel="R-recovery difference vs REAL_ONLY" rows={nc.map(([a, v]) => ({ label: armLabel(a), ci: v.diff, color: v.beats_real_only ? "#e2555a" : "#5a6270" }))} /> : <EmptyState reason="no controls in artifact" />}
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Leakage and reconciliation" subtitle="V1 audit on every arm; P1 replay of the frozen P0 real-only decision" />
          <PanelBody className="flex flex-col gap-2 text-[12px] text-text-secondary">
            <div className="flex items-center justify-between"><span>V1 violations (all arms, all seeds)</span><Badge tone={Object.values(d.provenance.v1_violations).every((v) => v === 0) ? "good" : "bad"}>{Object.values(d.provenance.v1_violations).reduce((a, b) => a + b, 0)}</Badge></div>
            <div className="flex items-center justify-between"><span>P1 manifests of seeds 0–4 equal P0’s</span><Badge tone={Object.values(d.provenance.manifest_matches_p0).filter((v) => v !== null).every(Boolean) ? "good" : "bad"}>{Object.values(d.provenance.manifest_matches_p0).filter((v) => v !== null).filter(Boolean).length}/{Object.values(d.provenance.manifest_matches_p0).filter((v) => v !== null).length}</Badge></div>
            <div className="flex items-center justify-between"><span>real-only (no canary) reproduces frozen P0 REAL_ONLY step-for-step</span><Badge tone={d.p0_reconciliation.identical ? "good" : "bad"}>{d.p0_reconciliation.identical ? `identical · seeds ${d.p0_reconciliation.seeds.join(",")}` : `${d.p0_reconciliation.problems.length} differences`}</Badge></div>
            <p className="text-[11px] text-text-tertiary">{d.p0_reconciliation.note}</p>
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}
