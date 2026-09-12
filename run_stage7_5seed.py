"""Script to trigger the multi-hour 5-seed evaluation sweep for Stage 7.

Runs baseline, static-augmentation, and closed-loop orchestrator across 5 random seeds
with 95% confidence interval calculations per the paper-grade evaluation requirements.
"""
from proteus.evaluate_full import run_stage7

if __name__ == "__main__":
    run_stage7(n_seeds=5)
