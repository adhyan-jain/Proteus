# What does the SDN controller actually see?

Controller-observable telemetry in InSDN's own OpenFlow control channel: a measurement and validity study
Adhyan Jain · draft for supervisor review · October 2026

Paper: `paper/main.pdf` (source `paper/main.tex`). Every number below comes from a stored result file in
`results/` (named in each slide's source line). Speaker notes are the **Say** blocks.

---

## 1. The question

**Benchmarks score features a controller never receives.**

| What the benchmark gives | What an OpenFlow controller gets |
|---|---|
| InSDN CSV: 80+ CICFlowMeter statistics per bidirectional 5-tuple flow, computed offline from packet captures at the victim host | PacketIn headers, packet and byte counters of the flow entries it installed, and its own FlowMod / PacketOut decisions |

**Question:** what can be detected from the controller's own view?

**Say:** SDN IDS papers motivate themselves with the controller's global view, but are evaluated on flow features
computed at the victim host. Inter-arrival moments, per-direction length statistics and flag counts cannot be computed
by a controller. InSDN is convenient because its authors also captured the ONOS controller interface in every scenario.

---

## 2. The controller never installed or reported a 5-tuple flow entry

- **2** flow-entry match structures appear in every flow-statistics reply across all 44 controller captures:
  `eth_type` (default punt rules) and `(in_port, eth_src, eth_dst)` (reactive forwarding, a MAC pair)
- **0** of the **3,827 FlowMods** the controller sent has IP or transport match fields (3,811 MAC-pair, 16 `eth_type`;
  `results/flowmod_matches.json`), so a short-lived 5-tuple entry cannot have slipped between two polls
- so the dataset's labelled flows are not counters the controller can read

Source: decoded OpenFlow 1.3 multipart replies (`results/gap_attack_v2.json`, `feats_v4/meta.json`).
Observations: 80,464 `eth_type`, 24,437 MAC-pair.

**Say:** Measured, not assumed. Scope it correctly if asked: it is a property of the ONOS reactive-forwarding
configuration in InSDN, not of OpenFlow in general. Slide 4 tests exactly that.

---

## 3. What it does see: roughly one PacketIn per data packet

Ratio = PacketIns seen by ONOS ÷ data packets recorded at the target.

| Metasploitable-2 | Target pkts | Ratio | | OVS host | Target pkts | Ratio |
|---|---:|---:|---|---|---:|---:|
| Brute force | 1,311 | 1.20 | | Botnet | 902 | 1.11 |
| DDoS | 652,495 | 1.22 | | DDoS | 6,510,923 | 0.08 |
| DoS | 13,078 | 15.69 | | Probe | 86,705 | 1.29 |
| Exploit | 86 | 3.86 | | Brute force | 5,892 | 0.68 |
| Probe | 507,650 | 1.01 | | App. + net. DoS | 604,511 | 1.03–1.09 |
| | | | | Web | 987 | 1.21 |

Nine of twelve scenarios fall between 0.68 and 1.29. OVS DDoS is the outlier (6.5M target packets, few PacketIns),
consistent with control-channel saturation (not tested directly).

**Say:** The two sides are separate recordings, so alignment is unverified and the ratios are indicative, not exact
per-packet counts. The first parser lost up to ~90% of PacketIns on the DDoS captures; the resync fix reduced loss to
12 KB out of 7.38M decoded messages. Values: `results/gap_attack_v2.json`.

---

## 4. Forwarding application: what the controller observes (benign case study)

| Per run (~99 s capture), Mininet + Ryu, benign traffic only, 5 runs per mode | MAC-pair | 5-tuple, 10 s idle | 5-tuple, 2 s idle |
|---|---:|---:|---:|
| TCP PacketIns | 11.6 ± 4.2 | 10,350 ± 440 | 10,233 ± 415 |
| FlowMods (they follow the PacketIns) | 18.8 ± 2.8 | 10,372 ± 438 | 10,396 ± 423 |
| Per-flow (IP-specific) entries returned per stats reply | 0 | 151.9 ± 1.8 | 36.8 ± 0.4 |

- 5-tuple forwarding gave **675×–1,752×** (10 s idle) and **685×–1,780×** (2 s idle) more TCP PacketIns than MAC-pair in **every** paired run (5 of 5; the smallest
  possible sign-test p at n = 5 is 0.0625, but the intervals are ~3 orders of magnitude apart).
- 2 s vs 10 s idle: per-flow entries a 1 s poller sees drop to **0.239–0.246×** in all five pairs.
- ≈11–12 TCP PacketIns per completed request: connections are punted repeatedly (likely packets arriving before the
  FlowMod takes effect; mechanism **not** isolated).
- MAC-pair replicates the first campaign: 11.6 ± 4.2 vs 11.0 ± 4.1.

13,366 requests completed, 41 failed (all in one run: 5-tuple 2 s idle, seed 4), 0 parser desyncs
(`results/live_modes_v3.json`, `paper/live_table.tex`). Original flawed campaign: `results/live_modes_v2.json`.

**Say:** A visibility study, not a detection study: benign traffic, one switch, one app, no attacks, no detector.
Headline: forwarding granularity decides how much traffic reaches the controller, by about three orders of magnitude in
this testbed, and the idle timeout decides how much of the flow table a poller can see. Own the first campaign: my
original learning switch installed MAC-pair entries for ping and ARP in every mode; those also matched later TCP, so it
showed only 4× (43.4 ± 30.1 vs 11.0 ± 4.1). I found that through a review, fixed the app, and reran. The mode contrast
does not transfer to InSDN's ONOS, which punted ~1 packet per target packet even with MAC-pair entries (slide 3).
Mention the 41 failed requests in one run: probably the controller overloaded; not investigated.

---

## 5. Method

1. **Parse.** 44 ONOS captures (11 benign, 33 attack, 7 classes). 7.38M OpenFlow messages decoded; 134 resyncs,
   12,217 bytes lost. 182,153 PacketIns are truncated to headers (labels unaffected).
2. **Features.** 22 per 1 s window from PacketIn headers and flow-stats deltas, with 3 windows of history.
3. **Labels.** Window = attack iff a PacketIn's 5-tuple matches an attack flow in InSDN's CSV. Unmatched windows inside
   attack captures are excluded ("strict").
4. **Protocol.** No capture in both train and test. 10 seeds, GPU training, balanced accuracy.

**Say:** Labels are the part reviewers will probe. The alternative rule (also counting IPs seen only in attack flows)
covers spoofed floods but overlaps with the IP-count features, so it is a sensitivity variant. Strict labels leave
brute force, web and exploit with only 6, 12 and 12 attack windows: say this up front.

---

## 6. Feasibility: simple models separate attack captures from benign ones on unseen captures

Grouped 5-fold CV by capture, 1 s windows, strict labels, 10 seeds, 95% CI over seeds (`results/v4_strict_W1.json`).

| Method | Balanced acc. | Recall | FPR |
|---|---:|---:|---:|
| MLP, all features | 0.946 ± 0.016 | 0.893 | 0.001 |
| MLP, PacketIn features only | 0.943 ± 0.015 | 0.887 | 0.002 |
| Logistic regression | 0.939 ± 0.016 | 0.887 | 0.009 |
| MLP, single window | 0.934 ± 0.015 | 0.870 | 0.003 |
| Threshold: source-IP entropy | 0.852 ± 0.029 | 0.763 | 0.059 |
| Threshold: dst-port entropy | 0.839 ± 0.018 | 0.736 | 0.059 |
| MLP, flow-stats features only | 0.699 ± 0.036 | 0.683 | 0.284 |
| Threshold: PacketIn burst | 0.643 ± 0.008 | 0.912 | 0.627 |
| Threshold: PacketIn rate | 0.616 ± 0.011 | 0.793 | 0.561 |

A linear model matches the MLP overall (it differs on some held-out families, e.g. botnet 0.803 vs 0.932), so the value is
the controller view, not model size. The PacketIn-rate heuristic is weak, plausibly because benign sessions also produce
heavy PacketIn volume; I cannot verify this (the Normal group has no target-side captures). Folds are by capture file, so
this number is optimistic; slide 8 explains why it is not an attack-detection accuracy.

**Say:** The intervals come from re-shuffling which captures fall in which fold plus model initialisation, on the same
44 captures: not intervals over new testbeds. The capture-level cluster bootstrap (in the paper, Table "boot") is wider,
e.g. 0.926–0.995 for the MLP. No tree baseline: the XGBoost install failed on the network and GPU-only training rules out
a CPU substitute. Robustness: 5 s windows give 0.958; the IP-based label rule gives 0.881 (1 s) / 0.887 (5 s), same ranking
against thresholds.

---

## 7. Held-out attack families and a second deployment (same caveats as slide 8)

| Held-out family | MLP | Best threshold |
|---|---:|---:|
| Flood (DoS + DDoS) | 0.936 ± 0.011 | 0.814 |
| Probe | 0.997 ± 0.000 | 0.970 |
| Web | 0.904 ± 0.020 | 0.699 |
| Brute force | 0.891 ± 0.029 | 0.888 |
| Exploit | 0.929 ± 0.037 | 0.929 |
| Botnet | 0.932 ± 0.024 | 0.965 |

| Cross-deployment | MLP | Best threshold |
|---|---:|---:|
| Train Metasploitable-2 → test OVS | 0.905 ± 0.021 | 0.866 |
| Train OVS → test Metasploitable-2 | 0.990 ± 0.001 | 0.947 |

Brute force, web and exploit rest on 6–12 attack windows: indicative only.

**Say:** Families are held out whole: DoS and DDoS go out together as flood because their SYN, UDP and ICMP variants share
tools and victims. The MLP clearly beats the best single-feature threshold on flood, probe and web, ties on brute force
and exploit, loses on botnet (one capture). The best threshold is chosen per family in hindsight, which favours the baseline.
Under the IP-based label rule, Metasploitable-2 → OVS transfer no longer beats a threshold (0.678 vs 0.678).

---

## 8. Validity: the scores cannot be read as attack-detection accuracy

| Check (1 s windows unless noted) | Result |
|---|---|
| Within attack sessions, strict labels: MLP | 0.942 pooled / 0.906 macro |
| Same windows, trivial rule "any IP PacketIn in the window" | **0.995 pooled / 1.000 macro** (2,589 attack vs 320 attack-free windows; 317 of 320 attack-free have no IP PacketIn) |
| Same, IP-based labels (nothing excluded): MLP vs trivial rule | 0.794 / 0.855 vs 0.741 / 0.700 (5 s: 0.715 / 0.782 vs 0.653 / 0.668) |
| Session probe, attack-matched PacketIns removed | 0.940 (majority 0.500), but 424 of 518 attack-side windows contain unmatched-IP traffic |
| Session probe, attack-free windows only | 0.950 at 1 s from **6 windows, 2 captures**; 0.550 at 5 s from 2 windows |
| Label-shuffle sanity check | 0.512 ± 0.054 (chance) |

**Say:** This is the slide to own. Benign and attack traffic were recorded in separate sessions, and the CSV labels
cover only part of the controller-visible traffic. Under strict labels my ambiguity mask removes exactly the hard
negatives, so a trivial rule beats the model within sessions: I retract the earlier "conservative within-session
estimate" claim. The session probe cannot separate session identity from unlisted attack traffic, so I do **not**
claim sessions are separable independently of attack traffic, only that this data cannot rule session recognition out.
What survives: the scores show PacketIn-level features distinguish InSDN's attack captures from its benign captures
(feasibility), not attack-detection accuracy. A proper test needs benign and attack traffic interleaved in one session.

---

## 9. Contributions

1. **Measured gap.** Inside InSDN, the controller's flow entries are MAC pairs or `eth_type` only, and it sees about one
   PacketIn per target packet in most scenarios.
2. **Pipeline.** A reproducible OpenFlow 1.3 control-channel parser and featuriser for InSDN's 44 ONOS captures, with
   parser loss reported.
3. **Detection from that view (feasibility).** 0.946 balanced accuracy on unseen captures; the PacketIn-rate heuristic
   reaches 0.616; simple models suffice. Not an attack-detection accuracy (see slide 8).
4. **Validity analysis.** A trivial "any IP PacketIn" rule scores 0.995 within sessions under strict labels; our session
   probes cannot separate session identity from unlisted attack traffic. InSDN cannot settle this.
5. **Forwarding-application case study.** Per-flow forwarding sends ~10,300 TCP PacketIns per run to the controller vs
   ~12 for MAC-pair (675×–1,752× in every paired run); a 2 s idle timeout cuts the per-flow entries a 1 s poller sees to
   ~¼. A first, flawed campaign understated this and is reported.

Novelty rests on "inside InSDN, controller-observable only". LAN-SDN-NIDS (2026) builds a new dataset instead.

**Say:** Claim carefully. We are *not* first to use control-plane telemetry: Arévalo-Herrera et al. (Data 11(8):195, 2026)
released a dataset with PacketIn and FlowMod metrics. What we add is the measurement inside the most-used existing SDN
benchmark, its controller captures analysed (as far as our searches show; searches are not proof), the
controller-observable-only evaluation, the confound quantification, and the forwarding-app study. Verified related work:
Sarhan et al. 2022, Engelen et al. 2021, Pinto et al. 2025, Pekar and Jozsa 2024, Arp et al. 2022.

---

## 10. Likely questions, and honest answers

| Question | Answer |
|---|---|
| Is this just a better classifier? | No. A linear model matches the MLP. The claim is the measured controller view, the evaluation protocol and the forwarding-app finding. |
| Is it novel? | Within InSDN, controller-observable only: yes as far as searches show. Not first to use control-plane telemetry. |
| Does it detect attacks? | Not proven. It separates InSDN's attack captures from its benign captures; within sessions a trivial rule beats it under strict labels. We say so and recommend interleaved datasets. |
| One testbed only? | InSDN yes; plus a benign-only Mininet/Ryu study. Next: attack traffic with interleaved benign traffic, and detection under the other forwarding modes. |
| What about the 4× in your first Ryu run? | A bug in my learning switch: MAC-pair entries for ping/ARP shadowed TCP. Corrected app, rerun: 675×–1,752×. Both reported. |
| Why so many PacketIns per connection? | Likely packets arriving before the FlowMod takes effect (no barrier, full-packet PacketIns); not isolated. One run also had 41 failed requests, probably controller overload. |
| Folds are by capture file, not scenario? | Yes, so CV is optimistic; family-held-out and cross-deployment are the scenario-held-out tests. |

**Limits:** one InSDN testbed · strict labels leave brute force, web and exploit with 6–12 attack windows · no tree baseline ·
offline replay · live study is benign-only on one switch, so no cross-testbed detection yet.

**Say:** Robustness, all computed: 5 s windows give 0.958 overall and 0.944 within attack sessions. Under the broader
IP-based label rule the MLP drops to 0.881 (1 s) and 0.887 (5 s), still well above the best threshold (0.748 and 0.769).
Still open for a journal version: a second attack testbed with interleaved traffic, and detection under the other
forwarding modes.

---

## Reproduce

```
.venv/bin/python research/insdn_controller/ofgap/ctrlfeat.py data/raw/insdn_pcaps/ex research/insdn_controller/feats_v4
.venv/bin/python research/insdn_controller/ofgap/exp_ctrl2.py research/insdn_controller/feats_v4 research/insdn_controller/results/v4_strict_W1.json --W 1 --labels strict
.venv/bin/python research/insdn_controller/ofgap/make_tables.py <results.json> results/gap_attack_v2.json feats_v4/meta.json paper/tables.tex
sudo python3 research/insdn_controller/live/run_benign.py --out research/insdn_controller/live/campaign2 --repeats 5 --duration 90
.venv/bin/python research/insdn_controller/live/live_table.py live/campaign2 results/live_modes_v3.json paper/live_table.tex
cd research/insdn_controller/paper && latexmk -pdf main.tex
```

Dataset provenance and capture hashes: `data/MANIFEST.md` (InSDN controller-interface PCAPs section).
