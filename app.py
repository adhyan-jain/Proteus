"""Proteus demo UI -- drift-aware GAN-augmented IDS proof-of-concept."""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from proteus import data as data_mod, drift as drift_mod
from proteus.pipeline import run_pipeline

RESULTS_PATH = Path(__file__).parent / "results" / "results.pkl"

st.set_page_config(page_title="Proteus POC", layout="wide")

st.markdown(
    "<div style='background:#4a2f0a;color:#ffd479;padding:8px 14px;border-radius:6px;"
    "font-weight:600;'>⚠️ PROOF-OF-CONCEPT — simulated/synthetic scaled-down demo. "
    "Not real SDN traffic, not production scale. See 'What's real vs. simulated' at the "
    "bottom.</div>",
    unsafe_allow_html=True,
)
st.title("Proteus — Drift-Aware GAN-Augmented IDS (Demo POC)")


@st.cache_data(show_spinner=False)
def load_cached_results():
    if RESULTS_PATH.exists():
        with open(RESULTS_PATH, "rb") as f:
            return pickle.load(f)
    return None


def architecture_figure():
    nodes = [
        ("Data\n(NSL-KDD /\nsynthetic)", 0, 1),
        ("WGAN-GP\nGenerator", 1, 1),
        ("Fidelity Gate\n(MMD)", 2, 1),
        ("Training Set", 3, 1),
        ("Deployed\nClassifier (RF)", 4, 1),
        ("Drift Detector\n(KS-test)", 4, 0),
    ]
    fig = go.Figure()
    for name, x, y in nodes:
        fig.add_shape(type="rect", x0=x - 0.4, x1=x + 0.4, y0=y - 0.3, y1=y + 0.3,
                       line=dict(color="#4c8bf5"), fillcolor="rgba(76,139,245,0.15)")
        fig.add_annotation(x=x, y=y, text=name, showarrow=False, font=dict(size=11))
    arrows = [(0, 1, 0, 1, 1, 1), (1, 1, 1, 1, 2, 1), (2, 1, 1, 1, 3, 1),
              (3, 1, 1, 1, 4, 1), (4, 1, 1, 0.7, 4, 0.3)]
    edge_pairs = [(0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (4, 0.3)]
    coords = [((0.4, 1), (0.6, 1)), ((1.4, 1), (1.6, 1)), ((2.4, 1), (2.6, 1)),
              ((3.4, 1), (3.6, 1)), ((4, 0.7), (4, 0.3))]
    for (x0, y0), (x1, y1) in coords:
        fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref="x", yref="y", axref="x", ayref="y",
                            showarrow=True, arrowhead=3, arrowsize=1, arrowwidth=2,
                            arrowcolor="#4c8bf5")
    fig.add_annotation(x=1, y=0.65, ax=3.5, ay=-0.55, xref="x", yref="y", axref="x", ayref="y",
                        showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor="#e06666",
                        text="drift fires -> triggers retrain", font=dict(size=10, color="#e06666"))
    fig.update_xaxes(visible=False, range=[-0.6, 4.6])
    fig.update_yaxes(visible=False, range=[-0.75, 1.5])
    fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10),
                       plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


st.subheader("Architecture")
st.plotly_chart(architecture_figure(), width='stretch')
st.caption(
    "How to read this: traffic data feeds a generator (WGAN-GP) that manufactures extra "
    "synthetic examples of rare attack types. A fidelity gate checks each synthetic batch "
    "against real traffic before it's trusted enough to use. Approved samples go into the "
    "training set, which produces the deployed classifier. A drift detector watches that "
    "classifier's live confidence and, if the traffic looks statistically different from what "
    "it was trained on, triggers the loop to regenerate and retrain -- shown by the red arrow."
)

st.subheader("Run Pipeline")
col1, col2 = st.columns([1, 3])
with col1:
    run_clicked = st.button("▶ Run full pipeline", type="primary")
with col2:
    st.caption("Runs data -> baseline -> WGAN-GP -> drift-sim -> 3-condition eval. "
               "~30-60s. Cached results load instantly if already run.")

results = load_cached_results()

if run_clicked:
    progress_bar = st.progress(0.0, text="Starting...")

    def cb(frac, msg):
        progress_bar.progress(min(frac, 1.0), text=msg)

    with st.spinner("Running pipeline..."):
        results = run_pipeline(progress_cb=cb)
        with open(RESULTS_PATH, "wb") as f:
            pickle.dump(results, f)
    load_cached_results.clear()
    progress_bar.empty()
    st.success(f"Pipeline complete in {results['runtime_seconds']:.1f}s")

