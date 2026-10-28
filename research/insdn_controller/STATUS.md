# Status: controller-observable telemetry on InSDN (2026-10-28)

## What exists
- `paper/main.pdf` (7 pages, IEEE journal format; source `paper/main.tex`, generated `paper/tables.tex`, `paper/live_table.tex`).
- Pipeline: `ofgap/` (OpenFlow parser, features, experiments, table generator, review checks); live testbed in `live/`.
- Results: `results/` (every number in the paper comes from these files); capture hashes: `capture_hashes.sha256`.

## What the paper claims (and no more)
1. Measured: InSDN's own ONOS flow entries are MAC-pair or `eth_type` only; ~1 PacketIn per target packet in 9 of 12 scenarios.
2. Feasibility: controller-observable features separate InSDN's attack captures from benign captures (BAcc 0.946, capture-grouped CV).
3. Validity limits (stated in the paper): a trivial "any IP PacketIn" rule scores 0.995 within attack sessions under strict labels;
   the session probes cannot separate session identity from unlisted attack traffic; folds are by capture file, not scenario.
4. Case study (corrected app, 10 runs/mode on one switch and 10 on a 3-switch chain): per-flow forwarding sends 10,422 ± 202 TCP PacketIns per run vs 12.3 ± 2.3 for MAC-pair
   (665×–1,752× in every paired run; 391×–1,509× on 3 switches); a 2 s idle timeout cuts the per-flow entries a 1 s poller sees from 153.1 to 36.9 per reply.
   The first campaign (flawed app, ping/ARP shadowing) showed only 4× and is reported as such. One early run had 41 failed requests; 59 later runs had none (cause not established).

## Not done, and why it blocks "submittable as a strong paper"
| Item | Blocker |
|---|---|
| Detection evaluated with benign and attack traffic interleaved in one session, in a second testbed (the only way to remove the session/label-coverage confound) | needs labelled attack traffic from an external source; not built in these sessions |
| Tree-model baseline | DONE (W=5 s, strict labels, 10 seeds, GPU): XGBoost BAcc 0.952 ± 0.013 vs linear 0.961 ± 0.011 vs MLP 0.958 ± 0.012 (capture-grouped CV; `results/v4_strict_W5_xgb.json`). Trees give no gain. |
| Fourth review pass | after the paper update with the corrected-campaign numbers (the third review is done and applied: verdict "defensible as a scoped workshop measurement-and-validity paper, not a detector paper") |

## Honest venue assessment
A measurement-and-validity paper: workshop or conference level as written. A stronger journal version needs the interleaved
second testbed. Novelty rests on "inside InSDN, controller-observable only" (as far as searches show); LAN-SDN-NIDS (Data 11(8):195, 2026)
already builds a control-plane dataset, so "first to use control-plane telemetry" must not be claimed.
