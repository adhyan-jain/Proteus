"""Generate every figure, table and number macro of the P1 paper from result artifacts.

    .venv/bin/python paper/p1/make_assets.py

Reads results/intervention_p0_S1_summary.json, results/intervention_p1_S1_B100_summary.json and
results/intervention_p1_S1_B100_decisions.json (+ optional S2/P2/P3 summaries). Writes
paper/p1/generated/*.tex (tables, numbers.tex) and paper/p1/figures/*.pdf. No number is typed in by
hand: the LaTeX prose refers to the macros defined in numbers.tex.
"""
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from proteus.intervention.serialize import from_jsonable, loads_strict  # noqa: E402

RES = ROOT / "results"
OUT_T = Path(__file__).parent / "generated"
OUT_F = Path(__file__).parent / "figures"
OUT_T.mkdir(exist_ok=True)
OUT_F.mkdir(exist_ok=True)

plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "figure.dpi": 150, "pdf.fonttype": 42})
C = {"FROZEN": "#7f7f7f", "REAL_ONLY": "#1b9e77", "CTRL-SMOTE": "#7570b3", "CTRL-THRESH": "#d95f02",
     "CTRL-ROS": "#1f78b4", "FIXED-SMOTE-1": "#e7298a", "FIXED-SMOTE-4": "#a6761d",
     "ALWAYS-SMOTE": "#666666", "FIDGATE-SMOTE": "#66a61e", "REAL_ONLY_ALL_LABELS": "#17becf"}
NAME = {"FROZEN": "Frozen", "REAL_ONLY": "Real-only", "CTRL-ROS": "Ctrl+duplication",
        "CTRL-THRESH": "Ctrl+threshold", "CTRL-SMOTE": "Ctrl+SMOTE", "FIXED-SMOTE-1": "Fixed SMOTE $\\rho{=}1$",
        "FIXED-SMOTE-4": "Fixed SMOTE $\\rho{=}4$", "ALWAYS-SMOTE": "Always-on SMOTE",
        "FIDGATE-SMOTE": "Fidelity-gated SMOTE", "NC1-DONOR-SMOTE": "NC1 wrong-class rows",
        "NC2-GAUSSIAN": "NC2 Gaussian", "NC3-SHUFFLE": "NC3 shuffled", "NC4-PLACEBO-DDOS": "NC4 placebo (DDoS)",
        "ABL-NO-STEP-TEST": "no step test", "ABL-I-EQ-A": "no need test ($I{:=}A$)",
        "ABL-NO-STEP-SAFETY": "no step safety", "ABL-KMAX1": "$K_{\\max}{=}1$", "ABL-MMD": "+MMD pre-filter",
        "ABL-POOLED": "pooled sel/gate", "ABL-NO-CANARY-CTRL": "ctrl, no canary",
        "ABL-NO-CANARY-REAL": "real-only, no canary", "REAL_ONLY_ALL_LABELS": "All-labels control",
        "ORACLE_DOSE": "Oracle dose (ref.)"}


def plain(label):
    """Plain-text version of a LaTeX arm label for matplotlib ticks."""
    return (label.replace("$\\rho{=}", "\u03c1=").replace("$K_{\\max}{=}1$", "K_max=1")
            .replace("$I{:=}A$", "I:=A").replace("$", ""))


def load(name):
    p = RES / name
    return from_jsonable(loads_strict(p.read_text())) if p.exists() else None


p0 = load("intervention_p0_S1_summary.json")
p1 = load("intervention_p1_S1_B100_summary.json")
dec = load("intervention_p1_S1_B100_decisions.json")
if p1 is None or p0 is None:
    sys.exit("P0/P1 summaries missing: run analyze_p1 first")
arms = p1["arm_table"]
H = p1["hypotheses"]


def nan(x):
    return x is None or (isinstance(x, float) and x != x)


def f(x, d=3):
    return "--" if nan(x) else f"{x:.{d}f}"


