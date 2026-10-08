import { research, isOk } from "@/lib/research";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { EvidenceLabel, type EvidenceKind } from "@/components/research/evidence-label";
import { ciStr } from "@/lib/research-format";

export const dynamic = "force-dynamic";

const THREATS: [string, string][] = [
  ["One effective class", "Across both P0 budgets only PortScan ever generates a GO. Any positive result is a statement about PortScan on CICIDS2017 Friday until a second scenario replicates it."],
  ["Contradictory labels", "A share of PortScan feature vectors also carry other labels elsewhere in the corpus, so part of the residual error may be intrinsically unrepairable. The ambiguity flag from P0 is retained and decomposed (ambiguous vs non-ambiguous rows) in P1."],
  ["Certification power", "At 100 labels per window the promotion gate sees roughly 100–160 benign rows; one extra false positive already exceeds ε_FPR = 0.005. A better candidate can be unprovable, which is why candidate quality is scored separately from deployed quality."],
  ["Post-hoc design choices", "The R-recovery endpoint and the incremental step-safety filter were fixed after reading P0 descriptives and before any P1 data; both are recorded in the v1.4 spec with their reason. P1 thresholds were not tuned on P1 outcomes."],
  ["Analysis-time repairable set", "R comes from the all-labels control of P0; no arm ever receives it, but the endpoint uses it, so the endpoint is not label-free."],
  ["Learner and trigger", "Random forests only; oracle trigger (every post-drift window is an episode); label delay fixed at one window; shuffled stationary drift day. KS-triggered operation and time-ordered replay are not evaluated."],
  ["Statistics", "10 paired seeds, two-sided t-intervals; the fixed sequence controls family-wise error for H2→H5 only. Ablations, controls and references are descriptive."],
  ["No live network", "Nothing here ran on Mininet/Ryu. 39 of 52 deployment features are defaulted to 0 by the OpenFlow mapper, so no deployment claim follows."],
];

