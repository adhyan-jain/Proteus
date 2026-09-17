"""Diagnostic script to inspect fidelity gate MMD scores and admission decisions in demo pipeline."""
import numpy as np
from proteus.pipeline import run_pipeline

def main():
    print("Running demo pipeline diagnostic...")
    results = run_pipeline()
    gate_log = results.get("closed_loop_gate_log", [])
    print(f"\nTotal fidelity gate check calls: {len(gate_log)}")
    print(f"{'Step':<6} {'Class':<12} {'MMD Score':<12} {'Threshold':<12} {'Admitted':<10}")
    print("-" * 55)
    for entry in gate_log:
        step = entry.get("step")
        cls = entry.get("class", entry.get("class_name", "N/A"))
        score = entry.get("mmd_score", entry.get("score", -1.0))
        thresh = entry.get("threshold", 0.25)
        admitted = entry.get("admitted", False)
        print(f"{step:<6} {str(cls):<12} {score:<12.4f} {thresh:<12.4f} {str(admitted):<10}")

if __name__ == "__main__":
    main()
