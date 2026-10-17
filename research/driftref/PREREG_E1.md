# PREREG E1 — Does a model swap make the drift alarm fire on unchanged traffic?

Written 2026-10-17, BEFORE any E1 result exists. Anything decided after seeing results is
labelled EXPLORATORY in the report. Hash of this file: `PREREG_E1.sha256` (committed with it).

## Invariant under test (I1)
"A drift alarm reflects a change in the traffic, not a change in which model is serving."
Formally: if traffic is exchangeable with the reference traffic, the per-window false-alarm
rate of the KS confidence test is <= alpha, whatever model is serving.

## Why it can fail in this repo (code facts, read before the run)
- `proteus/drift_daemon.py`: reference = first 30 live confidences (`LiveSampleBuffer.add`,
  min(reference_size,30)); never reset; `hot_swap_to_release` does not touch it. Defaults:
  eval window 100, alpha 0.01.
- `proteus/closed_loop_full.py`: `ref_confidence` = initial model's confidences on its own first
  50,000 TRAINING rows; never recomputed after `partial_fit_adaptation`. alpha 0.05.
- The adapted model is a different model (BoundedBuffer 20k ref + 5k recent; daemon uses depth 15),
  so its confidence distribution can differ from the reference model's on identical traffic.

## Data and splits (no synthetic data; cached CICIDS2017, `results/cache/cicids2017_v1.npz`)
- Rows from Monday-Thursday only (pre-drift days). Friday is used ONLY for the positive control.
- Per seed s in 0..9: group-hash split (`group` column, salted by s): TRAIN 50%, HOLD 10%, STREAM 40%.
  Group-disjoint, so duplicate flows never straddle a boundary.
- Model-fit subsample: 200,000 rows of TRAIN (RAM limit; 16 GB machine). Recorded as a limitation.
- "Stationary stream" = windows drawn IID without replacement from STREAM. Under this design the
  null (no traffic change) is TRUE BY CONSTRUCTION.

## Models (sklearn RandomForest, CPU — same learner as the repo's P-line; no neural training in E1)
- A: RF(100 trees, unlimited depth), seed s, subsample S1 of TRAIN.
- A2 ("equivalent retrain"): same config, RF seed s+1000, different subsample S2 of TRAIN.
- B_loop ("system adaptation, loop profile"): BoundedBuffer — 20k from TRAIN + 5k labelled STREAM
  rows (disjoint from evaluation windows), RF(100, unlimited depth), as `closed_loop_full.py`.
- B_daemon ("system adaptation, daemon profile"): same 25k rows, RF(100, max_depth=15), as
  `drift_daemon.py`. True labels are used (daemon uses predicted labels; this favours the system).
- Reported alongside: accuracy and macro-F1 on HOLD for every model, so "equally accurate" is checked.

## Profiles (mirror the code defaults)
- LOOP:   window W=1000 (disjoint IID draws, 300 per seed), alpha=0.05, reference = A's confidence
  on first 50,000 rows of S1 (in-sample, as the system does).
- DAEMON: W=100 (300 windows per seed), alpha=0.01, reference = A's confidences on 30 STREAM rows.

## Conditions (confidence = max predicted probability; test = `proteus.drift.detect_drift`)
- C0 VALIDITY: serving A, reference = A on HOLD (exchangeable with STREAM). Must give ~alpha.
- C1 NO-SWAP SYSTEM: serving A, system reference (LOOP: in-sample train; DAEMON: first-30).
- C2 SWAP-STALE (system behaviour): serving X in {A2, B_loop (LOOP) / B_daemon (DAEMON)},
  reference = A's system reference (not reset).
- C3 SWAP-FRESH (proposed repair): serving X, reference = X's confidence on HOLD.
- C4 POSITIVE CONTROL: serving A, Friday windows, C3-style reference. Must fire (~1).
- C5 DAEMON REFERENCE-DRAW: 200 independent 30-row reference draws per seed from STREAM, serving A,
  fire rate over 300 windows per draw => distribution of the CONDITIONAL false-alarm rate.

## Primary measure and thresholds (fixed now)
FAR = fraction of windows where the test fires. Intervals: two-level cluster bootstrap
(resample seeds, then windows within seed), 5,000 reps, percentile 95%. C5 clusters = reference draws.
- H2 (validity, must pass for anything to be reported): C0 FAR 95% CI contains alpha in both profiles,
  and C4 FAR >= 0.95.
- H1 (violation, PRIMARY): C2 FAR lower CI bound > 2*alpha for at least one swapped model in a profile.
- H3 (repair): C3 FAR upper CI bound <= alpha + 0.02 for every swapped model and profile.
- H5 (daemon reference lottery, secondary): share of reference draws with conditional FAR > 2*alpha.
  No threshold; reported as-is.
- If H2 fails the whole E1 is reported as INVALID, not as a finding.

## Stopping
Fixed design above. No seeds added or dropped after results. Failed/null outcomes are reported as such.

## Out of scope for E1 (later pre-registrations)
Second model family (step 4), cost of the repair and the naive "suppress alarms after swap" baseline
(step 5), prior-art search (step 8). Temporal (non-IID) windows are EXPLORATORY only, because real
traffic mix changes over time and the null is then not guaranteed.
