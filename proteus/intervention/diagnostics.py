"""Evaluation-side data diagnostics for P0 (SPEC v1.2, section L.1 "Diagnostics").

Two things are reported, and neither ever gates the P0 outcome:

  * cross-pool duplicates: identical feature vectors (same group) that occur in both the pre-drift
    and the drift pool, and learning-buffer rows whose group also occurs in a stable-evaluation
    partition (S_report, S_gate, S_sel, S_cal, D_ref);
  * conflicting labels: groups that carry more than one label. Such vectors can be intrinsically
    unrepairable (no amount of data fixes a vector that is BENIGN on one day and an attack on
    another), so a GO whose class has a large ambiguous share needs interpretation.

Only the runner (which owns the dataset and the manifest) uses this module; nothing here is
reachable from the learner, promotion or conditions.
"""
import numpy as np

_NAN = float("nan")


def _unique_pairs(group, y):
    """Unique (group, label) pairs, sorted by group then label."""
    group, y = np.asarray(group), np.asarray(y)
    if not len(group):
        return group[:0], y[:0]
    order = np.lexsort((y, group))
    g, yy = group[order], y[order]
    keep = np.ones(len(g), dtype=bool)
    keep[1:] = (g[1:] != g[:-1]) | (yy[1:] != yy[:-1])
    return g[keep], yy[keep]


def ambiguous_groups(group, y):
    """Sorted group values that carry more than one distinct label in the given rows."""
    g, _ = _unique_pairs(group, y)
    if not len(g):
        return g
    values, counts = np.unique(g, return_counts=True)
    return values[counts > 1]


def label_conflict_report(group, y, pre_mask, drift_mask):
    """Counts of conflicting-label groups: anywhere in the corpus, within each temporal pool, and
    across the two pools (a group present in both pools whose label SETS differ)."""
    group, y = np.asarray(group), np.asarray(y)
    amb_all = ambiguous_groups(group, y)
    amb_pre = ambiguous_groups(group[pre_mask], y[pre_mask])
    amb_drift = ambiguous_groups(group[drift_mask], y[drift_mask])

    gp, yp = _unique_pairs(group[pre_mask], y[pre_mask])
    gd, yd = _unique_pairs(group[drift_mask], y[drift_mask])
    both = np.intersect1d(np.unique(gp), np.unique(gd))
    n_cross = 0
    cross_conflict = both[:0]
    if len(both):
        gu, _ = _unique_pairs(np.concatenate([gp, gd]), np.concatenate([yp, yd]))

        def per_group(g):
            return np.unique(g[np.isin(g, both)], return_counts=True)[1]
        n_pre, n_dr, n_union = per_group(gp), per_group(gd), per_group(gu)
        differs = ~((n_pre == n_dr) & (n_dr == n_union))     # label sets are not identical
        cross_conflict = both[differs]
        n_cross = int(len(cross_conflict))

    def rows_in(groups, mask):
        return int(np.isin(group[mask], groups).sum())

    return {
        "n_groups_pre_pool": int(len(np.unique(group[pre_mask]))),
        "n_groups_drift_pool": int(len(np.unique(group[drift_mask]))),
        "n_groups_in_both_pools": int(len(both)),
        "n_rows_pre_pool_in_both_pools": rows_in(both, pre_mask),
        "n_rows_drift_pool_in_both_pools": rows_in(both, drift_mask),
        "n_groups_with_conflicting_labels_corpus": int(len(amb_all)),
        "n_groups_with_conflicting_labels_within_pre_pool": int(len(amb_pre)),
        "n_groups_with_conflicting_labels_within_drift_pool": int(len(amb_drift)),
        "n_groups_with_different_labels_across_pools": n_cross,
        "n_rows_pre_pool_in_cross_pool_conflict_groups": rows_in(cross_conflict, pre_mask),
        "n_rows_drift_pool_in_cross_pool_conflict_groups": rows_in(cross_conflict, drift_mask),
    }


def ambiguity_shares(rows, group, y, ambiguous, classes):
    """Per class: the share of its rows (among `rows`) whose group carries another label."""
    rows = np.asarray(rows, dtype=np.int64)
    out = {}
    for c in classes:
        sel = rows[y[rows] == c]
        n = int(len(sel))
        k = int(np.isin(group[sel], ambiguous).sum()) if n else 0
        out[int(c)] = {"n_rows": n, "n_ambiguous": k, "share": (k / n) if n else _NAN}
    return out


def contamination_counts(prov, pool_of, group, dest_groups):
    """For each learning buffer (real/sel/gate): how many rows have a group that also occurs in
    each destination partition, split by the pool the row came from (1 = pre, 2 = drift).
    `real` -> S_* is the number of training rows exactly duplicated in stable evaluation rows."""
    out = {}
    for part in ("real", "sel", "gate"):
        rows = np.asarray(prov[part], dtype=np.int64)
        entry = {"n_rows": int(len(rows))}
        for dest, groups in dest_groups.items():
            hit = np.isin(group[rows], groups) if len(rows) else np.zeros(0, dtype=bool)
            pools = pool_of[rows] if len(rows) else np.zeros(0, dtype=np.int8)
            entry[dest] = {"drift_pool": int((hit & (pools == 2)).sum()),
                           "pre_pool": int((hit & (pools == 1)).sum())}
        out[part] = entry
    return out
