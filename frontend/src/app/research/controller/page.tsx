import { research, isOk, type DecisionRow } from "@/lib/research";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { Stat } from "@/components/ui/stat";
import { EmptyState } from "@/components/ui/empty-state";
import { DecisionGrid } from "@/components/research/decision-grid";
import { StackedBars } from "@/components/research/stacked-bars";
import { EvidenceLabel } from "@/components/research/evidence-label";
import { armLabel, fx, REASON_LABEL } from "@/lib/research-format";

export const dynamic = "force-dynamic";

const REASON_COLORS: Record<string, string> = {
  promoted: "#3ecf8e", no_affected_region: "#454b55", utility_no_gain: "#4fb3d9", utility_inconclusive: "#1c3a45",
  utility_unmeasurable: "#5a6270", envelope_inconclusive: "#e0a63e", envelope_violated: "#e2555a", envelope_unverifiable: "#9d7de8", sanity: "#e08fc0",
};
const STOP_COLORS: Record<string, string> = {
  no_affected_region: "#454b55", real_only_sufficient: "#3ecf8e", no_admissible: "#5a6270", k_max: "#9d7de8",
  no_safe_candidate: "#e0a63e", no_gain: "#4fb3d9", fixed_dose: "#e08fc0", real_only: "#2c313b",
};

function tally(t: Record<string, number>, prefix: string) {
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(t)) if (k.startsWith(prefix + ":")) out[k.slice(prefix.length + 1)] = v;
  return out;
}