def ci(c, d=3):
    return "--" if nan(c["mean"]) else f"{c['mean']:.{d}f} [{c['lo']:.{d}f}, {c['hi']:.{d}f}]"


def tex(s):
    return s.replace("_", "\\_").replace("&", "\\&").replace("%", "\\%")


_DIG = dict(zip("0123456789", "zero one two three four five six seven eight nine".split()))


def mname(*parts):
    """LaTeX control-sequence name: letters only (digits spelled out), CamelCase after the first part."""
    out = []
    for i, p in enumerate(parts):
        p = re.sub(r"\d", lambda m: " " + _DIG[m.group()] + " ", str(p))
        words = re.sub(r"[^A-Za-z]+", " ", p).split()
        out.append("".join(w.capitalize() if (i or j) else w for j, w in enumerate(words)))
    return "".join(out)


# ------------------------------------------------------------------------------------ numbers.tex
macros = {}


def put(name, value):
    macros[name] = value


n_seeds = len(p1["provenance"]["seeds_present"])
put("nSeeds", str(n_seeds))
put("budget", str(p1["budget"]))
put("complete", "yes" if p1["provenance"]["complete"] else "NO")
put("prereg", "yes" if p1["provenance"]["all_preregistered"] else "NO")
put("verdictBranch", tex(p1["verdict"]["branch"]))
put("specVersion", p1["p1_spec_version"])
put("rulesHash", p1["provenance"]["p1_rules_sha256"][0][:16])
put("gitSha", p1["git_sha"][:7])
for a, row in arms.items():
    for key, label in (("r_recovery", "Rr"), ("shadow_candidate", "Sh"), ("r_recovery_matched", "Rm"), ("v13_auc", "Auc")):
        c = row[key]
        for stat in ("mean", "lo", "hi"):
            put(mname(label, a, stat), f(c[stat]))
    put(mname("Wall", a), f"{row['wall_clock_s']:.0f}")
    put(mname("Star", a), str(row["promotions"]["star"]))
    put(mname("Real", a), str(row["promotions"]["real_only"]))
    put(mname("Roll", a), str(row["promotions"]["rollbacks"]))
    put(mname("Chk", a), str(row["promotions"]["canary_checks"]))
    put(mname("Seeds", a), str(row["promotions"]["seeds_with_star"]))
    put(mname("Fits", a), str(row["candidate_fits"]))
for name in ("H2", "H3a", "H3b"):
    for stat in ("mean", "lo", "hi"):
        put(mname(name, stat), f(H[name]["diff"][stat]))
    put(mname(name, "rejected"), "rejected" if H[name]["rejected"] else "not rejected")
for a, v in H["H5"]["per_fixed"].items():
    for stat in ("mean", "lo", "hi"):
        put(mname("Hfive", a, stat), f(v["diff"][stat]))
put("hFourBreaches", str(H["H4"]["s_report_breaches"]))
put("hFourSeeds", str(H["H4"]["seeds_with_star_promotion"]))
fd = p1["flag_details"]
put("eligibleRuns", str(fd.get("controller_runs_with_eligible", 0)))
put("eligibleKzero", str(fd.get("controller_runs_k0", 0)))
put("goCleanRecall", f(fd.get("go_class_clean_row_recall_of_real_only_theta_R")))
sf = p1["step_filter_diagnostics"]
for k, v in sf.items():
    put(mname("Step", k), str(v))
put("probeWindows", str(p1["pre_drift_probe"]["windows"]))
put("probeNonempty", str(p1["pre_drift_probe"]["nonempty_region"]))
sh = fd["shadow_vs_real_only"]
for stat in ("mean", "lo", "hi"):
    put(mname("ShadowDiff", stat), f(sh["diff"][stat]))
put("pZeroOutcome", tex(p0["h1"]["outcome"]))
put("pZeroScope", tex(p0["h1"]["scope"]))
put("nRows", f"{p0['data']['cache']['n_rows']:,}".replace(",", "\\,"))
for k, v in p1["flags"].items():
    put(mname("Flag", k.split("_")[0]), "fired" if v else "not fired")
