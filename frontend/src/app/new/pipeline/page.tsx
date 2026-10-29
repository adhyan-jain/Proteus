import { DT, Mono, PageHead, Section, Why } from "@/components/new-ui/study";

const STEPS: [string, string, string, string][] = [
  ["0 Dataset", "InSDN PCAP archives (hashed, see data/MANIFEST.md)", "44 ONOS controller captures: 11 benign, 33 attack, 7 attack classes", "data/raw/insdn_pcaps/ex/"],
  ["1 Parse OpenFlow", "One capture (TCP 6653)", "Messages: PacketIn, PacketOut, FlowMod, FlowRemoved, stats replies (7,381,679 total; 12,217 bytes lost)", "ofgap/ofparse.py"],
  ["2 Label", "Each PacketIn's embedded packet and the InSDN CSV flow IDs", "Tag per PacketIn: attack-in-CSV, attack-IP-only, normal, unmatched IP, non-IP", "ofgap/ctrlfeat.py, attacker_ips.py"],
  ["3 Windows and features", "Message stream; window of 1 s or 5 s", "22 numbers per window", "ofgap/ctrlfeat.py"],
  ["4 History", "Window rows", "88 inputs: current plus three previous windows, causal", "ofgap/exp_ctrl.py"],
  ["5 Models", "88 inputs and the window label", "Attack or not per window; recall, FPR, balanced accuracy", "ofgap/exp_ctrl2.py (GPU)"],
  ["6 Tests", "Predictions", "10-seed mean with 95% CI; bootstrap; trivial-rule and session probes", "ofgap/exp_ctrl2.py, review_checks.py"],
  ["7 Granularity check", "The same captures", "Which header fields every FlowMod and stats entry matches on", "ofgap/flowmod_check.py, gap_measure.py"],
  ["8 Live study", "Ryu app in three modes plus Mininet, benign traffic", "Control-channel captures and client logs", "live/run_benign.py (needs root)"],
  ["9 Live analysis", "Those captures", "PacketIns, FlowMods and entries per poll, per mode, with CI", "live/live_table.py"],
  ["10 Baselines", "InSDN CSV", "Host-side XGBoost score (contrast only)", "ofgap/hostside_baseline.py"],
  ["11 Paper", "Result JSON files", "LaTeX tables and the PDF", "ofgap/make_tables.py, paper/"],
];

export default function Pipeline() {
  return (
    <>
      <PageHead kicker="Architecture" title="What goes in and what comes out, step by step" intro="The study has two independent pipelines that meet in the paper. The InSDN pipeline analyses recorded controller captures; the live pipeline records new captures from a small Mininet and Ryu network. Both end as result JSON files, and the paper's tables are generated from those files." />
      <Section title="Flow">
        <pre className="overflow-x-auto rounded-md bg-muted p-4 text-xs leading-relaxed">{`InSDN controller pcaps (44) ──► OpenFlow parser ──► label PacketIns ◄── InSDN CSVs (labels only)
                                          │
                                          ▼
                             windows: 22 features per 1 s / 5 s
                                          │
                                          ▼
                     + 3 previous windows = 88 inputs ──► MLP / logistic / XGBoost / thresholds
                                          │
                                          ▼
              tests: unseen captures · unseen families · other deployment · trivial rule · session probes
                                          │
                                          ▼
                        results/*.json ──► paper tables ──► verify_numbers.py

Ryu app (3 forwarding modes) + Mininet ──► control-channel pcap ──► live_table.py ──► results/live_modes_*.json`}</pre>
        <Why>The model never sees the CSV&apos;s flow features. The CSV only tells us which windows contain attack traffic. All training runs on the GPU.</Why>
      </Section>
      <Section title="Every step" desc="Input, output and the file that does it">
        <DT head={["Step", "Input", "Output", "File"]} rows={STEPS.map(([a, b, c, d]) => [a, b, c, <Mono key={a}>{d}</Mono>])} />
      </Section>
    </>
  );
}
