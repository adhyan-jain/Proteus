import { research, isOk } from "@/lib/research";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { Stat } from "@/components/ui/stat";
import { EmptyState } from "@/components/ui/empty-state";
import { CiPlot } from "@/components/research/ci-plot";
import { EvidenceLabel } from "@/components/research/evidence-label";
import { fx } from "@/lib/research-format";

export const dynamic = "force-dynamic";

const STATUS_TONE = { GO: "good", NO_ROOM: "warn", UNMEASURABLE: "idle" } as const;

export default async function P0Page() {
  const [r, s2r] = await Promise.all([research.p0(), research.p0s2()]);
  if (!isOk(r)) return <EmptyState title="P0 NOT RUN" reason={r.reason} />;
  const s2 = isOk(s2r) ? s2r.doc : null;
  const d = r.doc;
  const names = d.data.class_names;
  const R = d.validity.v4_repairability.repairable_set;
  const budgets = d.budgets.map(String);
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[15px] font-semibold text-text-primary">P0 · feasibility and data adequacy</h1>
        <EvidenceLabel kind="PROVEN" />
        <Badge tone="idle">frozen · spec v{d.spec_version} · commit {d.git_sha.slice(0, 7)}</Badge>
      </div>
      <p className="max-w-4xl text-[12.5px] leading-relaxed text-text-secondary">
        P0 asks only whether there is residual per-class deficiency <em>after</em> real-only adaptation under a realistic label
        budget. It does <strong>not</strong> show that synthetic data helps. Scenario {d.scenario} (Mon–Thu → Fri), seeds {d.seeds.join(", ")},
        budgets {d.budgets.join(" and ")} labels per window.
      </p>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Panel><PanelBody><Stat label="outcome" value={d.h1.outcome} tone={d.h1.outcome === "GO" ? "good" : "warn"} /><p className="mt-2 text-[11px] text-text-tertiary">{d.h1.scope}</p></PanelBody></Panel>
        <Panel><PanelBody><Stat label="repairable set R" value={R.map((c) => names[c]).join(" · ")} tone="network" /><p className="mt-2 text-[11px] text-text-tertiary">drift classes that abundant labels repair in ≥3/5 seeds</p></PanelBody></Panel>
        <Panel><PanelBody><Stat label="V1 leakage audit" value={d.validity.v1_leakage_audit.pass ? "PASS" : "FAIL"} tone={d.validity.v1_leakage_audit.pass ? "good" : "bad"} /><p className="mt-2 text-[11px] text-text-tertiary">{d.validity.v1_leakage_audit.n_runs_audited} runs, {d.validity.v1_leakage_audit.n_run_violations} violations</p></PanelBody></Panel>
        <Panel><PanelBody><Stat label="V2 null region (diagnostic)" value={d.diagnostics.v2_null_region.pass ? "PASS" : "FAIL"} tone={d.diagnostics.v2_null_region.pass ? "good" : "warn"} /><p className="mt-2 text-[11px] text-text-tertiary">never gates the outcome</p></PanelBody></Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {budgets.map((b) => {
          const a = d.data_adequacy.per_budget[b];
          return (
            <Panel key={b}>
              <PanelHeader title={`Budget B=${b} labels / window`} subtitle={`${a.n_seeds_with_go} of 5 seeds have ≥2 GO cells (need 3) · ${a.n_seeds_assessable} assessable`}
                right={<Badge tone={STATUS_TONE[a.status as keyof typeof STATUS_TONE] ?? "neutral"}>{a.status}</Badge>} />
              <PanelBody>
                <table className="mono w-full text-[11.5px]">
                  <thead><tr className="text-left text-text-tertiary"><th className="pb-1 font-normal">seed</th><th className="font-normal">cells</th><th className="font-normal">assessable</th><th className="font-normal">GO cells</th><th className="font-normal">GO classes</th></tr></thead>
                  <tbody>
                    {Object.entries(a.per_seed).map(([s, v]) => (
                      <tr key={s} className="border-t border-border-subtle text-text-secondary">
                        <td className="py-1">{s}</td><td>{v.n_cells}</td><td>{v.n_assessable}</td>
                        <td className={v.n_go >= 2 ? "text-good" : "text-text-tertiary"}>{v.n_go}</td>
                        <td>{v.go_classes.map((c) => names[c]).join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </PanelBody>
            </Panel>
          );
        })}
      </div>

      <Panel>
        <PanelHeader title="Repairability of each drift class (positive control: all labels)" subtitle="Seeds (of 5) in which abundant labels repair the class; a class outside R can never create a GO" />
        <PanelBody>
          <table className="mono w-full text-[11.5px]">
            <thead><tr className="text-left text-text-tertiary"><th className="pb-1 font-normal">class</th><th className="font-normal">repaired</th><th className="font-normal">residual deficiency</th><th className="font-normal">thin real support</th><th className="font-normal">unmeasurable</th><th className="font-normal">in R</th></tr></thead>
            <tbody>
              {Object.entries(d.validity.v4_repairability.per_budget[budgets[budgets.length - 1]].per_class_seed_counts).map(([c, v]) => (
                <tr key={c} className="border-t border-border-subtle text-text-secondary">
                  <td className="py-1">{names[Number(c)]}</td><td className="text-good">{v.repaired}</td><td>{v.residual_deficiency}</td><td>{v.thin_real_support}</td><td>{v.unmeasurable}</td>
                  <td>{R.includes(Number(c)) ? <Badge tone="good">R</Badge> : <Badge tone="idle">unrepaired</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Ambiguity qualification" subtitle="The GO class carries contradictory feature vectors; the GO must be cited with this qualification" />
          <PanelBody className="flex flex-col gap-3">
            {Object.entries(d.diagnostics.label_ambiguity.go_classes).map(([c, v]) => (
              <div key={c} className="rounded border border-warn/30 bg-warn-dim/20 p-3 text-[12px] text-text-secondary">
                <p className="text-text-primary"><strong>{names[Number(c)]}</strong> is the only class that generates a GO (GO cells in {v.seeds_with_go_cell} seed-window sets).</p>
                <p className="mono mt-1 text-[11px]">max D_sel conflict share {fx(v.max_d_sel_share)} · max E share {fx(v.max_e_share)} · threshold ε_def {d.diagnostics.label_ambiguity.threshold_eps_def}</p>
                {v.possibly_ambiguity_driven && <p className="mt-1 text-warn">flag: possibly ambiguity-driven</p>}
              </div>
            ))}
            <p className="mono text-[11px] text-text-tertiary">
              corpus: {d.data.label_conflicts.n_groups_with_conflicting_labels_corpus?.toLocaleString()} feature vectors carry more than one label;{" "}
              {d.data.label_conflicts.n_groups_with_different_labels_across_pools?.toLocaleString()} differ across the pre-drift/drift pools.
            </p>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="What P0 recovery looked like" subtitle="Descriptive only: v1.3 recovery AUC by condition and budget (mean, 95% t-interval, n=5)" />
          <PanelBody>
            <CiPlot zero={false}
              rows={budgets.flatMap((b) => ["FROZEN", "REAL_ONLY", "REAL_ONLY_ALL_LABELS"].map((c) => ({
                label: `B=${b} · ${c.replaceAll("_", " ").toLowerCase()}`, ci: d.aggregate_by_budget[b].recovery_auc[c],
                color: c === "REAL_ONLY" ? "#3ecf8e" : c === "FROZEN" ? "#5a6270" : "#4fb3d9" })))} />
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Scenario S2 · the gate for P3" subtitle="Same frozen §L.1 rules, scenario S2 (Mon+Tue → Wed, DoS family). P3 runs only if this gate is GO."
          right={s2 ? <Badge tone={s2.h1.outcome === "GO" ? "good" : "warn"}>{s2.h1.outcome}</Badge> : <Badge tone="idle">not run</Badge>} />
        <PanelBody>
          {s2 ? (
            <div className="flex flex-col gap-3">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {Object.entries(s2.data_adequacy.per_budget).map(([b, a]) => (
                  <div key={b} className="rounded border border-border-subtle bg-surface-2 p-3 text-[12px] text-text-secondary">
                    <div className="flex items-center justify-between"><span className="text-text-primary">B={b}</span><Badge tone={STATUS_TONE[a.status as keyof typeof STATUS_TONE] ?? "neutral"}>{a.status}</Badge></div>
                    <p className="mono mt-1 text-[11px]">{a.n_seeds_assessable}/5 seeds assessable · {a.n_seeds_with_go}/5 seeds with ≥2 GO cells · GO cells in total: {Object.values(a.per_seed).reduce((t, v) => t + v.n_go, 0)}</p>
                  </div>
                ))}
              </div>
              <p className="text-[12px] text-text-secondary">
                Validity {s2.validity.v4_repairability.pass && s2.validity.v1_leakage_audit.pass && s2.validity.v3_integrity.pass ? "passed" : "FAILED"}. {s2.h1.scope}: abundant labels repair the DoS drift classes
                ({s2.validity.v4_repairability.repairable_set.map((c) => s2.data.class_names[c]).join(", ")}), and real-only adaptation leaves no certifiable residual deficiency. By the preregistered rule P3 does not run and
                the conclusion for S2 is “real-only adaptation suffices at the assessed budgets”.
              </p>
              <p className="mono text-[11px] text-text-tertiary">{s2r.available ? (s2r as { artifact: { file: string; sha256: string } }).artifact.file : ""} · sha256 {s2r.available ? (s2r as { artifact: { sha256: string } }).artifact.sha256 : ""}</p>
            </div>
          ) : <EmptyState reason="results/intervention_p0_S2_summary.json does not exist: the S2 gate has not been run on this machine." className="min-h-[100px]" />}
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Frozen preregistration" subtitle="Provenance of the P0 artifact" />
        <PanelBody className="mono grid grid-cols-1 gap-1 text-[11px] text-text-tertiary">
          <span>file: {r.artifact.file} · {r.artifact.bytes.toLocaleString()} bytes</span>
          <span>sha256: {r.artifact.sha256}</span>
          <span>spec rules sha256: {d.spec_rules_sha256}</span>
          <span>criteria digest: {d.criteria_digest}</span>
          <span>params digest: {d.params_digest}</span>
          <span>preregistered configuration: {String(d.preregistered_configuration)}</span>
        </PanelBody>
      </Panel>
    </div>
  );
}