# --- extra quoted numbers --------------------------------------------------------------------
shv = p1["shadow_vs_real_only"]
for a in ("FIXED-SMOTE-1", "FIXED-SMOTE-4", "ALWAYS-SMOTE", "FIDGATE-SMOTE", "ORACLE_DOSE", "REAL_ONLY_ALL_LABELS", "ABL-POOLED"):
    for stat in ("mean", "lo", "hi"):
        put(mname("ShDiff", a, stat), f"{shv[a]['diff'][stat]:.4f}")
for a in ("FIXED-SMOTE-1", "FIXED-SMOTE-4", "ALWAYS-SMOTE", "FIDGATE-SMOTE", "ABL-POOLED", "REAL_ONLY_ALL_LABELS"):
    d = (p1["main_arms_vs_real_only"].get(a) or p1["ablations"].get(a, {}).get("vs_real_only") or p1["references"][a]["vs_real_only"])["diff"]
    for stat in ("mean", "lo", "hi"):
        put(mname("DepDiff", a, stat), f"{d[stat]:.4f}")
for a, row in arms.items():
    put(mname("Breach", a), str(row["safety"]["breaches"]))
    put(mname("NonBase", a), str(row["safety"]["nonbase_windows"]))
    for rname, n in row["tallies"].items():
        if rname.startswith("reasons:"):
            put(mname("N", a, rname.split(":")[1]), str(n))
ps = {}
for sub in ("all", "clean", "ambig"):
    num = den = 0.0
    for sd, m in p1["per_seed"]["REAL_ONLY"].items():
        r_ = m["recall"]["theta_R"][sub][str(fd["go_classes"][0])]
        if r_["n"] and r_["recall"] is not None:
            num += r_["recall"] * r_["n"]
            den += r_["n"]
    ps[sub] = (num / den if den else float("nan"), den)
put("recallAll", f(ps["all"][0]))
put("recallClean", f(ps["clean"][0]))
put("recallAmbig", f(ps["ambig"][0]))
put("shareAmbig", f"{100 * ps['ambig'][1] / ps['all'][1]:.1f}")
put("nGoRows", f"{int(ps['all'][1]):,}".replace(",", "\\,"))
zero = [s_ for s_, m in p1["per_seed"]["REAL_ONLY"].items() if (m["r_recovery"] or 0) == 0]
put("seedsNeverDeployed", str(len(zero)))
put("seedsNeverDeployedList", ", ".join(sorted(zero, key=int)))
put("gapRealOnly", f(arms["REAL_ONLY"]["shadow_candidate"]["mean"] - arms["REAL_ONLY"]["r_recovery_matched"]["mean"]))
put("totalWallMin", f"{sum(r['wall_clock_s'] for r in arms.values()) / 60:.0f}")
put("nArms", str(len(arms)))
ctrl_pos = {}
import json as _json
if dec:
    for arm in ("CTRL-SMOTE", "CTRL-ROS", "CTRL-THRESH"):
        pts, lcbs, nsyn = [], [], []
        for rows_ in dec["traces"].get(arm, {}).values():
            for r_ in rows_:
                for it in r_["search"]:
                    for c in it["candidates"]:
                        pts.append(c["gain_point"]); lcbs.append(c["gain_lcb"]); nsyn.append(c["n_syn_after"])
        a_ = np.array([x if x is not None else np.nan for x in pts], float)
        l_ = np.array([x if x is not None else np.nan for x in lcbs], float)
        put(mname("Cand", arm), str(len(a_)))
        put(mname("CandPos", arm), str(int((a_ > 0).sum())))
        put(mname("CandMaxLcb", arm), f"{np.nanmax(l_):.3f}")
        put(mname("CandMaxPt", arm), f"{np.nanmax(a_):.3f}")
        if arm != "CTRL-THRESH":
            put(mname("CandMedRows", arm), str(int(np.median(nsyn))))
