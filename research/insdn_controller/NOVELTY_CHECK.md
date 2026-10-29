# Novelty and publishability check (2026-10-29)

Method: read main.tex abstract and contributions, literature_check.json, protocol_audit_*.json, and the head of recipe_replication.json. Then ran web searches. Depth of reading per source is stated below. Nothing here was verified beyond that. Time-boxed to about 20 minutes, so the search is not exhaustive.

## Closest prior work

| Paper | Read? | What it did | Overlap |
|---|---|---|---|
| Flood, Engelen, Aspinall, Desmet, "Bad Design Smells in Benchmark NIDS Datasets", EuroS&P 2024 (Distinguished Paper). https://detlearsom.github.io/pubs/BadSmells-EuroSP24-finaldraft.pdf | Full text fetched. I grepped the extracted text and read the smell 2 and section 3.5 passages. I did not read it end to end. | Names 6 "bad smells" in 7 NIDS benchmarks. Re-evaluates published papers (AJSMA, ADA, CADE). Shows timestamp or protocol shortcuts. States that standard randomised train/test splits leak in homogeneous traffic and that "no papers in our overview commented on this". Recommends against training and testing on the same attack class and dataset. Reviews the assumptions in published papers. | **C2 and C4: heavy conceptual overlap.** Random-split leakage, a paper-protocol audit, and the shortcut-feature argument are all already published at a top venue. They did not quantify a paired host-grouped gap per dataset, and they did not cover SDN or InSDN. |
| Engelen, Rimmer, Joosen, "Troubleshooting an Intrusion Detection Dataset: the CICIDS2017 Case Study", IEEE SPW 2021. DOI 10.1109/SPW53761.2021.00009 | Search snippet only | Label, flow-construction and feature-extraction errors in CICIDS2017. | C2 (CICIDS2017 half only). It is about errors, not splits. |
| Lanvin et al., "Errors in the CICIDS2017 dataset...", CRiSIS 2022. https://hal.archives-ouvertes.fr/hal-03775466 | Snippet only | Same family. Shows how corrections change detector performance. | Minor, CICIDS2017 only. |
| Liu, Engelen et al., "Error Prevalence in NIDS datasets", IEEE CNS 2022 | Snippet only | Recreates CICIDS2017 and CSE-CIC-IDS-2018 with corrected labels. | Minor. |
| Arp et al., "Dos and Don'ts of Machine Learning in Computer Security", USENIX Security 2022 | **Not fetched.** Cited from memory. | Pitfalls P1-P10 (sampling bias, spurious correlations, data snooping, etc.), and a survey of papers. | C2: the general argument is already established. Spurious correlation is their pitfall P4. |
| Apruzzese, Laskov, Schneider, "SoK: Pragmatic Assessment of ML for NID", EuroS&P 2023 | Reference seen in search results only. Content from memory. | Gap between lab evaluation and practice. | C1 and C2, conceptually. |
| Kostas et al., 2024 | **Not found.** One search returned nothing. | Cannot assess. | Do not cite it from memory without a verified reference. |
| Roy et al., "Unmasking Shortcut Learning in IoT Intrusion Detection", arXiv 2609.28725. https://arxiv.org/abs/2609.28725 | Search-result summary only | Static IP/MAC and timestamp shortcuts. Random flow split vs PCAP-disjoint evaluation. | **C2 pattern is repeated on an IoT dataset.** It is a preprint. |
| "A Multi-Class SDN Intrusion Detection Dataset with Synchronized OpenFlow Control-Plane Telemetry" (LAN-SDN-NIDS), MDPI Data 2025/26. https://doi.org/10.3390/data11080195 | Search summary only | Containernet/ODL dataset. 29 traffic features plus 11 control-plane metrics (Packet-In, Flow-Mod counts). Argues no comparable public dataset has this. | **C1, partially.** It builds the control-plane data a dataset-side fix needs. It does not audit other datasets' observability. |
| ASEADOS-SDN-IoT (ONOS, Elsevier 2026) https://www.sciencedirect.com/science/article/pii/S2542660526000211 ; Research Square preprint "Cross-Layer Early Detection of SDN-IoT Attacks: Fusing Controller Telemetry With Data-Plane Flow Statistics" https://www.researchsquare.com/article/rs-10119275/v1 | Snippets only | Controller telemetry combined with flow stats. | C1, adjacent. |
| PacketIn-based DDoS detection, and FlowStats-polling IDS lines (for example https://www.researchgate.net/publication/324791040 and https://ieeexplore.ieee.org/document/8024623/) | Snippets only | Detectors built on PacketIn counts or polled flow statistics. | C1: the idea that the controller sees PacketIn and FlowStats is textbook SDN-IDS. Our detection result is not new. |
| Elsayed et al., InSDN, IEEE Access 2020 | Snippet only | Dataset paper. States IPs can't separate classes. Claims it is free of duplicates. | C2: the "no duplicates" claim is contradicted by our 48.7% duplicate test rows, but only partly. See the attacks below. |

I found no paper that:
(a) parses InSDN's published ONOS control-channel PCAPs and shows that no FlowMod matches IP or ports,
(b) reports a paired random vs host-grouped gap on InSDN,
(c) audits the split protocol of InSDN papers.
That is an absence in about 15 searches, not proof. Search coverage of the SDN-IDS literature is thin, and IEEE and ACM pages mostly weren't readable.

## Per-claim verdict

1. **Observability gap: novel in its specific form, modest in importance.**
   - The strong form is that InSDN's own control-channel captures show the controller never holds 5-tuple counters. That I could not find anywhere.
   - The general point is folklore: a controller sees PacketIn and wildcard or MAC-level FlowStats, not CICFlowMeter features.
   - The forwarding-mode result (per-flow forwarding causes about 10,400 TCP PacketIns, MAC-pair forwarding about 12) is a sound measurement. It is close to trivially expected from how Ryu `simple_switch_13` works.
   - Stock Ryu installs only MAC-pair entries (86/91 FlowMods). Reviewers will say this is a property of the example app.
   - The PacketIn-only detector scores are admittedly unusable because of the session confound. They add nothing.
   - LAN-SDN-NIDS and ASEADOS already move toward control-plane features, which reduces novelty for a "should use controller telemetry" message.

2. **Paired split gap: incremental.**
   - Random-split leakage in NIDS is known. Flood 2024 states it and shows it on published papers. Engelen 2021, Arp 2022, Lanvin 2022 and Roy 2026 cover the same ground.
   - What is new is the specific numbers on InSDN. That includes 0.9998 vs 0.907 ± 0.085, the identifier-only probe, and the 48.7% duplicate rows.
   - CICIDS2017 (0.992 vs 0.641 ± 0.056) is the weaker point, because that dataset is already well-trodden.
   - Your own text rightly says "known", so keep it that way.

3. **Recipe replication: incremental, and fragile.**
   - It is one classifier (XGBoost), approximate recipes, and your own caveat that grouping changes class composition. Part of the 0.856-0.943 is class composition, not leakage.
   - A reviewer will say it does not replicate the papers. It is an XGBoost stand-in.
   - It is useful as a supporting table. It cannot carry a claim.

4. **Literature audit: known method, small sample, but a useful gap.**
   - Flood 2024 did a larger and better-designed version of this for non-SDN literature.
   - Your audit has 9 InSDN papers read in full, plus 3 other papers. 2 of 12 were unreadable.
   - "None uses host-grouped split" is a negative finding on a small sample. Several papers don't state a split at all. The text correctly says this does not prove their numbers are wrong.
   - The InSDN-specific claim is new and narrow. The count is too small to be a headline.

## Strongest honest framing

A measurement and methodology study for SDN-IDS evaluation, not a detection paper. In two parts.

1. Using the dataset's own control-channel PCAPs, flow-CSV features cannot be computed at the controller. We measure how forwarding applications shape what is visible.
2. A quantified instance of known leakage problems on the dominant SDN benchmark, with an audit of how its papers evaluate.

Explicitly present the PacketIn detector as a negative or validity result, not as a contribution. The abstract currently leads with detection scores that you then say are unreadable. Lead with the gap and the audit instead.

Do not claim "first to show random-split leakage". Claim "first to quantify it on InSDN, and to cross-check it against the controller's actual observables".

## Realistic venue tiers

- USENIX Security, CCS, NDSS, S&P: **very unlikely.** Flood 2024 already took the evaluation-flaws angle at the next tier down. A measurement of one dataset plus one Mininet case study is not enough.
- IEEE TNSM, Computer Networks, Computers & Security: **a long shot as it stands.** Reviewers will want a more general contribution, more than one SDN dataset (you have one; UKMDDoSDN could not be used), real baselines, and real-controller traffic. After the extra experiments below, it is possible but not likely.
- IEEE Access, Journal of Network and Systems Management, Computer Communications, Computers & Electrical Engineering: **plausible** with modest revisions. Access is the most likely journal.
- NOMS, NetSoft, IEEE CNS, ARES, ESORICS or ACSAC workshops, CSET, RAID workshops: **the realistic target.** A full or short paper on a measurement and methodology study fits the NetSoft / NOMS / ARES level well.
- Artifact or reproducibility tracks and dataset-and-benchmarks style venues: a good fit for the artifact itself (parser, audit scripts, seeds, hashes), but there is no new dataset, so benchmarks tracks are unlikely.

Honest summary: this is workshop or lower-tier-journal level, a solid short methodology paper. It is not top-tier, and I would not describe it as journal-level without the additions below.

## What a reviewer will attack

1. "Leakage in NIDS evaluation is known" (Flood, Engelen, Arp). Your answer is the SDN-specific quantification, so make that the contribution and don't oversell it.
2. InSDN is one dataset, one controller (ONOS), and a single lab. The gap may be specific to its capture design (benign and attack in separate sessions, few attacker hosts). The wide spread, with a worst split of 0.66 and several seeds near 1.0, shows how fragile the held-out-host numbers are.
3. The host-grouped split is also confounded. With few attacker IPs, holding out a host removes a whole class from training. Your recipe table admits this. "Gap = leakage" is not cleanly separated from "gap = class absence", and 0.907 itself is a harsh and partly artificial number. You need a control that holds class coverage fixed.
4. The controller-visible detector is confounded by session identity. You say so yourself, which means the detection results show nothing.
5. The Mininet/Ryu result is about one example app. A production controller runs reactive-proactive hybrids, ONOS fwd vs a proactive intent app, and so on. Stock-app evidence for "controllers see no IPs" is weak.
6. The recipe replication is XGBoost-only, so it is not a replication.
7. Literature audit: 12 papers, 2 unreadable, no inter-rater check, no stated inclusion criteria.
8. The first campaign had a flawed application and understated the PacketIn effect by more than two orders of magnitude. It is honest to report it, but it signals fragile experimental practice.

## Minimal extra experiments (each under a week, most 1-2 days)

1. **Class-coverage-controlled grouped split (1 day).** Make host-grouped splits that keep every class in training, or report per-class and macro metrics only on classes present in training. Also add a "random split of whole sessions or captures" condition. This separates leakage from class absence, and it answers attack 3, the most dangerous one.
2. **Time/session-grouped and duplicate-removed random split (1 day).** Report the random split after de-duplicating rows. If it still scores about 0.99, the leakage is identifier-driven. If it drops, the gap is partly duplicate-driven. Add a ladder: random, de-duplicated random, session-grouped, host-grouped, with identifiers removed in each.
3. **Second SDN dataset (2-4 days).** LAN-SDN-NIDS (CC-BY-4.0, Containernet/ODL) or ASEADOS-SDN-IoT (Kaggle) are available. Run the same split audit. Even just the paired gap would turn "one dataset" into "SDN datasets". Check against `data/MANIFEST.md`: the project rules require verified institutional sources and hashes. The data-source rule applies to the paper-grade pipeline, so check before you download.
4. **Second controller app/controller (1-2 days).** Add a proactive or hybrid forwarding setup in Ryu (or ONOS `fwd` vs intent-based). Report which fields are visible. This answers attack 5.
5. **Replicate at least one paper with its own model (2 days).** Use the Ataa et al. features (open, text-described) with their CNN-LSTM on random vs grouped split. One real model replication is worth more than four XGBoost recipes.
6. **Audit rigour (1 day).** State inclusion criteria, search date and queries, and list the 2 unreadable papers as unverified. A second person checks the 9 InSDN papers, and the two of you report agreement.
7. **Reframe the abstract (a few hours).** Lead with the gap and the audit. Cut or demote the detection score paragraph.

Still no pretense on numbers: all figures above come from the repo JSON files (random 0.99982, grouped 0.9074 ± 0.0847, CICIDS 0.9917 vs 0.6408 ± 0.0564, duplicate rate 0.487 and 0.203). I did not re-run anything.

## Caveats on this check

- Most sources are search snippets, not full text. Only Flood 2024 was fetched in full (the text was then grepped, not fully read). Arp 2022 and Apruzzese 2023 are cited from memory. Kostas 2024 could not be located.
- The ASEADOS / LAN-SDN-NIDS characterisations come from search-result summaries and could be inaccurate.
- The Roy et al. arXiv ID and others look like real search results but are unreviewed preprints.
