import { ci, DT, J, PageHead, Say, Section, Why } from "@/components/new-ui/study";

const FAMS: Record<string, string> = { flood: "Flood (DoS + DDoS)", probe: "Probe", brute: "Brute force", exploit: "Exploit", web: "Web attack", botnet: "Botnet" };

export default function Validity() {
  const w1 = J("v4_strict_W1.json"), w5 = J("v4_strict_W5_xgb.json"), ip1 = J("v4_iprule_W1.json");
  const rc = J("review_checks.json"), hs = J("hostside_xgb.json");
  const A1 = w1.A_grouped_cv, A5 = w5.A_grouped_cv, B = w1.B_grouped_cv ?? w1.B_leave_one_attack_family_out, C = w1.C_cross_deployment, D = w1.D_session_confound_probe;
  const best = (o: Record<string, { bacc?: { mean: number } }>) => Math.max(...Object.entries(o).filter(([k]) => k.startsWith("thr_")).map(([, v]) => v.bacc?.mean ?? 0));
  const row = (label: string, k: string) => [label, ci(A1[k]?.bacc, 3), A5[k] ? ci(A5[k].bacc, 3) : "n/a"];
  const t1 = rc.within_session_W1_strict.any_ip_packet_in, t5 = rc.within_session_W5_strict.any_ip_packet_in;
  return (
    <>
      <PageHead kicker="Novelty 3" title="A high score is not proof of detection" intro="We built detectors that use only what the controller receives, then tested them as strictly as the data allows. The scores are high, but InSDN's design means they cannot be read as attack-detection accuracy. This page shows the scores and the checks that limit them." />
      <Section title="How the detectors work" desc="Input and output">
        <p><b>Input:</b> 88 numbers per window: 22 controller-observable features (message counts, distinct IPs and ports in PacketIns, protocol fractions, entropies, flow-statistics deltas) for the current and the three previous windows. <b>Output:</b> attack or not attack for that window. The CSV only supplies labels; its flow features are never an input.</p>
        <p><b>Labels (strict):</b> a window is attack if it holds at least one PacketIn whose 5-tuple matches an InSDN attack flow. Attack-session windows with unmatched IP traffic are dropped as ambiguous. <b>Protocol:</b> no capture is in both training and test; 10 seeds; mean ± 95% CI.</p>
      </Section>
      <Section title="A · Unseen captures" desc="Capture-grouped 5-fold cross-validation, balanced accuracy">
        <Why>How well each method separates attack windows from benign windows on recordings it never trained on. 0.5 is a coin flip. The simple PacketIn-rate threshold is the usual heuristic.</Why>
        <DT head={["Method", "1 s windows", "5 s windows"]} rows={[
          row("MLP (controller features + history)", "mlp_all"), row("Logistic regression", "linear_all_history"),
          row("Single-window MLP", "mlp_all_single_window"), row("PacketIn-only features", "mlp_packet_in_only"), row("Flow-stats-only features", "mlp_stats_only"),
          row("XGBoost (GPU)", "xgb_all_history"), row("Threshold: PacketIn rate", "thr_packet_in_rate"), row("Threshold: source-IP entropy", "thr_src_ip_entropy"),
        ]} />
        <p className="text-muted-foreground">Logistic regression and XGBoost match the neural network, so history and non-linearity add little: the model is not the contribution. XGBoost was not run at 1 s.</p>
      </Section>
      <Section title="B · Withheld attack families" desc="Train without one family, test on it (1 s windows, MLP vs best single-feature threshold)">
        <Why>Tests whether the signal generalises to an attack type never seen in training. Some families rest on very few windows (brute force, exploit, web: 6 to 12 attack windows), so those rows are weak.</Why>
        <DT head={["Withheld family", "MLP", "Best threshold (chosen in hindsight)"]} rows={Object.entries(B).map(([f, v]) => [FAMS[f] ?? f, ci((v as { mlp_all: { bacc: never } }).mlp_all.bacc, 3), best(v as never).toFixed(3)])} />
      </Section>
      <Section title="C · Across deployments" desc="Train on one target setup, test on the other, disjoint benign captures">
        <DT head={["Direction", "MLP", "Best threshold"]} rows={Object.entries(C).map(([d, v]) => [d.replace("->", " → "), ci((v as { mlp_all: { bacc: never } }).mlp_all.bacc, 3), best(v as never).toFixed(3)])} />
      </Section>
      <Section title="D · Why the score is not detection accuracy" desc="The validity checks">
        <Why>InSDN records benign and attack traffic in separate sessions, and its CSV labels cover only part of the traffic the controller sees. A model can therefore score well by recognising the session. These checks show how large that risk is.</Why>
        <DT head={["Check", "Result"]} rows={[
          ["Trivial rule: at least one IP PacketIn, inside attack sessions (1 s)", `${t1.bacc_pooled.toFixed(3)} balanced accuracy (${t1.positives.toLocaleString()} attack, ${t1.negatives} attack-free windows)`],
          ["Same rule at 5 s", `${t5.bacc_pooled.toFixed(3)} (${t5.positives} attack, ${t5.negatives} attack-free windows)`],
          ["Why it works", `${rc.within_session_W1_strict.attack_capture_negatives_nonempty.with_zero_ip_packet_in} of ${rc.within_session_W1_strict.attack_capture_negatives_nonempty.total} attack-free windows have no IP PacketIn at all (ARP or LLDP only)`],
          ["Session probe: background-only features predict the session", `${ci(D.D1_all_windows.bacc, 3)} (majority baseline ${D.D1_all_windows_majority_baseline.bacc.mean.toFixed(3)}), but 82% of its attack side holds unmatched-IP PacketIns that may be unlisted attack traffic`],
          ["IP-rule labels (all windows kept), MLP vs best threshold", `${ci(ip1.A_grouped_cv.mlp_all.bacc, 3)} vs ${best(ip1.A_grouped_cv).toFixed(3)}`],
        ]} />
        <p className="text-muted-foreground">We conclude only that the available data cannot rule out session recognition as the source of the scores. A convincing evaluation needs benign and attack traffic interleaved in one session, with labels for all controller-visible traffic.</p>
      </Section>
      <Section title="Contrast: the usual flow-CSV protocol" desc="Host-side features, random row splits">
        <p>XGBoost on InSDN&apos;s own CICFlowMeter features ({hs.rows.toLocaleString()} flows, {hs.features} features, {hs.seeds} seeds) reaches {hs.bacc_mean.toFixed(4)} ± {hs.bacc_ci95.toFixed(5)}. This is not the same traffic or unit: rows of one session fall on both sides of the split and a controller never receives these features. It shows the usual benchmark protocol is far easier, not that the controller view is worse.</p>
        <Say>We do not claim a detector. On InSDN, controller-side scores cannot be trusted as detection accuracy; mixing benign and attack traffic in one session would fix that.</Say>
      </Section>
    </>
  );
}
