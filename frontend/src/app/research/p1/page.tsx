import { research, isOk, type Hypothesis } from "@/lib/research";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { CiPlot } from "@/components/research/ci-plot";
import { CurvesChart } from "@/components/research/curves-chart";
import { EvidenceLabel } from "@/components/research/evidence-label";
import { armLabel, ciStr, fx } from "@/lib/research-format";

export const dynamic = "force-dynamic";

const FLAG_TEXT: Record<string, string> = {
  F2_H2_not_rejected: "F2 · H2 lower bound ≤ 0: no measurable recovery beyond real-only adaptation",
  F3a_H3a_not_rejected: "F3a · not better than plain duplication",
  F3b_H3b_not_rejected: "F3b · not better than a decision-threshold shift",
  F4_unsafe_or_rollbacks: "F4 · S_report envelope breach or rollbacks > 20% of promotions",
  F5_established_inferior_to_fixed: "F5 · established worse than a fixed dose",
  F8_degenerate_controller: "F8 · controller degenerate (k = 0 in > 80% of runs with a need)",
  F9_ambiguity_bound: "F9 · the GO is explained by ambiguous (contradictory-label) rows",
  F10_certification_bottleneck: "F10 · better candidates exist but cannot be certified",
  F11_negative_control_beats_real_only: "F11 · a negative control beats real-only",
};

const COLORS: Record<string, string> = {
  FROZEN: "#5a6270", REAL_ONLY: "#3ecf8e", "CTRL-SMOTE": "#9d7de8", "CTRL-THRESH": "#e0a63e",
  "CTRL-ROS": "#4fb3d9", "FIXED-SMOTE-4": "#e08fc0", REAL_ONLY_ALL_LABELS: "#7ec9e0",
};

function HypRow({ name, h, gate }: { name: string; h: Hypothesis; gate?: boolean }) {
  const tested = gate === undefined ? true : gate;
  return (
    <tr className="border-t border-border-subtle align-top">
      <td className="py-2 pr-3 text-text-primary">{name}</td>
      <td className="pr-3 text-text-secondary">{h.contrast}</td>
      <td className="mono pr-3">{ciStr(h.diff)}</td>
      <td>{!tested ? <Badge tone="idle">not tested · sequence stopped</Badge> : h.rejected ? <Badge tone="good">null rejected</Badge> : <Badge tone="warn">null not rejected</Badge>}</td>
    </tr>
  );
}