gb = p1["gate_blocking_exploratory"]["REAL_ONLY"]
put("gbRejected", str(gb["rejected_with_report"]))
put("gbStableF", str(gb["failed_criteria"].get("stable_f1", 0)))
put("gbFprCur", str(gb["failed_criteria"].get("fpr_current", 0)))
put("gbFprStable", str(gb["failed_criteria"].get("fpr_stable", 0)))
put("gbUtil", str(gb["failed_criteria"].get("utility", 0)))
put("gbUtilOkEnvFail", str(gb["utility_ok_but_envelope_failed"]))
put("gbMedBenign", f"{gb['median_gate_benign_rows']:.0f}")
put("gbOneFp", f"{gb['one_extra_benign_fp_moves_fpr_by']:.4f}")
gba = p1["gate_blocking_exploratory"]["REAL_ONLY_ALL_LABELS"]
put("gbAllRejected", str(gba["rejected_with_report"]))
put("gbAllFprCur", str(gba["failed_criteria"].get("fpr_current", 0)))
put("gbAllFprStable", str(gba["failed_criteria"].get("fpr_stable", 0)))
put("gbAllMedBenign", f"{gba['median_gate_benign_rows']:.0f}")
s2 = load("intervention_p0_S2_summary.json")
if s2:
    put("sTwoOutcome", tex(s2["h1"]["outcome"]))
    put("sTwoScope", tex(s2["h1"]["scope"]))
    put("sTwoValid", "pass" if s2["validity"]["all_pass"] else "FAIL")
    put("sTwoGoCells", str(sum(v["n_go"] for b_ in s2["data_adequacy"]["per_budget"].values() for v in b_["per_seed"].values())))
    put("sTwoAssessSeeds", str(min(b_["n_seeds_assessable"] for b_ in s2["data_adequacy"]["per_budget"].values())))
    for b_, ag in s2["aggregate_by_budget"].items():
        for cond in ("FROZEN", "REAL_ONLY", "REAL_ONLY_ALL_LABELS"):
            put(mname("sTwoAuc", "B" + b_, cond), f(ag["recovery_auc"][cond]["mean"]))
    names2 = s2["data"]["class_names"] if s2["data"].get("class_names") else p1["class_names"]
    put("sTwoR", ", ".join(p1["class_names"][c] for c in s2["validity"]["v4_repairability"]["repairable_set"]))
(OUT_T / "numbers.tex").write_text("% generated by paper/p1/make_assets.py -- do not edit\n" + "\n".join(
    f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(macros.items())) + "\n")


# ------------------------------------------------------------------------------------ figures
def forest(ax, rows, xlabel, colors=None):
    ys = np.arange(len(rows))[::-1]
    for y, (lab, c, col) in zip(ys, rows):
        if nan(c["mean"]):
            continue
        ax.plot([c["lo"], c["hi"]], [y, y], color=col, lw=1.8)
        ax.plot([c["mean"]], [y], "o", color=col, ms=4)
    ax.axvline(0, color="#b00020", lw=0.8)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlabel(xlabel)
    ax.grid(axis="y", alpha=0)


main = [a for a in ["REAL_ONLY", "CTRL-ROS", "CTRL-THRESH", "CTRL-SMOTE", "FIXED-SMOTE-1", "FIXED-SMOTE-4",
                    "ALWAYS-SMOTE", "FIDGATE-SMOTE"] if a in arms]

fig, ax = plt.subplots(figsize=(5.2, 2.6))
forest(ax, [(plain(NAME[a]), p1["main_arms_vs_real_only"][a]["diff"], C.get(a, "#1f78b4"))
            for a in main if a != "REAL_ONLY"], "paired difference in R-recovery vs real-only (95% t-interval)")
fig.tight_layout()
fig.savefig(OUT_F / "fig_forest.pdf")
plt.close(fig)

