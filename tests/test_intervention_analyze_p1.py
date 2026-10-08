"""analyze_p1: cell maths, fixed-sequence gating, reconciliation with a P0 run, strict output."""
import json
from dataclasses import replace

import numpy as np
import pytest

import proteus.intervention.analyze_p1 as an
import proteus.intervention.p0 as p0
import proteus.intervention.p1 as p1
from proteus.intervention.conditions import RealOnly
from proteus.intervention.diagnostics import ambiguous_groups
from proteus.intervention.learner import CandidateBuilder
from proteus.intervention.p1_spec import P1Criteria
from proteus.intervention.protocol import StreamReplay, build_partitions
from proteus.intervention.serialize import dumps_strict, from_jsonable, loads_strict
from tests.test_intervention_p1 import CFG, PARAMS
from tests.test_intervention_protocol import _make_data

ARMS = ["FROZEN", "REAL_ONLY", "CTRL-ROS", "CTRL-THRESH", "CTRL-SMOTE", "FIXED-SMOTE-1",
        "FIXED-SMOTE-4", "NC1-DONOR-SMOTE", "ABL-NO-CANARY-REAL", "ORACLE_DOSE"]
CRIT = replace(P1Criteria(), seeds=(0, 1))


def test_window_r_f1_uses_only_repairable_classes_with_enough_support():
    cells = [[3, 3, 10], [3, 0, 10], [4, 4, 8], [5, 5, 2], [0, 0, 50]]    # class 5 has support 2
    k = 6
    f1_3, f1_4 = 2 * 10 / (2 * 10 + 10), 1.0
    assert an.window_r_f1(cells, [3, 4, 5], 5, k) == pytest.approx((f1_3 + f1_4) / 2)
    assert an.window_r_f1(cells, [5], 5, k) != an.window_r_f1(cells, [5], 5, k)      # nan
    rec, n = an.recall_of(cells, 3, k)
    assert rec == 0.5 and n == 20


def test_reject_is_the_lower_bound_above_zero_and_the_verdict_follows_the_sequence():
    mk = lambda lo: {"diff": {"lo": lo}}
    assert an.reject(mk(0.001)) and not an.reject(mk(0.0)) and not an.reject(mk(float("nan")))
    prov = {"complete": True, "all_preregistered": True}
    h = {"H2": {"rejected": False}, "H3a": {"rejected": False}, "H3b": {"rejected": False}}
    assert an.mechanical_verdict(h, {"F2": True}, prov)["branch"].startswith("NEGATIVE")
    assert not an.mechanical_verdict(h, {}, prov)["p2_unlocked"]
    h["H2"]["rejected"] = True
    assert an.mechanical_verdict(h, {}, prov)["branch"].startswith("PARTIAL")
    h["H3a"]["rejected"] = h["H3b"]["rejected"] = True
    v = an.mechanical_verdict(h, {}, prov)
    assert v["branch"].startswith("POSITIVE") and v["p2_unlocked"]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    data = _make_data()
    out = tmp_path_factory.mktemp("p1_an")
    amb = ambiguous_groups(data.group, data.y)
    for seed in (0, 1):
        p1.run_seed(data, seed, ARMS, CRIT, PARAMS, CFG, [4, 5], out, amb, progress=lambda m: None)
    # a stand-in "frozen P0": the same REAL_ONLY condition run through the P0 runner
    p0dir = tmp_path_factory.mktemp("p0_stub")
    runs = []
    for seed in (0, 1):
        manifest = build_partitions(data, replace(CFG, budget=100), seed)
        aud = p0.Auditor(data, manifest, amb)
        st = p0.TrackedState(data, manifest)
        st.ingest(next(iter(StreamReplay(manifest))))
        base = CandidateBuilder(PARAMS, seed).build_base(st.view())
        k = len(data.class_names)
        stable = [int(c) for c in np.unique(data.y[manifest.ref_idx])]
        bs = p0.s_report_stats(base, data, manifest, stable, 0, k, PARAMS.s_min)
        runs.append(p0.run_condition(data, manifest, RealOnly(), PARAMS, base, bs, aud,
                                     p0.drift_classes_of(data, CFG)))
    (p0dir / "intervention_p0_S1_summary.json").write_text(
        dumps_strict({"data": {"cache": {"class_names": list(data.class_names)}}}))
    (p0dir / "intervention_p0_S1_B100.json").write_text(dumps_strict({"runs": runs}))
    return data, out, p0dir


@pytest.fixture(scope="module")
def summary(world):
    data, out, p0dir = world
    docs = an.load_seed_files(out, scenario="T")
    return an.analyze(docs, p0dir, criteria=CRIT, params=PARAMS)


def test_analysis_reconciles_with_the_p0_real_only_run(summary):
    rec = summary["p0_reconciliation"]
    assert rec["seeds"] == [0, 1] and rec["identical"] and not rec["problems"]


def test_structure_gating_and_flags(summary):
    h = summary["hypotheses"]
    assert set(h) == {"H2", "H3a", "H3b", "H5", "H4"}
    assert h["H3a"]["tested_under_sequence"] == h["H2"]["rejected"]
    assert h["H3b"]["tested_under_sequence"] == (h["H2"]["rejected"] and h["H3a"]["rejected"])
    assert h["H2"]["contrast"] == "CTRL-SMOTE - REAL_ONLY (R-recovery)"
    assert set(h["H5"]["per_fixed"]) == {"FIXED-SMOTE-1", "FIXED-SMOTE-4"}
    assert set(summary["flags"]) >= {"F2_H2_not_rejected", "F4_unsafe_or_rollbacks",
                                     "F8_degenerate_controller", "F10_certification_bottleneck",
                                     "F11_negative_control_beats_real_only"}
    assert summary["provenance"]["repairable_set_R"] == [4, 5]
    assert summary["provenance"]["complete"] and not summary["provenance"]["all_preregistered"]
    assert summary["verdict"]["complete_and_preregistered"] is False
    assert summary["pre_drift_probe"]["windows"] > 0
    t = summary["arm_table"]["REAL_ONLY"]
    assert t["r_recovery"]["n"] == 2 and t["safety"]["breaches"] >= 0


def test_paired_difference_is_the_per_seed_difference_with_a_t_interval(summary):
    d = summary["hypotheses"]["H2"]
    ps = list(d["per_seed"].values())
    assert d["diff"]["mean"] == pytest.approx(np.mean(ps))
    if len(ps) == 2 and np.std(ps, ddof=1) > 0:
        assert d["diff"]["half_width"] == pytest.approx(
            12.706204736 * np.std(ps, ddof=1) / np.sqrt(2), rel=1e-6)


def test_output_is_strict_json_and_roundtrips(summary, tmp_path):
    text = dumps_strict(summary)
    again = from_jsonable(loads_strict(text))
    assert again["kind"] == "p1_summary" and set(again["arm_table"]) == set(ARMS)
    assert "curves_r_f1_by_post_window" in again and len(again["curves_r_f1_by_post_window"]["REAL_ONLY"]["mean"]) == 4
