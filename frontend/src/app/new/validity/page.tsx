import { Bars } from "@/components/new-ui/charts";
import { COLORS } from "@/components/new-ui/colors";
import { Chip, Insight, J, PageHead, Section } from "@/components/new-ui/study";

const FAMS: Record<string, string> = { flood: "Flood", probe: "Probe", brute: "Brute force", exploit: "Exploit", web: "Web", botnet: "Botnet" };

export default function Validity() {
  const w1 = J("v4_strict_W1.json"), w5 = J("v4_strict_W5_xgb.json"), rc = J("review_checks.json"), hs = J("hostside_xgb.json");
  const A1 = w1.A_grouped_cv, A5 = w5.A_grouped_cv, B = w1.B_leave_one_attack_family_out, C = w1.C_cross_deployment, D = w1.D_session_confound_probe;
  const best = (o: Record<string, { bacc?: { mean: number } }>) => Math.max(...Object.entries(o).filter(([k]) => k.startsWith("thr_")).map(([, v]) => v.bacc?.mean ?? 0));
  const t1 = rc.within_session_W1_strict.any_ip_packet_in.bacc_pooled, t5 = rc.within_session_W5_strict.any_ip_packet_in.bacc_pooled;
  const M: [string, string][] = [["thr_packet_in_rate", "PacketIn-rate threshold"], ["thr_src_ip_entropy", "IP-entropy threshold"], ["linear_all_history", "Logistic regression"], ["mlp_all", "MLP"]];
  const main = [...M.map(([k, n]) => ({ name: n, w1: A1[k].bacc.mean, w5: A5[k].bacc.mean })), { name: "XGBoost", w1: null, w5: A5.xgb_all_history.bacc.mean }, { name: "Trivial rule: any IP PacketIn", w1: t1, w5: t5 }];
  const fam = Object.entries(B).map(([f, v]) => ({ name: FAMS[f] ?? f, mlp: (v as { mlp_all: { bacc: { mean: number } } }).mlp_all.bacc.mean, thr: best(v as never) }));
  const cross = Object.entries(C).map(([d, v]) => ({ name: d.replace("->", " → "), mlp: (v as { mlp_all: { bacc: { mean: number } } }).mlp_all.bacc.mean, thr: best(v as never) }));
  return (
    <>
      <PageHead kicker="Novelty 3" title="A high score is not proof of detection" intro="Detectors built only from controller messages score high, but a one-line rule scores higher inside attack sessions." />
      <Section title="Balanced accuracy on unseen captures" desc="Capture-grouped CV, 10 seeds. 0.5 is a coin flip. The last row is the trivial rule." tell="Models score 0.94 to 0.96, but a one-line rule scores 0.995 to 1.000, so the score is not proof of detection.">
        <Bars height={330} data={main} series={[{ key: "w1", name: "1 s windows", color: COLORS.teal }, { key: "w5", name: "5 s windows", color: COLORS.amber }]} decimals={3} />
        <Chip>v4_strict_W1.json · v4_strict_W5_xgb.json · review_checks.json</Chip>
      </Section>
      <Section title="Attack families never seen in training" desc="MLP vs the best single-feature threshold. Brute force, exploit and web rest on 6–12 attack windows." tell="The MLP beats the best threshold on flood, probe and web, ties on brute force and exploit, and loses on botnet.">
        <Bars height={300} data={fam} series={[{ key: "mlp", name: "MLP", color: COLORS.teal }, { key: "thr", name: "Best threshold", color: COLORS.gray }]} decimals={3} />
      </Section>
      <Section title="Across target setups" desc="Train on one deployment, test on the other." tell="The signal transfers between deployments (0.905 and 0.990), ahead of the best threshold.">
        <Bars height={240} data={cross} series={[{ key: "mlp", name: "MLP", color: COLORS.teal }, { key: "thr", name: "Best threshold", color: COLORS.gray }]} decimals={3} />
      </Section>
      <Section title="Why the score is not detection accuracy" desc="InSDN records benign and attack traffic in separate sessions." tell="A model can tell the sessions apart without any attack traffic (0.940), so the scores may reflect the session, not the attack.">
        <Bars height={240} data={[{ name: "Session probe (background only)", v: D.D1_all_windows.bacc.mean }, { name: "Majority baseline", v: D.D1_all_windows_majority_baseline.bacc.mean }, { name: "Host-side flow-CSV (contrast)", v: hs.bacc_mean }]} series={[{ key: "v", name: "BAcc", color: COLORS.purple }]} cellColors={[COLORS.purple, COLORS.gray, COLORS.amber]} decimals={3} />
        <p className="text-sm text-muted-foreground">The probe predicts the session without any attack traffic, but 82% of its attack side holds unlisted-IP PacketIns that may be unlabelled attacks, so it cannot settle the question. The host-side score uses features a controller never gets.</p>
      </Section>
      <Insight analogy="All the sick patients were photographed in one room and all the healthy ones in another. A model that recognises the room scores full marks without knowing anything about illness." gain="We claim a validity warning, not a detector. The fix is benign and attack traffic mixed in one session." />
    </>
  );
}