fig, ax = plt.subplots(figsize=(5.2, 2.7))
curves = p1["curves_r_f1_by_post_window"]
for a in ["FROZEN", "REAL_ONLY", "CTRL-SMOTE", "CTRL-THRESH", "FIXED-SMOTE-4", "REAL_ONLY_ALL_LABELS"]:
    if a in curves:
        m = np.array(curves[a]["mean"], dtype=float)
        ax.plot(np.arange(5, 5 + len(m)), m, "--" if a == "REAL_ONLY_ALL_LABELS" else "-", color=C[a],
                label=plain(NAME[a]), lw=1.4)
ax.set_xlabel("post-drift window $t$")
ax.set_ylabel("R-recovery (E-F1)")
ax.set_ylim(0, 1)
ax.legend(fontsize=6.5, ncol=2, frameon=False)
fig.tight_layout()
fig.savefig(OUT_F / "fig_curves.pdf")
plt.close(fig)

fig, ax = plt.subplots(figsize=(5.2, 2.6))
sel = [a for a in ["REAL_ONLY", "CTRL-SMOTE", "CTRL-THRESH", "FIXED-SMOTE-4"] if a in arms]
w = 0.36
for i, a in enumerate(sel):
    for j, (key, hatch, lab) in enumerate((("r_recovery_matched", "", "deployed"), ("shadow_candidate", "//", "candidate"))):
        c = arms[a][key]
        if nan(c["mean"]):
            continue
        ax.bar(i + (j - 0.5) * w, c["mean"], w, color=C[a], alpha=0.55 if j == 0 else 1.0, hatch=hatch,
               edgecolor="white", label=lab if i == 0 else None)
        ax.errorbar(i + (j - 0.5) * w, c["mean"], yerr=[[c["mean"] - c["lo"]], [c["hi"] - c["mean"]]], color="k", lw=0.8, capsize=2)
ax.set_xticks(range(len(sel)))
ax.set_xticklabels([plain(NAME[a]) for a in sel], fontsize=7)
ax.set_ylabel("R-recovery (matched windows)")
ax.legend(frameon=False, fontsize=7)
fig.tight_layout()
fig.savefig(OUT_F / "fig_candidate_vs_deployed.pdf")
plt.close(fig)

REASONS = ["promoted", "no_affected_region", "utility_no_gain", "utility_inconclusive", "envelope_inconclusive", "envelope_violated"]
RCOL = ["#1b9e77", "#bdbdbd", "#6baed6", "#c6dbef", "#fdae6b", "#d62728"]
fig, ax = plt.subplots(figsize=(5.2, 2.7))
labs = [a for a in ["REAL_ONLY", "CTRL-SMOTE", "CTRL-THRESH", "FIXED-SMOTE-1", "FIXED-SMOTE-4", "ALWAYS-SMOTE", "FIDGATE-SMOTE"] if a in arms]
left = np.zeros(len(labs))
for r, col in zip(REASONS, RCOL):
    v = np.array([arms[a]["tallies"].get(f"reasons:{r}", 0) for a in labs], dtype=float)
    ax.barh(range(len(labs)), v, left=left, color=col, label=r.replace("_", " "), edgecolor="white", lw=0.3)
    left += v
ax.set_yticks(range(len(labs)))
ax.set_yticklabels([plain(NAME[a]) for a in labs], fontsize=7)
ax.invert_yaxis()
ax.set_xlabel("seed-window decisions")
ax.legend(fontsize=6, frameon=False, ncol=2, loc="lower right")
fig.tight_layout()
fig.savefig(OUT_F / "fig_gate_outcomes.pdf")
plt.close(fig)

STOPS = ["no_affected_region", "real_only_sufficient", "no_admissible", "no_safe_candidate", "no_gain", "k_max"]
SCOL = ["#bdbdbd", "#1b9e77", "#969696", "#fdae6b", "#6baed6", "#7570b3"]
fig, ax = plt.subplots(figsize=(5.2, 1.9))
labs = [a for a in ["CTRL-SMOTE", "CTRL-ROS", "CTRL-THRESH"] if a in arms]
left = np.zeros(len(labs))
for s, col in zip(STOPS, SCOL):
    v = np.array([arms[a]["tallies"].get(f"stop_reasons:{s}", 0) for a in labs], dtype=float)
    ax.barh(range(len(labs)), v, left=left, color=col, label=s.replace("_", " "), edgecolor="white", lw=0.3)
    left += v
