# Status: controller-observable telemetry on InSDN (2026-10-28)

## What exists
- `paper/main.pdf` (6 pages, IEEE conference format; source `paper/main.tex`, generated `paper/tables.tex`, `paper/live_table.tex`).
- `DEFENSE.md`: 10-slide talk with speaker notes and Q&A (Markdown, no artifacts).
- Pipeline: `ofgap/` (OpenFlow parser, features, experiments, table generator, review checks); live testbed in `live/`.
- Results: `results/` (every number in the paper comes from these files); capture hashes: `capture_hashes.sha256`.

## What the paper claims (and no more)
1. Measured: InSDN's own ONOS flow entries are MAC-pair or `eth_type` only; ~1 PacketIn per target packet in 9 of 12 scenarios.
2. Feasibility: controller-observable features separate InSDN's attack captures from benign captures (BAcc 0.946, capture-grouped CV).
3. Validity limits (stated in the paper): a trivial "any IP PacketIn" rule scores 0.995 within attack sessions under strict labels;
   the session probes cannot separate session identity from unlisted attack traffic; folds are by capture file, not scenario.
4. Case study (corrected app, 5 runs/mode): per-flow forwarding sends 10,350 ± 440 TCP PacketIns per run vs 11.6 ± 4.2 for MAC-pair
   (675×–1,752× in every paired run); a 2 s idle timeout cuts the per-flow entries a 1 s poller sees from 151.9 to 36.8 per reply.
   The first campaign (flawed app, ping/ARP shadowing) showed only 4× and is reported as such. One run had 41 failed requests.

## Not done, and why it blocks "submittable as a strong paper"
| Item | Blocker |
|---|---|
| Detection evaluated with benign and attack traffic interleaved in one session, in a second testbed (the only way to remove the session/label-coverage confound) | needs labelled attack traffic from an external source; not built in these sessions |
| Tree-model baseline | `xgboost` install failed on the network; training must stay on the GPU |
| Fourth review pass | after the paper update with the corrected-campaign numbers (the third review is done and applied: verdict "defensible as a scoped workshop measurement-and-validity paper, not a detector paper") |

## Honest venue assessment
A measurement-and-validity paper: workshop or conference level as written. A stronger journal version needs the interleaved
second testbed. Novelty rests on "inside InSDN, controller-observable only" (as far as searches show); LAN-SDN-NIDS (Data 11(8):195, 2026)
already builds a control-plane dataset, so "first to use control-plane telemetry" must not be claimed.
