# Defense framing — Evaluation Validity in SDN Intrusion Detection

## One-sentence thesis
Reported InSDN accuracy of 99%+ answers "can a classifier label flows from hosts it has already seen?", not "can it detect a new attacker?"; we measure the difference with controls, on two datasets, and show that the controller-visible features are narrower than flow-CSV papers assume.

## What we claim (and the evidence)
1. **Host structure of InSDN.** 122,868 source IPs; 122,307 appear in one flow (spoofed floods); 8 hosts have >=500 flows (215,404 of 343,889 rows); 3 are attackers. Source: `results/leave_one_host_out.json`.
2. **Unseen-host detection collapses.** Leave-one-host-out, identifier columns removed: main attacker 200.175.2.130 -> 51.6% of attack flows caught (DoS 34.7%); largest benign host 192.168.20.133 -> 37.9% flagged. CICIDS2017 (48 source IPs): main attacker 172.16.0.1 -> 28.3% caught, 54.0% of its benign flows flagged. Sources: `leave_one_host_out*.json`.
3. **Random-split score is not explained by duplicates or missing classes.** InSDN random 0.9998; held-out hosts 0.907±0.085; after dropping 46% exact duplicates random is still 0.9998; with all attack classes present in training held-out is 0.939. CICIDS2017: 0.9917 vs 0.641±0.056. Sources: `protocol_audit_*.json`, `dedup_ladder.json`.
4. **Published-paper audit.** 12 papers examined, 10 read in full; none reports a host-grouped split; most do not describe their split; three list Flow ID/Src IP/ports among inputs. Source: `literature_check.json`.
5. **Observability gap.** 0 of 3,827 FlowMods in InSDN's ONOS captures match IPs or ports.

## What we do NOT claim
- That any paper's reported number is wrong. SDNGuardStack-style pipeline reproduces 0.9999 under its own random split (paper: 99.98%); it is the question it answers that differs.
- That leakage from random splits is new (Engelen 2021, Flood 2024 established it for other datasets).
- Priority on host structure: stated only as "absent in the papers we read in full". Not read: the InSDN dataset paper itself (README only).
- Confidence intervals on leave-one-host-out. Results are identical across 10 model seeds; uncertainty is which host is held out.

## Likely questions and honest answers
- *"Leakage is known."* Yes; we cite it. Contribution is the quantified, controlled gap on an SDN dataset, the host structure that explains the variance, and the protocol audit.
- *"Grouped split just removes a class."* Tested: gap persists with every attack class in training (0.939); dedup does not change the random score.
- *"Held-out-host is too harsh."* Agreed; it is a stress test of generalisation to a new host, stated as such. Triple-grouped split (src, dst, port) gives 0.961, so the effect is tied to unseen hosts.
- *"Your replication is not their model."* Correct: approximation, default hyperparameters, 5 seeds, CI up to ±0.39. We call it a partial replication.
- *"Only two datasets, one not SDN."* True. UKMDDoSDN has no benign class and was unusable; a second SDN dataset is future work.
- *"Why XGBoost?"* One fixed classifier isolates the protocol effect; other models may differ.

## AI-use statement (check your target venue's policy and adapt)
"An AI assistant (Claude, Anthropic) was used to help write analysis scripts, run and organise experiments, search and summarise the literature, and draft and edit text. The authors designed the study, verified every reported number against stored result files (`paper/verify_numbers.py`), and take responsibility for the content."

## Local checks run
- Heuristic AI-text scan of the paper: only 1 occurrence of "robust", 2 em dashes, none of the usual filler words; but 108 semicolons and long sentences (mean 21.7 words), which read as dense/machine-like. A humanizing pass should shorten sentences and break up semicolon chains. This is a heuristic, not a detector.
- 8-gram overlap vs 17 source texts on disk: only shared citations.
- Run a real similarity checker (Turnitin/iThenticate) and an AI-text checker on the final PDF yourself; I cannot run those services.