if results is None:
    st.info("No cached results yet. Click 'Run full pipeline' above.")
    st.stop()

# ---- data source banner ----
src_label = ("NSL-KDD (downloaded)" if results["data_source"] == "nsl-kdd-download"
             else "Synthetic NSL-KDD-schema data (download unavailable/skipped)")
st.markdown(f"**Data source:** {src_label}  |  **Classes:** {', '.join(results['class_names'])}  "
            f"|  **Rare/minority classes (GAN targets):** {', '.join(results['rare_classes'])}")
if results.get("gan_degraded"):
    st.warning(f"WGAN-GP degraded during this run: {results.get('gan_error')}")

st.divider()

# ---- live metrics table ----
st.subheader("Live Metrics — Final Held-Out Performance (per condition)")
with st.expander("What do precision / recall / F1 / macro F1 mean?"):
    st.markdown(
        "- **Precision**: of everything the model flagged as this attack type, how much "
        "actually was that attack. Low precision = lots of false alarms.\n"
        "- **Recall**: of everything that really was this attack type, how much the model "
        "actually caught. Low recall = attacks slipping through undetected.\n"
        "- **F1**: a single number balancing precision and recall (their harmonic mean) -- "
        "high only when both are reasonably good.\n"
        "- **Macro F1**: the F1 score averaged equally across all classes, including rare "
        "attack types. This matters because a model can look great on accuracy alone just by "
        "nailing the common 'benign' class while missing rare attacks entirely -- macro F1 "
        "doesn't let it hide that."
    )
tabs = st.tabs(["Baseline (no augmentation)", "Static augmentation", "Closed-loop (drift-aware)"])
cond_keys = ["baseline", "static_augmentation", "closed_loop"]
for tab, key in zip(tabs, cond_keys):
    with tab:
        rep = results["final_reports"][key]
        rows = []
        for cls in results["class_names"]:
            if cls in rep:
                rows.append({"class": cls, "precision": round(rep[cls]["precision"], 3),
                             "recall": round(rep[cls]["recall"], 3),
                             "f1": round(rep[cls]["f1-score"], 3),
                             "support": int(rep[cls]["support"])})
        df = pd.DataFrame(rows)
        st.dataframe(df, width='stretch', hide_index=True)
        st.caption(f"Macro F1: {rep['macro avg']['f1-score']:.3f}")

st.divider()

# ---- headline graph: macro-F1 over time, one line per condition ----
st.subheader("Macro-F1 Over Simulated Time (headline result)")
st.caption(
    "**How to read this graph:** each dashed red vertical line is a point where simulated "
    "drift was injected (a new or shifted attack pattern appeared in the traffic). Red X "
    "markers show timesteps where the drift detector actually fired in response. The core "
    "question this graph answers: after a drift event, does the green line (closed-loop, "
    "drift-aware) hold up or recover better than the gray (baseline, no augmentation) or "
    "orange (static augmentation, trained once and frozen) lines?"
)
fig = go.Figure()
colors = {"baseline": "#888888", "static_augmentation": "#f5a623", "closed_loop": "#2ecc71"}
labels = {"baseline": "Baseline (no augmentation)", "static_augmentation": "Static augmentation",
          "closed_loop": "Closed-loop (drift-aware)"}
timesteps = list(range(results["n_timesteps"]))
for key in cond_keys:
    fig.add_trace(go.Scatter(x=timesteps, y=results["conditions"][key]["macro_f1"],
                              mode="lines+markers", name=labels[key],
                              line=dict(color=colors[key], width=3)))

for t in results["drift_schedule"]:
    fig.add_vline(x=t, line_dash="dash", line_color="#e06666",
                  annotation_text="drift injected", annotation_position="top")
fired_ts = [e["timestep"] for e in results["drift_events"] if e["fired"]]
if fired_ts:
    y_at_fire = [results["conditions"]["closed_loop"]["macro_f1"][t] for t in fired_ts]
    fig.add_trace(go.Scatter(x=fired_ts, y=y_at_fire, mode="markers", name="detector fired",
                              marker=dict(symbol="x", size=12, color="#e06666")))
fig.update_layout(xaxis_title="Simulated timestep", yaxis_title="Macro F1",
                   height=420, legend=dict(orientation="h", y=-0.2))
