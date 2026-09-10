"""Drift detector: KS-test on classifier prediction-confidence distributions."""
from scipy.stats import ks_2samp


def detect_drift(current_confidences, reference_confidences, alpha=0.05):
    statistic, p_value = ks_2samp(current_confidences, reference_confidences)
    fired = bool(p_value < alpha)
    return {"fired": fired, "statistic": float(statistic), "p_value": float(p_value),
            "alpha": alpha}
