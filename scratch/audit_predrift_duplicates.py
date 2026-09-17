"""Audit exact train/eval index overlap and feature duplication in pre-drift windows."""
import numpy as np
from proteus.evaluate_full import _load_day_split_data, N_WINDOWS, WINDOW_SIZE, DRIFT_AT_WINDOW
from proteus.closed_loop_full import RealDataReplaySource, ClosedLoopOrchestrator

def main():
    print("Loading day split data...")
    X_stable, y_stable, X_drifted, y_drifted, class_names = _load_day_split_data()
    print(f"X_stable total rows: {len(X_stable):,}")
    
    seed = 42
    rng = np.random.default_rng(seed)
    train_idx = set(rng.choice(len(X_stable), size=min(len(X_stable), 1_200_000), replace=False))
    
    # Replay source draws from X_stable
    replay_rng = np.random.default_rng(seed)
    total_eval_samples = 0
    overlapping_indices = 0
    
    split_rng = np.random.default_rng(123)
    
    for t in range(DRIFT_AT_WINDOW):
        idx = replay_rng.choice(len(X_stable), size=min(WINDOW_SIZE, len(X_stable)), replace=False)
        # 30% eval split
        n_eval = int(len(idx) * 0.3)
        perm = split_rng.permutation(len(idx))
        eval_idx = idx[perm[:n_eval]]
        
        eval_overlap = sum(1 for i in eval_idx if i in train_idx)
        total_eval_samples += len(eval_idx)
        overlapping_indices += eval_overlap
        print(f"Window {t}: {len(eval_idx)} eval rows, {eval_overlap} index overlap ({eval_overlap/len(eval_idx):.1%}) with 1.2M train pool")

    print(f"\nOverall Pre-Drift Eval Rows: {total_eval_samples}")
    print(f"Overlapping Index Count: {overlapping_indices} ({overlapping_indices/total_eval_samples:.1%})")
    print(f"Expected index overlap from random draw of 1.2M from {len(X_stable):,}: {1_200_000/len(X_stable):.1%}")

if __name__ == "__main__":
    main()