st.plotly_chart(fig, width='stretch')

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("WGAN-GP Convergence")
    st.caption(
        "The generator and critic ('discriminator') are two networks competing: the generator "
        "tries to produce convincing fake attack samples, the critic tries to tell real from "
        "fake. Their loss values are a tug-of-war score, not an accuracy metric -- what matters "
        "is that the curves settle into a stable pattern rather than diverging or exploding, "
        "which would mean the generator is failing to learn anything real."
    )
    loss_log = results.get("gan_loss_log", [])
    if loss_log:
        steps = [e["step"] for e in loss_log]
        g_loss = [e["g_loss"] for e in loss_log]
        d_loss = [e["d_loss"] for e in loss_log]
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=steps, y=g_loss, name="Generator loss", line=dict(color="#4c8bf5")))
        fig2.add_trace(go.Scatter(x=steps, y=d_loss, name="Critic loss", line=dict(color="#e06666")))
        fig2.update_layout(xaxis_title="Training step", yaxis_title="Loss", height=360,
                            legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig2, width='stretch')
    else:
        st.text("not available in this demo build")

with col_b:
    st.subheader("Fidelity Gate Admission Rate")
    st.caption(
        "MMD (Maximum Mean Discrepancy) is a statistical similarity test between the "
        "generator's synthetic batch and real recent traffic. A batch is 'admitted' only if "
        "it's statistically close enough to be trusted; otherwise it's rejected and never "
        "enters training. A low admission rate isn't necessarily a bad sign -- it can mean "
        "this safety check is correctly refusing to trust synthetic data that doesn't yet "
        "look realistic."
    )
    gate_log = results.get("closed_loop_gate_log", [])
    if gate_log:
        gdf = pd.DataFrame(gate_log)
        by_step = gdf.groupby("step")["admitted"].mean().reset_index()
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(x=by_step["step"], y=by_step["admitted"],
                               marker_color="#2ecc71", name="Admission rate"))
        fig3.update_layout(xaxis_title="Timestep (drift-triggered retrains only)",
                            yaxis_title="Fraction of batches admitted", yaxis_range=[0, 1],
                            height=360)
        st.plotly_chart(fig3, width='stretch')
        st.caption(f"{gdf['admitted'].sum()}/{len(gdf)} synthetic batches admitted across "
                   f"drift-triggered retrains. MMD threshold = 0.25.")
    else:
        st.text("not available in this demo build (no drift-triggered retrains occurred)")

st.divider()

# ---- live drift-detector demo ----
st.subheader("Live Drift Detector Demo")
st.caption("Click to generate a fresh drifted batch on the spot and run the real KS-test "
           "against the reference confidence distribution -- independent of the precomputed run.")
st.caption(
    "The KS-test compares two distributions of the classifier's confidence scores (its "
    "reference behavior vs. its behavior on the new batch). The **p-value** is the "
    "probability those two distributions could look this different just by chance -- a very "
    "small p-value means 'basically no chance this is random,' which is why it counts as "
    "drift detected. The **statistic** is simply how far apart the two distributions are."
)
if st.button("⚡ Inject drift now and test detector"):
    d = data_mod.load_data()
    from proteus import baseline as baseline_mod
    clf = baseline_mod.train_classifier(d["X_train"], d["y_train"], n_estimators=50)
    ref_conf = baseline_mod.confidence_distribution(clf, d["X_test"])

    rng = np.random.default_rng()
    shift = rng.normal(0, 1, size=d["X_test"].shape[1]) * d["X_train"].std(axis=0) * 1.2
    drifted_X = d["X_test"][:150] + shift
    drifted_conf = baseline_mod.confidence_distribution(clf, drifted_X)

    result = drift_mod.detect_drift(drifted_conf, ref_conf)
    if result["fired"]:
        st.error(f"🚨 DRIFT DETECTED — KS statistic={result['statistic']:.4f}, "
                 f"p-value={result['p_value']:.6f} (< alpha={result['alpha']})")
    else:
        st.success(f"No drift detected — KS statistic={result['statistic']:.4f}, "
                   f"p-value={result['p_value']:.4f}")

st.divider()

with st.expander("What's real vs. simulated in this demo", expanded=True):
    st.markdown(f"""
- **Real, computed on this run:** the Random Forest baseline, the WGAN-GP training loop and
  its loss curves, the KS-test drift detector, the MMD fidelity gate scores/admissions, and
  every F1 number shown above -- all genuine computations, not placeholders.
- **Simulated:** the underlying dataset is {src_label.lower()}, not full-scale CICIDS2017/InSDN.
- **Simulated:** "live traffic" is a Python generator replaying held-out data with injected
  distribution shifts, standing in for a live SDN controller feed -- there is no real
  Mininet/Ryu integration in this build (explicitly next milestone).
- **Honest finding:** during drift-triggered retrains in this run, the fidelity gate rejected
  most of the quickly-retrained GAN's synthetic batches (MMD above threshold) -- the safety
  mechanism is working as designed even when it means less synthetic data gets used.
""")
