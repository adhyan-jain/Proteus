import Link from "next/link";
import { research, isOk } from "@/lib/research";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { Stat } from "@/components/ui/stat";
import { EmptyState } from "@/components/ui/empty-state";
import { CiPlot } from "@/components/research/ci-plot";
import { EvidenceLabel } from "@/components/research/evidence-label";
import { armLabel, ciStr, fx } from "@/lib/research-format";

export const dynamic = "force-dynamic";

const STAGE_FLOW = [
  { id: "P0", text: "Is there room? (REAL_ONLY vs all-labels control)", gate: "GO → P1" },
  { id: "P1", text: "Does a utility-tested synthetic controller beat real-only adaptation?", gate: "H2∧H3a∧H3b → P2" },
  { id: "P2", text: "Does a learned generator (WGAN-GP) beat SMOTE?", gate: "S2 P0 GO → P3" },
  { id: "P3", text: "Does it replicate on a second scenario (S2)?", gate: "" },
];

export default async function ResearchOverview() {
  const [p0r, p1r, stagesR] = await Promise.all([research.p0(), research.p1(), research.stages()]);
  const p0 = isOk(p0r) ? p0r.doc : null;
  const p1 = isOk(p1r) ? p1r.doc : null;
  const stages = stagesR.stages;

  const arms = p1?.arm_table;
  const h2 = p1?.hypotheses.H2;
  const ranked = arms
    ? ["FROZEN", "REAL_ONLY", "CTRL-ROS", "CTRL-THRESH", "CTRL-SMOTE", "FIXED-SMOTE-1", "FIXED-SMOTE-4", "ALWAYS-SMOTE", "FIDGATE-SMOTE"]
        .filter((a) => arms[a])
        .map((a) => ({
          label: armLabel(a),
          ci: arms[a].r_recovery,
          color: a === "CTRL-SMOTE" ? "#9d7de8" : a === "REAL_ONLY" ? "#3ecf8e" : a === "FROZEN" ? "#5a6270" : "#4fb3d9",
          bold: a === "CTRL-SMOTE" || a === "REAL_ONLY",
        }))
    : [];

  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-[15px] font-semibold text-text-primary">Feedback-controlled synthetic intervention</h1>
          <Badge tone="network">research console</Badge>
        </div>
        <p className="mt-1 max-w-4xl text-[12.5px] leading-relaxed text-text-secondary">
          Can a drift-aware IDS decide <em>when</em>, <em>for which class</em> and <em>how much</em> synthetic data to add, from
          observed recovery value, under an explicit safety envelope, and does that beat simply adapting on the real labels it
          has? Everything below is read from result files on disk; nothing is estimated.
        </p>
      </div>

      {p1 ? (
        <Panel className={p1.verdict.branch.startsWith("NEGATIVE") ? "border-warn/40" : p1.verdict.branch.startsWith("POSITIVE") ? "border-good/40" : "border-network/40"}>
          <PanelBody className="flex flex-wrap items-center justify-between gap-4">
            <div className="max-w-3xl">
              <p className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-text-tertiary">Mechanical verdict of the preregistered P1 sequence</p>
              <p className="mt-1 text-[14px] font-semibold text-text-primary">{p1.verdict.branch}</p>
              <p className="mt-1 text-[11.5px] text-text-tertiary">
                Applied by <span className="mono">analyze_p1.py</span> to {p1.provenance.seeds_present.length} paired seeds
                {p1.provenance.complete ? " (complete)" : " (INCOMPLETE campaign: do not cite)"} ·{" "}
                {p1.provenance.all_preregistered ? "preregistered configuration" : "NOT a preregistered configuration"} · spec v{p1.p1_spec_version}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {p1.verdict.fired_flags.map((f) => (
                <Badge key={f} tone="warn">{f.split("_")[0]} {f.split("_").slice(1).join(" ").toLowerCase()}</Badge>
              ))}
            </div>
          </PanelBody>
        </Panel>
      ) : (
        <EmptyState title="P1 NOT RUN" reason="results/intervention_p1_S1_B100_summary.json does not exist. Run the campaign and proteus.intervention.analyze_p1." />
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Panel><PanelBody>
          <Stat label="P0 outcome" value={p0?.h1.outcome ?? "—"} tone={p0?.h1.outcome === "GO" ? "good" : "warn"} />
          <p className="mt-2 text-[11px] text-text-tertiary">{p0?.h1.scope}</p>
        </PanelBody></Panel>
        <Panel><PanelBody>
          <Stat label="R-recovery · real-only" value={fx(arms?.REAL_ONLY.r_recovery.mean)} tone="good" />
          <p className="mt-2 text-[11px] text-text-tertiary">{ciStr(arms?.REAL_ONLY.r_recovery)}</p>
        </PanelBody></Panel>
        <Panel><PanelBody>
          <Stat label="R-recovery · controller+SMOTE" value={fx(arms?.["CTRL-SMOTE"].r_recovery.mean)} tone="synthetic" />
          <p className="mt-2 text-[11px] text-text-tertiary">{ciStr(arms?.["CTRL-SMOTE"].r_recovery)}</p>
        </PanelBody></Panel>
        <Panel><PanelBody>
          <Stat label="H2 · paired difference" value={fx(h2?.diff.mean)} tone={h2?.rejected ? "good" : "warn"} />
          <p className="mt-2 text-[11px] text-text-tertiary">{h2 ? `${ciStr(h2.diff)} · ${h2.rejected ? "null rejected" : "null NOT rejected"}` : "—"}</p>
        </PanelBody></Panel>
      </div>

      <Panel>
        <PanelHeader title="Deployed recovery of the repairable drift classes, by arm"
          subtitle={`Mean over seeds with 95% t-interval (n=${p1?.provenance.seeds_present.length ?? "—"}). R = ${p1?.provenance.repairable_set_names.join(", ") ?? "—"} (frozen P0 repairable set). Endpoint: ${p1?.primary_endpoint ?? "—"}`} />
        <PanelBody>{ranked.length ? <CiPlot rows={ranked} zero={false} axisLabel="R-recovery (mean E-F1 over repairable classes, deployed model)" /> : <EmptyState reason="No P1 summary." />}</PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Evidence ladder" subtitle="What is established, what is implemented, what is not run" />
          <PanelBody className="flex flex-col gap-3 text-[12.5px]">
            <Row label="Feasibility: room for intervention exists at B=100 (one class, PortScan)" k="PROVEN" note={p0 ? `P0 ${p0.h1.outcome}; V1/V3/V4 pass: ${p0.h1.validity_all_pass}` : ""} />
            <Row label="Controller, generators, threshold arm, gate, canary, shadow scoring" k="IMPLEMENTED" note="unit-tested; mutation/isolation tests in tests/test_intervention_*.py" />
            <Row label="Synthetic intervention beats real-only (H2)" k={p1 ? (h2?.rejected ? "SUPPORTED" : "NOT_SUPPORTED") : "NOT_RUN"} note={h2 ? ciStr(h2.diff) : ""} />
            <Row label="WGAN-GP generator beats SMOTE (P2)" k={stages.gates.p2_unlocked ? "NOT_RUN" : "NOT_RUN"} note={stages.gates.p2_unlocked ? "unlocked, not yet run" : "gate closed: H2∧H3a∧H3b not all rejected"} />
            <Row label="Second scenario S2 replication (P3)" k={(stages.p3_s2 as { ran: boolean }).ran ? "SUPPORTED" : "NOT_RUN"} note={(stages.s2_p0_summary as { ran: boolean }).ran ? "S2 P0 gate evaluated; P3 runs only if it is GO (see P0 page)" : "S2 P0 gate not run"} />
            <Row label="Live SDN / Mininet deployment" k="FUTURE" note="no live controller; 39 of 52 features are defaulted in the SDN mapper" />
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Gated research pipeline" subtitle="Each stage runs only if its predecessor's gate opened" />
          <PanelBody className="flex flex-col gap-2">
            {STAGE_FLOW.map((s, i) => (
              <div key={s.id} className="flex items-start gap-3 rounded border border-border-subtle bg-surface-2 px-3 py-2">
                <span className="mono mt-0.5 w-7 text-[12px] font-semibold text-network">{s.id}</span>
                <div className="flex-1 text-[12px] text-text-secondary">{s.text}</div>
                <span className="mono text-[10.5px] text-text-tertiary">{s.gate}</span>
                {i < STAGE_FLOW.length - 1 && null}
              </div>
            ))}
            <p className="mt-1 text-[11px] text-text-tertiary">
              Detail: <Link className="text-network underline" href="/research/p0">P0</Link> ·{" "}
              <Link className="text-network underline" href="/research/p1">P1</Link> ·{" "}
              <Link className="text-network underline" href="/research/controller">controller decisions</Link> ·{" "}
              <Link className="text-network underline" href="/research/limits">claims &amp; limits</Link>
            </p>
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}

function Row({ label, k, note }: { label: string; k: Parameters<typeof EvidenceLabel>[0]["kind"]; note?: string }) {
  return (
    <div className="flex flex-col gap-1 border-b border-border-subtle pb-2 last:border-0 last:pb-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-text-primary">{label}</span>
        <EvidenceLabel kind={k} />
      </div>
      {note && <span className="mono text-[11px] text-text-tertiary">{note}</span>}
    </div>
  );
}