export default async function ControllerPage() {
  const [p1r, decR] = await Promise.all([research.p1(), research.decisions()]);
  if (!isOk(p1r)) return <EmptyState title="P1 NOT RUN" reason={p1r.reason} />;
  const d = p1r.doc;
  const names = d.class_names;
  const ctrlArms = ["CTRL-SMOTE", "CTRL-ROS", "CTRL-THRESH"].filter((a) => d.arm_table[a]);
  const stopKeys = ["no_affected_region", "real_only_sufficient", "no_admissible", "no_safe_candidate", "no_gain", "k_max"];
  const stopData = ctrlArms.map((a) => ({ name: armLabel(a), ...Object.fromEntries(stopKeys.map((k) => [k, tally(d.arm_table[a].tallies, "stop_reasons")[k] ?? 0])) }));
  const reasonArms = ["REAL_ONLY", "CTRL-SMOTE", "CTRL-THRESH", "FIXED-SMOTE-1", "FIXED-SMOTE-4", "ALWAYS-SMOTE", "FIDGATE-SMOTE"].filter((a) => d.arm_table[a]);
  const reasonKeys = Object.keys(REASON_COLORS);
  const reasonData = reasonArms.map((a) => ({ name: armLabel(a), ...Object.fromEntries(reasonKeys.map((k) => [k, tally(d.arm_table[a].tallies, "reasons")[k] ?? 0])) }));
  const alloc = ctrlArms.flatMap((a) => Object.entries(tally(d.arm_table[a].tallies, "class_allocation")).map(([c, n]) => ({ a, c: names[Number(c)], n })));
  const fd = d.flag_details as { controller_runs_with_eligible?: number; controller_runs_k0?: number };
  const sf = d.step_filter_diagnostics;

  const dec = isOk(decR) ? decR.doc : null;
  // an example search trace: first CTRL-SMOTE window that evaluated candidates
  let example: { seed: string; row: DecisionRow } | null = null;
  if (dec) {
    for (const [s, rows] of Object.entries(dec.traces["CTRL-SMOTE"] ?? {})) {
      const row = rows.find((r) => r.search.length > 0 && r.search.some((it) => it.candidates.length > 0));
      if (row && (!example || row.k! > (example.row.k ?? 0))) example = { seed: s, row };
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[15px] font-semibold text-text-primary">Controller decisions</h1>
        <EvidenceLabel kind="IMPLEMENTED" />
        <Badge tone="idle">oracle trigger · B={d.budget}</Badge>
      </div>
      <p className="max-w-4xl text-[12.5px] leading-relaxed text-text-secondary">
        Each window the controller (1) finds the affected region A, (2) builds the real-only model θ_R, (3) takes the classes whose recall θ_R still lacks as the need set I,
        (4) greedily adds dose to one class at a time only if the <em>lower confidence bound</em> of the gain on selection labels exceeds the step cost η and the step stays inside the
        incremental safety envelope, and (5) hands the result to the frozen promotion gate. Below: what it actually did.
      </p>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Panel><PanelBody><Stat label="controller runs with a need" value={String(fd.controller_runs_with_eligible ?? "—")} /><p className="mt-2 text-[11px] text-text-tertiary">CTRL-SMOTE, all seeds, I ≠ ∅</p></PanelBody></Panel>
        <Panel><PanelBody><Stat label="of which k = 0 (no step accepted)" value={String(fd.controller_runs_k0 ?? "—")} tone={d.flags.F8_degenerate_controller ? "warn" : "good"} /><p className="mt-2 text-[11px] text-text-tertiary">F8 fires above 80%</p></PanelBody></Panel>
        <Panel><PanelBody><Stat label="candidate steps evaluated" value={String(sf.candidates ?? "—")} /><p className="mt-2 text-[11px] text-text-tertiary">{sf.safe} passed the step safety filter · {sf.gain_lcb_positive} had gain LCB &gt; 0</p></PanelBody></Panel>
        <Panel><PanelBody><Stat label="anchor-relative filter would block" value={`${sf.anchor_would_block_stable ?? 0}`} tone="warn" /><p className="mt-2 text-[11px] text-text-tertiary">stable-F1 steps (logged, not used): why the filter is incremental</p></PanelBody></Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Why the search stopped" subtitle="Per controller arm, over all seeds and post-drift windows" />
          <PanelBody><StackedBars data={stopData} series={stopKeys.map((k) => ({ key: k, label: k.replaceAll("_", " "), color: STOP_COLORS[k] }))} height={220} /></PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Class allocation" subtitle="Windows in which each class received a non-zero accepted dose" />
          <PanelBody>
            {alloc.length ? (
              <table className="mono w-full text-[11.5px]"><tbody>
                {alloc.map((r) => <tr key={r.a + r.c} className="border-t border-border-subtle text-text-secondary"><td className="py-1">{armLabel(r.a)}</td><td>{r.c}</td><td className="text-right text-synthetic">{r.n}</td></tr>)}
              </tbody></table>
            ) : <EmptyState title="NO DOSE ACCEPTED" reason="No controller arm accepted a dose step for any class in any window: the controller degenerated to a no-op (reported, not hidden)." className="min-h-[120px]" />}
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="What happened to each candidate at the gate" subtitle="Final per-window outcome by arm (all seeds). Amber = the envelope could not be shown safe: the certification bottleneck." />
        <PanelBody><StackedBars data={reasonData} series={reasonKeys.map((k) => ({ key: k, label: REASON_LABEL[k] ?? k, color: REASON_COLORS[k] }))} height={300} /></PanelBody>
      </Panel>

      {dec && ["CTRL-SMOTE", "CTRL-THRESH", "REAL_ONLY", "FIXED-SMOTE-4"].filter((a) => dec.traces[a]).map((a) => (
        <Panel key={a}>
          <PanelHeader title={`Decision grid · ${armLabel(a)}`} subtitle="One cell per (seed, window); hover for the reason, candidate verdict and stop reason" />
          <PanelBody><DecisionGrid rows={dec.traces[a]} /></PanelBody>
        </Panel>
      ))}

      <Panel>
        <PanelHeader title="One search trace" subtitle={example ? `CTRL-SMOTE · seed ${example.seed} · window ${example.row.t} · need set ${JSON.stringify((example.row.eligible ?? []).map((c) => names[c]))} · stopped: ${example.row.stop_reason}` : "no trace with evaluated candidates"} />
        <PanelBody>
          {example ? (
            <table className="mono w-full text-[11px]">
              <thead><tr className="text-left text-text-tertiary"><th className="pb-1 font-normal">iter</th><th className="font-normal">class</th><th className="font-normal">rung</th><th className="font-normal">+rows</th><th className="font-normal">gain LCB</th><th className="font-normal">gain pt</th><th className="font-normal">ΔFPR sel UCB</th><th className="font-normal">Δstable UCB</th><th className="font-normal">ΔFPR S UCB</th><th className="font-normal">safe</th><th className="font-normal">accepted</th></tr></thead>
              <tbody>
                {example.row.search.flatMap((it) => it.candidates.map((c) => (
                  <tr key={`${it.k}-${c.c}`} className="border-t border-border-subtle text-text-secondary">
                    <td className="py-1">{it.k}</td><td>{names[c.c]}</td><td>{c.rung}</td><td>{c.n_syn_after}</td><td>{fx(c.gain_lcb)}</td><td>{fx(c.gain_point)}</td>
                    <td>{fx(c.d_fpr_sel_ucb, 4)}</td><td>{fx(c.d_stable_s_ucb, 4)}</td><td>{fx(c.d_fpr_s_ucb, 4)}</td>
                    <td className={c.safe ? "text-good" : "text-warn"}>{String(c.safe)}</td><td className={it.accepted === c.c ? "text-synthetic" : ""}>{it.accepted === c.c ? "yes" : "—"}</td>
                  </tr>)))}
              </tbody>
            </table>
          ) : <EmptyState reason="No decision trace is available (run analyze_p1 to export results/intervention_p1_S1_B100_decisions.json)." className="min-h-[100px]" />}
        </PanelBody>
      </Panel>
    </div>
  );
}