export default async function LimitsPage() {
  const [p1r, p0r, artR, verR, stagesR] = await Promise.all([research.p1(), research.p0(), research.artifacts(), research.verification(), research.stages()]);
  const p1 = isOk(p1r) ? p1r.doc : null;
  const h = p1?.hypotheses;
  const ledger: { claim: string; kind: EvidenceKind; note: string }[] = [
    { claim: "Real-only adaptation leaves a residual per-class deficiency at B=100", kind: isOk(p0r) ? "PROVEN" : "NOT_RUN", note: isOk(p0r) ? `P0 ${p0r.doc.h1.outcome} (${p0r.doc.h1.scope}); PortScan only; ambiguity-qualified` : "" },
    { claim: "A utility-tested synthetic controller beats real-only adaptation (H2)", kind: !p1 ? "NOT_RUN" : h!.H2.rejected ? "SUPPORTED" : "NOT_SUPPORTED", note: h ? `Δ ${ciStr(h.H2.diff)}` : "" },
    { claim: "…and the gain is attributable to synthetic content (H3a, H3b)", kind: !p1 || !h!.H2.rejected ? "NOT_RUN" : h!.H3a.rejected && h!.H3b.rejected ? "SUPPORTED" : "NOT_SUPPORTED", note: !p1 ? "" : h!.H2.rejected ? "tested" : "not tested: sequence stopped at H2" },
    { claim: "The controller is selective (adds synthetic data only where it is useful)", kind: "NOT_RUN", note: p1 ? (p1.flags.F8_degenerate_controller ? "UNTESTED: the controller never added a row (F8), so the negative controls are vacuous; only pre-drift windows (no-op) were a non-trivial check" : p1.flags.F11_negative_control_beats_real_only ? "a negative control beat real-only (F11)" : "controls did not beat real-only") : "" },
    { claim: "Promoted models stay inside the safety envelope", kind: !p1 ? "NOT_RUN" : h!.H4.passed ? "SUPPORTED" : h!.H4.s_report_breaches > 0 ? "NOT_SUPPORTED" : "HYPOTHESIS", note: h ? (h.H4.safe_by_inaction ? "no breach, but only because synthetic candidates were (almost) never promoted" : `${h.H4.s_report_breaches} breaches`) : "" },
    { claim: "A learned generator (WGAN-GP) beats SMOTE", kind: "NOT_RUN", note: p1?.verdict.p2_unlocked ? "gate open" : "P2 gate closed (H2∧H3a∧H3b not all rejected)" },
    { claim: "The result replicates on scenario S2", kind: (stagesR.stages.p3_s2 as { ran: boolean }).ran ? "SUPPORTED" : "NOT_RUN", note: "S2 is only run through its own P0 gate" },
    { claim: "Live SDN deployment", kind: "FUTURE", note: "not evaluated" },
  ];
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-[15px] font-semibold text-text-primary">Claims, limits and reproducibility</h1>

      <Panel>
        <PanelHeader title="Claims ledger" subtitle="Labels are derived from the artifacts, not written by hand" />
        <PanelBody className="flex flex-col gap-2">
          {ledger.map((l) => (
            <div key={l.claim} className="flex flex-col gap-1 border-b border-border-subtle pb-2 last:border-0 last:pb-0">
              <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-[12.5px] text-text-primary">{l.claim}</span><EvidenceLabel kind={l.kind} /></div>
              {l.note && <span className="mono text-[11px] text-text-tertiary">{l.note}</span>}
            </div>
          ))}
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border-subtle pt-2">
            <span className="text-[12.5px] text-text-primary">Legacy “5.91× macro-F1” (Stage 7, demo console)</span><Badge tone="bad">SUPERSEDED · not evidence for synthetic benefit</Badge>
          </div>
          <span className="mono text-[11px] text-text-tertiary">the legacy gain comes from oracle labels on 70% of every window; its own ablation shows real-only adaptation does as well (results/gan_ablation.json)</span>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader title="Threats to validity" subtitle="Design-level limits; they hold regardless of the result" />
        <PanelBody className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {THREATS.map(([t, body]) => (
            <div key={t} className="rounded border border-border-subtle bg-surface-2 p-3">
              <p className="text-[12px] font-semibold text-text-primary">{t}</p>
              <p className="mt-1 text-[11.5px] leading-relaxed text-text-secondary">{body}</p>
            </div>
          ))}
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Artifact registry" subtitle="Every number in this console comes from one of these files" />
          <PanelBody>
            <table className="mono w-full text-[10.5px]"><tbody>
              {artR.artifacts.map((a) => (
                <tr key={a.key} className="border-t border-border-subtle align-top text-text-secondary">
                  <td className="py-1 pr-2">{a.file}</td>
                  <td className="pr-2">{a.exists ? <Badge tone="good">present</Badge> : <Badge tone="idle">absent</Badge>}</td>
                  <td className="break-all text-text-tertiary">{a.sha256?.slice(0, 20) ?? ""}</td>
                </tr>))}
            </tbody></table>
            <p className="mt-2 text-[11px] text-text-tertiary">{artR.p1_seed_files.length} per-seed P1 files under results/p1/</p>
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Verification" subtitle="Test runs recorded in results/verification_report.json" />
          <PanelBody>
            {isOk(verR) ? (
              <div className="flex flex-col gap-2 text-[12px]">
                {verR.doc.commands.map((c) => (
                  <div key={c.command} className="rounded border border-border-subtle bg-surface-2 p-2">
                    <p className="mono text-[11px] text-text-secondary">{c.command}</p>
                    <p className="mono text-[11px] text-text-tertiary">{c.result}</p>
                  </div>))}
                {verR.doc.notes.map((n) => <p key={n} className="text-[11px] text-text-tertiary">{n}</p>)}
              </div>
            ) : <EmptyState reason="results/verification_report.json has not been written yet." className="min-h-[100px]" />}
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Reproduce" subtitle="From the repo root; the P0 numbers need only the cached arrays" />
        <PanelBody>
          <pre className="mono overflow-x-auto whitespace-pre-wrap text-[11px] leading-relaxed text-text-secondary">{`python -m proteus.intervention.cache build        # once; verifies SHA-256 of CICIDS2017
python -m proteus.intervention.p0                 # frozen P0 (already run; results/intervention_p0_S1_*.json)
python -m proteus.intervention.p1                 # preregistered campaign -> results/p1/*.json
python -m proteus.intervention.analyze_p1         # tests + summary + decision traces
.venv/bin/pytest -q                               # full suite
cd paper/p1 && latexmk -pdf main.tex              # paper from the artifacts`}</pre>
        </PanelBody>
      </Panel>
    </div>
  );
}
