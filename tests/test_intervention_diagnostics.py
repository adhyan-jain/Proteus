"""Exact-count tests for the P0 data diagnostics (SPEC v1.2 L.1 diagnostics) on hand-built data."""
import numpy as np

from proteus.intervention.diagnostics import (
    ambiguity_shares, ambiguous_groups, contamination_counts, label_conflict_report)

U = np.uint64


def _arr(groups, labels, pools):
    return (np.array(groups, dtype=U), np.array(labels, dtype=np.int64),
            np.array(pools, dtype=np.int8))


def test_ambiguous_groups_are_those_with_more_than_one_label():
    g, y, _ = _arr([1, 1, 2, 2, 3, 4, 4, 4], [0, 1, 5, 5, 7, 0, 0, 2], [1] * 8)
    assert ambiguous_groups(g, y).tolist() == [1, 4]
    assert ambiguous_groups(g[:0], y[:0]).tolist() == []


def test_label_conflict_report_separates_within_pool_and_across_pool_conflicts():
    # pools: 1 = pre, 2 = drift
    #  g10: BENIGN(0) pre, PortScan(5) drift          -> contradictory ACROSS pools
    #  g11: BENIGN pre and drift                       -> legal duplicate, no conflict
    #  g12: 0 and 1 inside the pre pool only           -> conflict WITHIN pre pool
    #  g13: 5 and 6 inside the drift pool only         -> conflict WITHIN drift pool
    #  g14: {0,1} pre, {0,1} drift                     -> ambiguous but same label sets across pools
    #  g15: {0} pre, {0,5} drift                       -> across-pool: drift has a label pre lacks
    g, y, pool = _arr(
        [10, 10, 11, 11, 12, 12, 13, 13, 14, 14, 14, 14, 15, 15, 15],
        [0, 5, 0, 0, 0, 1, 5, 6, 0, 1, 0, 1, 0, 0, 5],
        [1, 2, 1, 2, 1, 1, 2, 2, 1, 1, 2, 2, 1, 2, 2])
    rep = label_conflict_report(g, y, pool == 1, pool == 2)
    assert rep["n_groups_in_both_pools"] == 4                       # g10, g11, g14, g15
    assert rep["n_groups_with_different_labels_across_pools"] == 2  # g10 and g15
    assert rep["n_groups_with_conflicting_labels_within_pre_pool"] == 2      # g12, g14
    assert rep["n_groups_with_conflicting_labels_within_drift_pool"] == 3    # g13, g14, g15
    assert rep["n_groups_with_conflicting_labels_corpus"] == 5      # g10, g12, g13, g14, g15
    assert rep["n_rows_pre_pool_in_cross_pool_conflict_groups"] == 2     # one row of g10, one of g15
    assert rep["n_rows_drift_pool_in_cross_pool_conflict_groups"] == 3   # g10:1, g15:2
    # pre rows: g10:1 + g11:1 + g14:2 + g15:1 = 5; drift rows: g10:1 + g11:1 + g14:2 + g15:2 = 6
    assert rep["n_rows_pre_pool_in_both_pools"] == 5 and rep["n_rows_drift_pool_in_both_pools"] == 6


def test_label_conflict_report_with_disjoint_pools_is_all_zero():
    g, y, pool = _arr([1, 2, 3, 4], [0, 1, 2, 3], [1, 1, 2, 2])
    rep = label_conflict_report(g, y, pool == 1, pool == 2)
    assert rep["n_groups_in_both_pools"] == 0
    assert rep["n_groups_with_different_labels_across_pools"] == 0
    assert rep["n_groups_with_conflicting_labels_corpus"] == 0


def test_ambiguity_shares_per_class():
    g, y, _ = _arr([1, 1, 2, 3, 4, 5], [5, 0, 5, 5, 6, 6], [2] * 6)
    amb = ambiguous_groups(g, y)                                     # group 1 only
    out = ambiguity_shares(np.arange(6), g, y, amb, [5, 6, 9])
    assert out[5] == {"n_rows": 3, "n_ambiguous": 1, "share": 1 / 3}
    assert out[6]["n_ambiguous"] == 0 and out[6]["share"] == 0.0
    assert out[9]["n_rows"] == 0 and np.isnan(out[9]["share"])       # no rows: NaN, not 0
    assert ambiguity_shares(np.array([2, 3]), g, y, amb, [5])[5]["share"] == 0.0   # row subset


def test_contamination_counts_rows_of_the_learning_buffers_found_in_stable_partitions():
    # rows 0..5: groups; pools: rows 0-2 pre pool, rows 3-5 drift pool
    group = np.array([100, 101, 102, 100, 103, 104], dtype=U)
    pool = np.array([1, 1, 1, 2, 2, 2], dtype=np.int8)
    dest = {"S_report": np.array([100, 104], dtype=U), "S_gate": np.array([], dtype=U),
            "S_sel": np.array([101], dtype=U), "S_cal": np.array([], dtype=U),
            "D_ref": np.array([103], dtype=U)}
    prov = {"real": np.array([3, 4, 5]), "sel": np.array([0, 3]), "gate": np.array([], dtype=int)}
    out = contamination_counts(prov, pool, group, dest)
    # real: row3 (g100) and row5 (g104) are drift-pool rows duplicated in S_report; row4 (g103)
    # duplicates D_ref -- "training rows exactly duplicated in stable evaluation rows"
    assert out["real"]["S_report"] == {"drift_pool": 2, "pre_pool": 0}
    assert out["real"]["D_ref"] == {"drift_pool": 1, "pre_pool": 0}
    assert out["real"]["S_gate"] == {"drift_pool": 0, "pre_pool": 0} and out["real"]["n_rows"] == 3
    assert out["sel"]["S_report"] == {"drift_pool": 1, "pre_pool": 1}    # row0 (pre) and row3 (drift)
    assert out["gate"]["n_rows"] == 0 and out["gate"]["S_report"] == {"drift_pool": 0, "pre_pool": 0}
