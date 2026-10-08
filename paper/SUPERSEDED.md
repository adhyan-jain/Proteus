# Notice about `paper/main.tex` (the 2026-09 demo/Stage-7 paper)

The headline of `paper/main.tex` (closed-loop final macro-F1 0.1738 vs baseline 0.0294, "5.91×") comes from a protocol in which the
adapter receives oracle labels for 70% of every post-drift window. Its own ablation (`results/gan_ablation.json`) shows real-only
adaptation does as well or better, and the WGAN-GP checkpoint it used was trained on a random split of all days (leakage L1 in
`docs/INTERVENTION_SPEC.md`). **It is not evidence that synthetic data helps.** The preregistered investigation of that question is
`paper/p1/` (result: negative). Do not cite the 5.91× figure for synthetic intervention.
