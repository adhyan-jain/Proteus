"""CLI entrypoint: runs the full pipeline and caches results to results/results.pkl."""
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from proteus.pipeline import run_pipeline


def main():
    def progress(frac, msg):
        print(f"[{frac*100:5.1f}%] {msg}")

    results = run_pipeline(progress_cb=progress)

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / "results.pkl", "wb") as f:
        pickle.dump(results, f)

    print(f"\nDone in {results['runtime_seconds']:.1f}s. "
          f"data_source={results['data_source']} gan_degraded={results['gan_degraded']}")
    print(f"Wrote {out_dir / 'results.pkl'}")


if __name__ == "__main__":
    main()