export default async function P1Page() {
  const r = await research.p1();
  if (!isOk(r)) return <EmptyState title="P1 NOT RUN" reason={r.reason} />;
  const d = r.doc;
  const h = d.hypotheses;
  const nSeeds = d.provenance.seeds_present.length;
  const main = ["REAL_ONLY", "CTRL-ROS", "CTRL-THRESH", "CTRL-SMOTE", "FIXED-SMOTE-1", "FIXED-SMOTE-4", "ALWAYS-SMOTE", "FIDGATE-SMOTE"];
  const nWin = d.curves_r_f1_by_post_window.REAL_ONLY.mean.length;
  const curveArms = ["FROZEN", "REAL_ONLY", "CTRL-SMOTE", "CTRL-THRESH", "FIXED-SMOTE-4", "REAL_ONLY_ALL_LABELS"];
  const pairs = ["REAL_ONLY", "CTRL-SMOTE", "CTRL-THRESH", "FIXED-SMOTE-4"].filter((a) => d.arm_table[a]);
  const nPre = 4;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[15px] font-semibold text-text-primary">P1 · preregistered hypotheses</h1>
        <EvidenceLabel kind={h.H2.rejected ? "SUPPORTED" : "NOT_SUPPORTED"} />
        <Badge tone={d.provenance.complete ? "good" : "bad"}>{nSeeds}/10 seeds {d.provenance.complete ? "complete" : "INCOMPLETE"}</Badge>
        <Badge tone={d.provenance.all_preregistered ? "good" : "warn"}>{d.provenance.all_preregistered ? "preregistered configuration" : "not preregistered"}</Badge>
      </div>
      <p className="max-w-4xl text-[12.5px] leading-relaxed text-text-secondary">
        Scenario S1, B={d.budget} labels/window, oracle trigger, paired seeds. Primary endpoint: <strong>R-recovery</strong>, the mean E-F1 of the repairable classes
        ({d.provenance.repairable_set_names.join(", ")}) of the <em>deployed</em> model over post-drift windows. Hypotheses are tested as a fixed sequence: a test is made
        only if the previous one rejected its null. Intervals are two-sided 95% t-intervals over {nSeeds} paired seeds.
      </p>

      <Panel>
        <PanelHeader title="Fixed-sequence tests" subtitle="H2 → H3a → H3b → H5; H4 (safety) is a separate family" />
        <PanelBody>
          <table className="w-full text-[12px]">
            <thead><tr className="text-left text-[10.5px] uppercase tracking-wide text-text-tertiary"><th className="pb-1 font-medium">test</th><th className="font-medium">contrast</th><th className="font-medium">paired difference [95% CI]</th><th className="font-medium">result</th></tr></thead>
            <tbody>
              <HypRow name="H2 · beats real-only" h={h.H2} />
              <HypRow name="H3a · not just duplication" h={h.H3a} gate={h.H3a.tested_under_sequence} />
              <HypRow name="H3b · not just a threshold shift" h={h.H3b} gate={h.H3b.tested_under_sequence} />
              {Object.entries(h.H5.per_fixed).map(([a, v]) => (
                <tr key={a} className="border-t border-border-subtle align-top">
                  <td className="py-2 pr-3 text-text-primary">H5 · non-inferior to {a}</td>
                  <td className="pr-3 text-text-secondary">CTRL-SMOTE − {a}</td>
                  <td className="mono pr-3">{ciStr(v.diff)}</td>
                  <td>{!h.H5.tested_under_sequence ? <Badge tone="idle">not tested · sequence stopped</Badge> : v.noninferior ? <Badge tone="good">non-inferior (LB ≥ −ε_ni)</Badge> : <Badge tone="warn">not established</Badge>}{v.established_inferior && <Badge tone="bad" className="ml-1">established inferior</Badge>}</td>
                </tr>
              ))}
              <tr className="border-t border-border-subtle align-top">
                <td className="py-2 pr-3 text-text-primary">H4 · safety + activity</td>
                <td className="pr-3 text-text-secondary">controller + SMOTE</td>
                <td className="mono pr-3">{h.H4.s_report_breaches} S_report breaches · star branch promoted in {h.H4.seeds_with_star_promotion}/{nSeeds} seeds (need ≥{h.H4.activity_required}/10)</td>
                <td>{h.H4.passed ? <Badge tone="good">passed</Badge> : h.H4.safe_by_inaction ? <Badge tone="warn">safe by inaction</Badge> : <Badge tone="bad">breach</Badge>}</td>
              </tr>
            </tbody>
          </table>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Every arm against real-only adaptation" subtitle="Paired per-seed difference in R-recovery (deployed); zero line = no difference" />
        <PanelBody>
          <CiPlot axisLabel="R-recovery difference vs REAL_ONLY"
            rows={main.filter((a) => a !== "REAL_ONLY" && d.main_arms_vs_real_only[a]).map((a) => ({
              label: armLabel(a), ci: d.main_arms_vs_real_only[a].diff, color: COLORS[a] ?? "#4fb3d9", bold: a === "CTRL-SMOTE" }))} />
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Recovery by post-drift window" subtitle="Mean over seeds of the repairable-class F1 on the held-out reporting rows E_t (deployed model)" />
        <PanelBody>
          <CurvesChart firstWindow={nPre + 1}
            curves={curveArms.filter((a) => d.curves_r_f1_by_post_window[a]).map((a) => ({
              name: a, label: armLabel(a), mean: d.curves_r_f1_by_post_window[a].mean, color: COLORS[a] ?? "#4fb3d9", dashed: a === "REAL_ONLY_ALL_LABELS" }))} />
          <p className="mt-2 text-[11px] text-text-tertiary">{nWin} windows scored. The dashed line is the all-labels positive control (a reference, never a method).</p>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Candidate quality vs. what can actually be deployed"
          subtitle="Same windows (t_d+2…): the model that WOULD be deployed (shadow candidate, scored after the decision) vs the model that WAS deployed. A gap = candidates the gate could not certify." />
        <PanelBody>
          <CiPlot axisLabel="R-recovery on matched windows"
            rows={pairs.flatMap((a) => [
              { label: `${armLabel(a)} · deployed`, ci: d.arm_table[a].r_recovery_matched, color: "#5a6270" },
              { label: `${armLabel(a)} · candidate`, ci: d.arm_table[a].shadow_candidate, color: COLORS[a] ?? "#4fb3d9", bold: true },
            ])} />
          <p className="mt-2 text-[11px] text-text-tertiary">
            Shadow CTRL-SMOTE − shadow REAL_ONLY: {d.shadow_vs_real_only["CTRL-SMOTE"] ? ciStr(d.shadow_vs_real_only["CTRL-SMOTE"].diff) : "—"} ·
            deployed difference (H2): {ciStr(h.H2.diff)}
          </p>
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Per-seed R-recovery" subtitle="Seed sensitivity: every paired value behind H2" />
          <PanelBody>
            <table className="mono w-full text-[11.5px]">
              <thead><tr className="text-left text-text-tertiary"><th className="pb-1 font-normal">seed</th><th className="font-normal">real-only</th><th className="font-normal">ctrl+SMOTE</th><th className="font-normal">Δ</th></tr></thead>
              <tbody>
                {Object.keys(h.H2.per_seed).map((s) => (
                  <tr key={s} className="border-t border-border-subtle text-text-secondary">
                    <td className="py-1">{s}</td>
                    <td>{fx(d.per_seed.REAL_ONLY[s].r_recovery as number)}</td>
                    <td>{fx(d.per_seed["CTRL-SMOTE"][s].r_recovery as number)}</td>
                    <td className={(h.H2.per_seed[s] ?? 0) > 0 ? "text-good" : (h.H2.per_seed[s] ?? 0) < 0 ? "text-bad" : ""}>{fx(h.H2.per_seed[s])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Reporting conditions" subtitle="Preregistered failure / qualification flags (fired = reportable outcome, never a reason to retune)" />
          <PanelBody className="flex flex-col gap-1.5">
            {Object.entries(FLAG_TEXT).map(([k, t]) => (
              <div key={k} className="flex items-start justify-between gap-3 border-b border-border-subtle pb-1.5 text-[12px] last:border-0">
                <span className="text-text-secondary">{t}</span>
                <Badge tone={d.flags[k] ? "warn" : "idle"}>{d.flags[k] ? "fired" : "not fired"}</Badge>
              </div>
            ))}
          </PanelBody>
        </Panel>
      </div>
      <p className="mono text-[11px] text-text-tertiary">artifact: {r.artifact.file} · sha256 {r.artifact.sha256}</p>
    </div>
  );
}
