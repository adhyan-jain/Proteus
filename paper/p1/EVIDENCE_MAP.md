# Evidence map for `paper/p1/main.tex`

Every number in the paper is a macro defined in `generated/numbers.tex`, produced by `make_assets.py` from the files below; nothing is typed by hand.

| Paper element | Generated file | Source artifact (under `results/`) |
|---|---|---|
| Abstract / Results numbers (`\HTwo*`, `\Rr*`, `\Sh*`, `\Rm*`, `\DepDiff*`, `\ShDiff*`, `\Breach*`, `\Star*`, `\Chk*`, `\Roll*`, `\N<arm><reason>`) | `numbers.tex` | `intervention_p1_S1_B100_summary.json` (from `results/p1/intervention_p1_S1_B100_seed{0..9}.json`) |
| Controller statistics (`\Cand*`, `\eligible*`, `\Step*`) | `numbers.tex` | `intervention_p1_S1_B100_decisions.json`, `…_summary.json` |
| Gate blocking (`\gb*`) | `numbers.tex` | `…_summary.json` → `gate_blocking_exploratory` (exploratory) |
| Ambiguity (`\recall*`, `\shareAmbig`, `\nGoRows`) | `numbers.tex` | `…_summary.json` → `per_seed[*].recall` |
| P0 (`\pZero*`, Fig. 1, Table I) | `numbers.tex`, `tab_p0.tex`, `fig_p0.pdf` | `intervention_p0_S1_summary.json` |
| S2 gate (`\sTwo*`) | `numbers.tex` | `intervention_p0_S2_summary.json` |
| Table II hypotheses | `tab_hyp.tex` | `…_summary.json` → `hypotheses` |
| Table III main arms | `tab_arms.tex` | `…_summary.json` → `arm_table` |
| Table IV controls/ablations/references | `tab_ablations.tex` | `…_summary.json` → `ablations`, `negative_controls`, `references` |
| Fig. 2 forest | `fig_forest.pdf` | `main_arms_vs_real_only` |
| Fig. 3 stops | `fig_stops.pdf` | `arm_table[*].tallies` (`stop_reasons:*`) |
| Fig. 4 candidate vs deployed | `fig_candidate_vs_deployed.pdf` | `arm_table[*].r_recovery_matched`, `shadow_candidate` |
| Fig. 5 gate outcomes | `fig_gate_outcomes.pdf` | `arm_table[*].tallies` (`reasons:*`) |
| Fig. 6 decision grid | `fig_decision_grid.pdf` | `…_decisions.json` |
| Fig. 7 curves | `fig_curves.pdf` | `curves_r_f1_by_post_window` |
| Provenance statements (rules hash, git SHA, code hashes) | `numbers.tex` (`\rulesHash`, `\gitSha`) | seed-file headers; `results/p1_leakage_audit.json`, `results/p1_audit_sensitivity.json` |
