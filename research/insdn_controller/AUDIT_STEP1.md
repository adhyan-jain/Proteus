# Step-1 audit: archived telemetry-contract study (2026-10-27)

Source: `tc/final_experiments.py` (extracted from proteus_repo_snapshot_20261017.tar.gz).
Verdict: **NO-GO as written.** The headline claims are true by construction, not measured.

1. **"Full Proteus 98.00% recall under degradation" is an oracle.** Lines 295-308 corrupt a
   random 20% of test rows, then "gate" them by indexing the same `corrupt_indices` and forcing
   prediction = 1. No detector runs, and the gate is handed the answer. The 22.7% FPR is just
   corrupted benign rows labelled attack.
2. **"Schema validation misses 6/6, gate catches 6/6" has no negative control.** Cases 2-4 carry
   identical payloads. Jitter is injected and checked inline in the test (lines 474-478). There
   is no clean case, so false-alarm rate is unmeasured, and a detector that blocks everything
   would also score 6/6.
3. **Single seed (42), single dataset.** This violates rule 6.
4. **The "9 OpenFlow-observable" set includes features OpenFlow 1.3 counters don't give**
   (`fwd_header_length`, CICFlowMeter-computed per-direction rates). It also includes `dst_port`,
   a known CICIDS2017 shortcut feature. The 97.55% figure therefore doesn't show deployability.
5. **What survives:** zero-filling unobserved features collapses a full-feature model (true, but a
   strawman), and a small-feature-subset model does well on CICIDS2017. The second is already
   known (Sarhan et al., standard NetFlow feature sets).

Why the plan's step 3 can't rescue it: threshold checks (staleness, jitter, negative delta) detect
exactly the defects they're defined for, so detection rates are tautological. The non-trivial
defects (unit or window mismatch) need distributional checks, which is drift detection and is
already covered. A real OpenFlow semantic-gap study (unidirectional entries, idle-timeout
splitting, mid-flow polling) needs packet-level traces or live Mininet (root). Neither is
available here: `data/raw` holds CSV flow records only.