ax.set_yticks(range(len(labs)))
ax.set_yticklabels([plain(NAME[a]) for a in labs], fontsize=7)
ax.invert_yaxis()
ax.set_xlabel("seed-window controller runs")
ax.legend(fontsize=6, frameon=False, ncol=3, loc="lower right")
fig.tight_layout()
fig.savefig(OUT_F / "fig_stops.pdf")
plt.close(fig)

if dec and "CTRL-SMOTE" in dec["traces"]:
    rows = dec["traces"]["CTRL-SMOTE"]
    seeds = sorted(rows, key=int)
    grid = np.zeros((len(seeds), len(rows[seeds[0]])))
    for i, s in enumerate(seeds):
        for j, r in enumerate(rows[s]):
            grid[i, j] = (4 if r["promoted"] and r["branch"] == "star" else 3 if r["promoted"] else
                          0 if r["reason"] == "no_affected_region" else 2 if str(r["reason"]).startswith("envelope") else 1)
    from matplotlib.colors import ListedColormap
    cm = ListedColormap(["#eeeeee", "#c6dbef", "#fdae6b", "#1b9e77", "#7570b3"])
    fig, ax = plt.subplots(figsize=(5.2, 2.3))
    ax.imshow(grid, cmap=cm, vmin=0, vmax=4, aspect="auto")
    ax.set_xticks(range(grid.shape[1]))
    ax.set_xticklabels([r["t"] for r in rows[seeds[0]]], fontsize=6)
    ax.set_yticks(range(len(seeds)))
    ax.set_yticklabels(seeds, fontsize=6)
    ax.set_xlabel("window $t$")
    ax.set_ylabel("seed")
    ax.grid(False)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, label=l) for c, l in zip(["#eeeeee", "#c6dbef", "#fdae6b", "#1b9e77", "#7570b3"],
              ["no affected region", "no demonstrated gain", "envelope not shown safe", "promoted (real-only)", "promoted (synthetic)"])],
              fontsize=5.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.28), ncol=3)
    fig.tight_layout()
    fig.savefig(OUT_F / "fig_decision_grid.pdf")
    plt.close(fig)

d2 = H["H2"]["per_seed"]
fig, ax = plt.subplots(figsize=(3.4, 2.4))
sd = sorted(d2, key=int)
ax.bar(range(len(sd)), [d2[s] if not nan(d2[s]) else 0 for s in sd],
       color=["#1b9e77" if (d2[s] or 0) > 0 else "#d62728" if (d2[s] or 0) < 0 else "#bdbdbd" for s in sd])
ax.axhline(0, color="k", lw=0.6)
ax.set_xticks(range(len(sd)))
ax.set_xticklabels(sd)
ax.set_xlabel("seed")
ax.set_ylabel("CTRL-SMOTE $-$ real-only")
fig.tight_layout()
fig.savefig(OUT_F / "fig_h2_per_seed.pdf")
plt.close(fig)

# P0 figure: recovery AUC by condition and budget
fig, ax = plt.subplots(figsize=(3.4, 2.4))
agg = p0["aggregate_by_budget"]
x = 0
ticks, labs0 = [], []
for b in sorted(agg, key=int):
    for cond, col in (("FROZEN", C["FROZEN"]), ("REAL_ONLY", C["REAL_ONLY"]), ("REAL_ONLY_ALL_LABELS", C["REAL_ONLY_ALL_LABELS"])):
        c = agg[b]["recovery_auc"][cond]
        ax.bar(x, c["mean"], color=col, alpha=0.9)
        ax.errorbar(x, c["mean"], yerr=[[c["mean"] - c["lo"]], [c["hi"] - c["mean"]]], color="k", lw=0.8, capsize=2)
        x += 1
    ticks.append(x - 2)
    labs0.append(f"B={b}")
    x += 0.6
