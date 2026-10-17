# driftref — does the drift alarm survive a model change? (closure report, 2026-10-17)

**Verdict: no publishable novelty. Research closed per the owner's rule ("if not, close the research
and make it a product and archive it").** What survives is a real, measured product bug and its fix.

Pre-registrations (committed before results): `PREREG_E1.md` (commit 3a92250), `PREREG_E2.md`
(commit a66f4bd; E2 was written AFTER E1 results, so it tests a hypothesis E1 generated).
Code: `run_e1.py`, `analyze_e1.py`, `run_e2.py`, `analyze_e2.py`. Raw results: `results/driftref/`.
Note: the term "chimera strategy" was not defined anywhere in the repo or session; it was interpreted as
"combine two separately known results into a defect neither covers alone". Not confirmed with the owner.

## 1. Invariant tested (step 1-2)
I1: "A drift alarm reflects a change in the traffic, not a change in which model is serving."
Oracle (metamorphic, no labels): serve IID windows from a pool that is exchangeable with the reference,
so the null is true by construction; swap the model; count KS alarms. Other candidates (I2 train/test
overlap, I3 fidelity-gate unit/order invariance, I4 prefix-rebuild of the intervention harness) were not
run: I2 is retracted-number territory, I3 has little harm, I4 was expected to pass.

## 2. Results

### E1 (10 seeds, RF, CICIDS2017 Mon-Thu, `results/driftref/e1_analysis.json`)
| Condition | Profile | Alarm rate on unchanged traffic [95% cluster CI] |
|---|---|---|
| Equivalent retrain (same size), stale ref | LOOP a=0.05 / DAEMON a=0.01 | 0.000 / 0.000 |
| System's bounded-buffer model (25k rows), stale in-sample ref | LOOP | **0.556 [0.454, 0.662]** |
| same, stale but unbiased hold-out ref (removes the in-sample factor) | LOOP | 0.154 [0.094, 0.225] |
| System's bounded-buffer model (depth 15), first-30 stale ref | DAEMON | **1.000 [1.000, 1.000]** (every reference draw, every window) |
| Reference recomputed for the serving model (repair) | both | 0.000 / 0.002 [0, 0.005] |
| Positive control (Friday, real drift) | both | 1.000 / 0.979 |
Accuracy on HOLD is nearly equal (A 0.9993 vs adapted 0.9983); mean confidence differs (0.9988 vs 0.9968/0.9965).
Pre-registered H1 PASS, H3 PASS, **H2 FAIL on its letter**: the validity control gives 0.000, not ~alpha,
because tied confidences make KS conservative. Guarantee is "<= alpha", my "~alpha" wording was wrong.
Cause separation: the equivalent retrain is harmless, so the swap alone is not the cause; the adapted
model's smaller training set (25k vs 200k) lowers its confidence; the in-sample reference adds about 0.40
on top (0.556 vs 0.154).

### E2 (5 seeds, RF + MLP-64 + MLP-512, retrain sizes 5k/25k/100k/200k; `e2_analysis.json`)
H6 formally passes (N=25k stale FAR: RF 0.234 [0.156, 0.321]; MLP64 1.000; MLP512 1.000), but
**H7 FAILS for both MLPs**: the equivalent retrain (N=200k, new seed) already alarms on 0.981 (MLP64) and
0.577 (MLP512) of windows. Under the pre-registered rule those families are INVALID, leaving RF alone,
so H6 is not satisfiable and the pre-registered decision is "specific to RF-on-small-buffer; close".
H8 (repair) holds except mild over-alarm 0.06 for MLP64 at N=5k and 25k and MLP512 at N=5k (upper CI
0.079-0.101 > 0.07). H9 PASS (all 1.000).
EXPLORATORY reading (post hoc, not a finding): KS on max-softmax confidences with n=1000 vs a 20k reference
detects tiny seed-to-seed shifts in NNs (mean confidence 0.9991 vs 0.9992). That is statistical
over-sensitivity, a known property of large-n two-sample tests, not a new defect.

## 3. Claim-to-evidence table
| Claim | Evidence | Provenance |
|---|---|---|
| Proteus' loop/daemon alarm on unchanged traffic after their own adaptation (RF) | E1 H1, `e1_analysis.json` | measured, real CICIDS2017 flows, system-internal; no labels from humans or models |
| Recomputing the reference for the serving model removes it | E1 H3 / E2 H8 | same |
| It is not caused by a swap per se | A2 control = 0.000 | same |
| The Stage-7 closed-loop's alarms in all 10 post-drift windows cannot be attributed to real drift alone | inference from E1 + `stage7_evaluation.json` drift_events (one seed) | system-internal, inferential |
| Defect is a property of the retrain-on-alarm DESIGN across learners | NOT SUPPORTED (E2 H7 invalidates MLPs) | n/a |

## 4. Ranked contributions and what is NOT claimed
1. (Engineering, real) Proteus' drift trigger self-excites after adaptation; repair = per-model-version
   reference (recompute on hold-out at swap). Cost: one extra scoring pass on a held-out sample per swap.
2. (Method note) a metamorphic "swap the model, hold traffic fixed" oracle with a true-by-construction null.
3. (Negative) the generalisation to other learners did not validate; the MLP behaviour is test over-sensitivity.
Not claimed: novelty of the principle (baseline per model version is practitioner guidance); a guarantee
beyond "exchangeable traffic"; any result on InSDN or live traffic; any human annotation (none done);
the effect of the daemon's predicted-label retraining (true labels used, favouring the system).

## 5. Prior art (step 8) — read only as search snippets, NOT full texts
- Rabanser et al., "Failing Loudly" (arXiv 1810.11953): two-sample tests on classifier outputs for shift detection; we use that test, not new.
- MLflow monitoring guidance: store baseline distributions per model version; the repair is this practice.
- DataEval `DriftUncertainty` docs: reference stays fixed unless an update strategy is set; same observation at library level.
- arXiv 2608.19488 "When to Retrain": retraining-policy study, detector fragility; does not isolate retrain-induced alarms in what I saw.
- ScienceDirect S0950705125020799: sensitive detector + short retrain lag causes repeated ineffective retraining; closest to our failure loop, different mechanism.
- arXiv 2508.00042 (label-free drift assessment), arXiv 2609.27865 (diagnosis of drift types): adjacent.
- Cys 5528 (K-Means + RF IDS with drift detection, 1.14% false alarm on NSL-KDD): IDS drift trigger, no post-adaptation analysis seen.
To our knowledge no source in this bounded search measures retrain-induced KS alarms with a swap-null; absence in a
bounded search is not proof of novelty, and the principle is known.

## 6. Limitations / what would change the conclusion
- One dataset (CICIDS2017), RF at 200k-row fits (RAM limit), IID window null; real traffic is temporally correlated.
- E1 H2 failed on its letter; the validity argument rests on KS being conservative under ties.
- E2 was written after seeing E1; it is not independent confirmation.
- A validity-passing NN design (e.g. practical-significance threshold or calibrated confidence) could show a
  design-level effect; that needs a new pre-registration and is not planned.
- No cost comparison against the naive fix "suppress alarms after a swap", no property test of the
  alpha-guarantee: both skipped because E2 closed the line.
- RF is CPU sklearn (as elsewhere in this repo); MLPs ran on CUDA.
