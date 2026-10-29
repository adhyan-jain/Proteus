import { J, PageHead, Say, Section, Mono, Next } from "@/components/new-ui/study";

export default function Novelty() {
  const fm = J("flowmod_matches.json");
  const one = J("live_modes_v4_one10.json").summary;
  const l3 = J("live_modes_v4_linear3.json").summary;
  const v2 = J("live_modes_v2.json").summary;
  const st = J("stock_ryu_flowmods.json");
  const w1 = J("v4_strict_W1.json").A_grouped_cv;
  const rc1 = J("review_checks.json").within_session_W1_strict.any_ip_packet_in;
  const xg = J("v4_strict_W5_xgb.json").A_grouped_cv;
  const t = fm.total_by_match_structure;
  const pf = one.fivetuple.packet_in_tcp.mean, mc = one.mac.packet_in_tcp.mean;
  return (
    <>
      <PageHead kicker="Novelty points" title="Five contributions, explained so you can say them yourself" intro="We say 'as far as our searches show', never 'first'. Combining known tools in a new way is still a contribution: we claim the measurement and the combination, not a new algorithm." />

      <Section title="1 · The controller never saw the flows the dataset labels" desc="A gap in the benchmark itself">
        <p><b>In one line.</b> The dataset labels connections by 5-tuple (source and destination IP and port, protocol), but the rules the controller installed never contained IP addresses or ports.</p>
        <p><b>Analogy.</b> A security guard who only checks door numbers cannot tell you who walked through; a visitor log that lists people by name was written by someone else.</p>
        <p><b>What we did.</b> Parsed all 44 controller recordings, read every FlowMod and flow-statistics message, and counted which header fields the rules match on.</p>
        <p><b>Evidence.</b> 0 of {fm.flowmods.toLocaleString()} FlowMods have IP or port fields ({t["in_port|eth_dst|eth_src"].toLocaleString()} look at MAC pairs, {t.eth_type} at EtherType). The controller still receives a PacketIn stream: 0.68 to 1.29 per target packet in 9 of 12 attack scenarios.</p>
        <p><b>Why it matters.</b> Every InSDN paper that calls a CSV-trained detector &quot;controller-based&quot; uses numbers the controller never had.</p>
        <p><b>Where.</b> <Mono>ofgap/flowmod_check.py</Mono> → <Mono>results/flowmod_matches.json</Mono>; <Mono>ofgap/gap_measure.py</Mono> → <Mono>gap_attack_v2.json</Mono>. Paper section III.</p>
        <Say>We checked the dataset&apos;s own controller recordings. The controller never saw the 5-tuple flows the dataset labels, so CSV-trained detectors do not describe a real controller-side detector.</Say>
        <Next href="/new/gap" label="Open the gap page" />
      </Section>

      <Section title="2 · The forwarding program decides what the controller sees" desc="A measured effect, with confidence intervals">
        <p><b>In one line.</b> Same traffic, different forwarding setting, and the controller&apos;s workload and view change by hundreds of times.</p>
        <p><b>Analogy.</b> A receptionist who asks every visitor for ID at every door is flooded with questions; one who only checks which building you belong to is hardly asked anything.</p>
        <p><b>What we did.</b> A Mininet + Ryu network, the same benign web traffic under three settings, 10 runs each, on one switch and on a three-switch chain; then Ryu&apos;s own unmodified example app.</p>
        <p><b>Evidence.</b> TCP PacketIns per run: {Math.round(pf).toLocaleString()} per-flow vs {mc.toFixed(1)} MAC-pair ({(pf / mc).toFixed(0)}× on average; 665× to 1,752× in every paired run). Three switches: {Math.round(l3.fivetuple.packet_in_tcp.mean).toLocaleString()} vs {l3.mac.packet_in_tcp.mean.toFixed(1)}. A 2 s idle timeout cuts per-flow entries a 1 s poller sees from {one.fivetuple.fivetuple_entries_per_reply.mean.toFixed(1)} to {one.fivetuple_short.fivetuple_entries_per_reply.mean.toFixed(1)}. Stock Ryu: {st.flowmods} FlowMods, {st.total_by_match_structure["in_port|eth_dst|eth_src"]} MAC-pair, {st.total_by_match_structure["(table-miss)"]} table-miss, none with IP or ports.</p>
        <p><b>Honest limit.</b> The direction is expected from how reactive forwarding works; the contribution is the measured size and the reproducible method.</p>
        <p><b>Where.</b> <Mono>live/ryu_fwd.py</Mono>, <Mono>live/run_benign.py</Mono>, <Mono>live/live_table.py</Mono> → <Mono>live_modes_v4_one10.json</Mono>, <Mono>live_modes_v4_linear3.json</Mono>, <Mono>stock_ryu_flowmods.json</Mono>. Paper section VI.</p>
        <Say>What a controller can observe is a property of the forwarding app, so a detector&apos;s inputs must be specified together with the forwarding setup.</Say>
        <Next href="/new/forwarding" label="Open the forwarding page" />
      </Section>

      <Section title="3 · A high score is not proof of detection" desc="The validity result">
        <p><b>In one line.</b> Controller-only models reach {w1.mlp_all.bacc.mean.toFixed(3)} balanced accuracy on unseen captures, but a one-line rule matches that inside attack sessions, so the score does not prove detection.</p>
        <p><b>Analogy.</b> A test where all sick patients were photographed in one room and all healthy ones in another: a model that recognises the room scores full marks without knowing anything about illness.</p>
        <p><b>What we did.</b> Built detectors from controller messages only and tested them on captures never seen, on attack families never seen, and across the two target setups; then checked what a trivial rule scores and probed whether sessions are separable without any attack traffic.</p>
        <p><b>Evidence.</b> MLP {w1.mlp_all.bacc.mean.toFixed(3)} vs PacketIn-rate threshold {w1.thr_packet_in_rate.bacc.mean.toFixed(3)} (1 s windows). The rule &quot;at least one IP PacketIn in the window&quot; scores {rc1.bacc_pooled.toFixed(3)} inside attack sessions. XGBoost ({xg.xgb_all_history.bacc.mean.toFixed(3)}) and logistic regression ({xg.linear_all_history.bacc.mean.toFixed(3)}) do not beat the MLP ({xg.mlp_all.bacc.mean.toFixed(3)}) at 5 s.</p>
        <p><b>Where.</b> <Mono>ofgap/ctrlfeat.py</Mono>, <Mono>exp_ctrl2.py</Mono>, <Mono>review_checks.py</Mono> → <Mono>v4_strict_W1.json</Mono>, <Mono>v4_strict_W5_xgb.json</Mono>, <Mono>review_checks.json</Mono>. Paper sections IV to VI.</p>
        <Say>We do not claim a detector. We show that on InSDN, controller-side scores cannot be trusted as detection accuracy, and we state what data would fix it: benign and attack traffic mixed in one session.</Say>
        <Next href="/new/validity" label="Open the validity page" />
      </Section>

      <Section title="4 · A measurement pitfall we caught in ourselves" desc="Method lesson">
        <p><b>What happened.</b> Our first test app let ping and ARP MAC-pair rules also match later TCP between the same hosts, so most connections never reached the controller and the effect looked like {(v2.fivetuple.packet_in_tcp.mean / v2.mac.packet_in_tcp.mean).toFixed(0)}× instead of about {(pf / mc).toFixed(0)}×.</p>
        <p><b>Why it helps others.</b> An overlapping coarse rule can understate what a controller sees by two orders of magnitude. The flawed app is kept (<Mono>live/ryu_fwd_v1.py</Mono>) and reported (<Mono>live_modes_v2.json</Mono>).</p>
      </Section>

      <Section title="5 · Everything can be rebuilt and checked" desc="Support, not the headline">
        <p>One command regenerates every result and compares it with the stored files; every capture has a SHA-256; a script checks the numbers quoted in the paper against the result files. Say it only as &quot;the numbers can be checked&quot;, not as research novelty.</p>
        <Next href="/new/reproduce" label="Open the reproduce page" />
      </Section>
    </>
  );
}