ax.set_xticks(ticks)
ax.set_xticklabels(labs0)
ax.set_ylabel("P0 recovery AUC")
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=C[k], label=plain(NAME[k])) for k in ("FROZEN", "REAL_ONLY", "REAL_ONLY_ALL_LABELS")], fontsize=6, frameon=False)
fig.tight_layout()
fig.savefig(OUT_F / "fig_p0.pdf")
plt.close(fig)


# ------------------------------------------------------------------------------------ tables
def table(path, header, rows, align):
    body = "\n".join(" & ".join(r) + " \\\\" for r in rows)
    path.write_text("\\begin{tabular}{" + align + "}\n\\toprule\n" + " & ".join(header) + " \\\\\n\\midrule\n" + body + "\n\\bottomrule\n\\end{tabular}\n")


rows = []
for a in main:
    t = arms[a]
    rows.append([NAME[a], ci(t["r_recovery"]), f"{t['promotions']['star']}/{t['promotions']['real_only']}",
                 f"{t['promotions']['rollbacks']}", f"{t['safety']['breaches']}", f"{t['wall_clock_s']/60:.1f}"])
table(OUT_T / "tab_arms.tex", ["Arm", "R-recovery [95\\% CI]", "Promoted (syn/real)", "Rollbacks", "Breaches", "Min"], rows, "lcccrr")

rows = []
for name, label in (("H2", "H2 Ctrl+SMOTE $-$ real-only"), ("H3a", "H3a Ctrl+SMOTE $-$ Ctrl+dup."), ("H3b", "H3b Ctrl+SMOTE $-$ Ctrl+thr.")):
    h = H[name]
    st = "n/a (sequence stopped)" if not h.get("tested_under_sequence", True) else ("null rejected" if h["rejected"] else "not rejected")
    rows.append([label, ci(h["diff"]), st])
for a, v in H["H5"]["per_fixed"].items():
    rows.append([f"H5 Ctrl+SMOTE $-$ {NAME[a]}", ci(v["diff"]),
                 "n/a (sequence stopped)" if not H["H5"]["tested_under_sequence"] else ("non-inferior" if v["noninferior"] else "not established")])
table(OUT_T / "tab_hyp.tex", ["Test", "Paired difference [95\\% CI]", "Result"], rows, "lcc")

rows = []
for a in [k for k in arms if k.startswith("ABL-")] + [k for k in arms if k.startswith("NC")] + ["REAL_ONLY_ALL_LABELS", "ORACLE_DOSE"]:
    if a not in arms:
        continue
    t = arms[a]
    v = (p1["ablations"].get(a, {}).get("vs_ctrl_smote") or p1["negative_controls"].get(a) or
         p1["references"].get(a, {}).get("vs_real_only"))
    base = "vs Ctrl+SMOTE" if a.startswith("ABL-") else "vs real-only"
    rows.append([NAME.get(a, a), ci(t["r_recovery"]), base, ci(v["diff"]) if v else "--",
                 f"{t['promotions']['star']}/{t['promotions']['real_only']}"])
table(OUT_T / "tab_ablations.tex", ["Variant", "R-recovery", "Contrast", "Paired diff.", "Prom. (syn/real)"], rows, "lccc c".replace(" ", ""))

b = "100"
rows = []
for s, v in sorted(p0["data_adequacy"]["per_budget"][b]["per_seed"].items()):
    rows.append([s, str(v["n_cells"]), str(v["n_assessable"]), str(v["n_go"]),
                 ", ".join(p1["class_names"][c] for c in v["go_classes"]) or "--"])
table(OUT_T / "tab_p0.tex", ["Seed", "Cells", "Assessable", "GO cells", "GO class"], rows, "lcccl")

rows = [[tex(k), "fired" if v else "not fired"] for k, v in p1["flags"].items()]
table(OUT_T / "tab_flags.tex", ["Condition", "Status"], rows, "ll")
print("assets written:", sorted(p.name for p in OUT_T.iterdir()), sorted(p.name for p in OUT_F.iterdir()))
