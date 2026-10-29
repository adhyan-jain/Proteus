"""Build PRESENTATION.pptx (flowchart style). Every number is read from results/*.json. Usage: make_deck.py <out.pptx>"""
import json
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

R = Path(__file__).resolve().parent.parent / "results"
J = lambda f: json.loads((R / f).read_text().replace("NaN", "null"))  # noqa: E731
fm, one, l3 = J("flowmod_matches.json"), J("live_modes_v4_one10.json")["summary"], J("live_modes_v4_linear3.json")["summary"]
xg, rc, st, hs = J("v4_strict_W5_xgb.json")["A_grouped_cv"], J("review_checks.json"), J("stock_ryu_flowmods.json"), J("hostside_xgb.json")
w1, v2 = J("v4_strict_W1.json")["A_grouped_cv"], J("live_modes_v2.json")["summary"]
triv1 = rc["within_session_W1_strict"]["any_ip_packet_in"]["bacc_pooled"]
mp = fm["total_by_match_structure"]["in_port|eth_dst|eth_src"]
pf, mc = one["fivetuple"]["packet_in_tcp"]["mean"], one["mac"]["packet_in_tcp"]["mean"]
pf3, mc3 = l3["fivetuple"]["packet_in_tcp"]["mean"], l3["mac"]["packet_in_tcp"]["mean"]
flawed = v2["fivetuple"]["packet_in_tcp"]["mean"] / v2["mac"]["packet_in_tcp"]["mean"]

BG, PANEL, FG, MUTED = RGBColor(0x0B, 0x12, 0x20), RGBColor(0x14, 0x1E, 0x33), RGBColor(0xF1, 0xF5, 0xF9), RGBColor(0x9A, 0xA8, 0xBC)
TEAL, AMBER, RED, PURPLE, GREEN = RGBColor(0x2D, 0xD4, 0xBF), RGBColor(0xF5, 0xB0, 0x41), RGBColor(0xF8, 0x71, 0x71), RGBColor(0xA7, 0x8B, 0xFA), RGBColor(0x4A, 0xDE, 0x80)
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)


def slide(title, kicker=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    if kicker:
        text(s, kicker.upper(), 0.6, 0.35, 12, 0.4, 12, TEAL, bold=True)
    text(s, title, 0.6, 0.7, 12.2, 0.9, 28, FG, bold=True)
    return s


def text(s, t, x, y, w, h, size=16, color=FG, bold=False, align=None):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = t
    p.font.size, p.font.bold, p.font.color.rgb = Pt(size), bold, color
    if align:
        p.alignment = align
    return tb


def box(s, x, y, w, h, title, sub="", color=TEAL, shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=PANEL, tsize=15, ssize=11):
    b = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    b.fill.solid()
    b.fill.fore_color.rgb = fill
    b.line.color.rgb = color
    b.line.width = Pt(2)
    tf = b.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Inches(0.08)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.text = title
    p.font.size, p.font.bold, p.font.color.rgb = Pt(tsize), True, color
    if sub:
        q = tf.add_paragraph()
        q.alignment = PP_ALIGN.CENTER
        q.text = sub
        q.font.size, q.font.color.rgb = Pt(ssize), FG
    return b


def arrow(s, x1, y1, x2, y2, color=MUTED, label=None):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(2.25)
    ln = c.line._get_or_add_ln()
    ln.append(etree.SubElement(ln, "{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd", type="triangle", w="lg", len="lg"))
    if label:
        text(s, label, min(x1, x2), min(y1, y2) - 0.32, abs(x2 - x1) + 0.4, 0.3, 11, color, align=PP_ALIGN.CENTER)


def chain(s, y, items, x0=0.6, w=1.85, h=1.25, gap=0.42, color=TEAL):
    for i, (t, sub) in enumerate(items):
        x = x0 + i * (w + gap)
        box(s, x, y, w, h, t, sub, color)
        if i < len(items) - 1:
            arrow(s, x + w + 0.03, y + h / 2, x + w + gap - 0.03, y + h / 2, color)


def say(s, t):
    text(s, t, 0.6, 6.75, 12.2, 0.6, 14, MUTED)


def chart(s, cats, vals, x, y, w, h, colors, fmt="#,##0.0"):
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("v", vals)
    ch = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
    ch.has_legend = ch.has_title = False
    ch.font.size, ch.font.color.rgb = Pt(12), FG
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    pl = ch.plots[0]
    pl.has_data_labels = True
    pl.data_labels.number_format, pl.data_labels.number_format_is_linked = fmt, False
    pl.data_labels.font.size, pl.data_labels.font.color.rgb = Pt(14), FG
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    pl.gap_width = 70
    for i, col in enumerate(colors):
        pt = pl.series[0].points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = col


# 1 title
s = prs.slides.add_slide(prs.slide_layouts[6])
s.background.fill.solid()
s.background.fill.fore_color.rgb = BG
text(s, "PROTEUS · SDN INTRUSION-DETECTION RESEARCH", 0.8, 1.5, 12, 0.5, 14, TEAL, bold=True)
text(s, "What an SDN Controller Can Actually Observe", 0.8, 2.0, 12, 1.4, 44, FG, bold=True)
text(s, "A measurement and validity study of the InSDN OpenFlow control channel", 0.8, 3.9, 12, 0.8, 22, MUTED)
text(s, "Adhyan Jain · Atharva Sheersh Pandey · Kshitij Manikshete\nVIT Vellore", 0.8, 5.2, 12, 1.0, 18, FG)

# 2 problem
s = slide("Detectors are scored on data the controller never sees", "The problem")
box(s, 0.6, 2.0, 3.4, 1.4, "Benchmark CSV", "flow features computed at the victim host (CICFlowMeter)", AMBER)
arrow(s, 4.05, 2.7, 5.0, 2.7, AMBER)
box(s, 5.05, 2.0, 3.0, 1.4, "Detector scored", "99% accuracy reported", AMBER)
arrow(s, 8.1, 2.7, 9.05, 2.7, AMBER)
box(s, 9.1, 2.0, 3.6, 1.4, "Called \"controller-based\"", "global-view claim", AMBER)
box(s, 0.6, 4.3, 3.4, 1.4, "What the controller receives", "PacketIn · FlowMod · flow statistics", TEAL)
box(s, 5.05, 4.0, 3.0, 2.0, "Same thing?", "Nobody checked", RED, shape=MSO_SHAPE.DIAMOND)
arrow(s, 4.05, 5.0, 5.0, 5.0, RED)
arrow(s, 6.55, 3.45, 6.55, 3.95, RED)
say(s, "InSDN also recorded its controller's OpenFlow traffic. We opened those recordings.")

# 3 approach (branching)
s = slide("What we did: one dataset, three questions", "Approach")
box(s, 0.6, 3.0, 2.9, 1.6, "44 controller captures", "InSDN, ONOS, OpenFlow 1.3 · 11 benign, 33 attack", TEAL)
for i, (t, sub, c) in enumerate([("Q1 Can it see the labelled flows?", "read every FlowMod", AMBER), ("Q2 Does the view depend on the forwarding app?", "Mininet + Ryu, 3 modes, 65 runs", TEAL), ("Q3 Is a high score proof of detection?", "controller-only models + trivial rule", PURPLE)]):
    y = 1.9 + i * 1.75
    box(s, 5.2, y, 4.2, 1.35, t, sub, c)
    arrow(s, 3.55, 3.8, 5.15, y + 0.67, c)
for i, (t, c) in enumerate([("No: 0 of %s FlowMods" % f"{fm['flowmods']:,}", AMBER), ("Yes: %dx more PacketIns" % round(pf / mc), TEAL), ("No: trivial rule %.3f" % triv1, PURPLE)]):
    y = 1.9 + i * 1.75
    arrow(s, 9.45, y + 0.67, 10.0, y + 0.67, c)
    box(s, 10.05, y, 2.7, 1.35, t, "", c)

# 4 novelty 1
s = slide("Novelty 1 · The controller never saw the labelled flows", "Gap in the benchmark")
box(s, 0.6, 2.0, 5.2, 1.7, "Dataset labels", "source IP · destination IP · source port · destination port · protocol (5-tuple)", AMBER)
box(s, 7.5, 2.0, 5.2, 1.7, "Controller's rules match", "in_port · eth_src · eth_dst (MAC pair), or EtherType", TEAL)
arrow(s, 5.85, 2.85, 7.45, 2.85, RED)
text(s, "✕ no overlap", 5.9, 2.4, 1.6, 0.4, 14, RED, bold=True, align=PP_ALIGN.CENTER)
box(s, 0.6, 4.2, 3.9, 1.9, "0 of %s" % f"{fm['flowmods']:,}", "FlowMods carry IP or port fields", RED, tsize=30, ssize=14)
box(s, 4.7, 4.2, 3.9, 1.9, f"{mp:,} + {fm['total_by_match_structure']['eth_type']}", "MAC-pair + EtherType rules", TEAL, tsize=30, ssize=14)
box(s, 8.8, 4.2, 3.9, 1.9, f"{st['flowmods']} FlowMods", "Ryu stock app: same, none with IP/ports", TEAL, tsize=30, ssize=14)
say(s, "So: CSV-trained detectors do not describe a deployable controller-side detector.")

# 5 novelty 2
s = slide("Novelty 2 · The forwarding app decides what the controller sees", "Measured effect")
box(s, 0.6, 2.6, 2.4, 1.3, "Same benign traffic", "10 runs per mode", MUTED)
box(s, 3.7, 1.9, 2.6, 1.1, "Ryu MAC-pair rules", "", TEAL)
box(s, 3.7, 3.5, 2.6, 1.1, "Ryu per-flow rules", "", AMBER)
arrow(s, 3.05, 3.0, 3.65, 2.5, TEAL)
arrow(s, 3.05, 3.5, 3.65, 4.05, AMBER)
arrow(s, 6.35, 2.45, 7.0, 2.45, TEAL)
arrow(s, 6.35, 4.05, 7.0, 4.05, AMBER)
box(s, 7.05, 1.9, 2.1, 1.1, f"{mc:.1f}", "PacketIns / run", TEAL, tsize=26)
box(s, 7.05, 3.5, 2.1, 1.1, f"{pf:,.0f}", "PacketIns / run", AMBER, tsize=26)
chart(s, ["MAC-pair", "Per-flow"], [mc3, pf3], 9.5, 1.8, 3.4, 2.9, [TEAL, AMBER], "#,##0")
text(s, "3-switch chain", 9.5, 4.65, 3.4, 0.3, 12, MUTED, align=PP_ALIGN.CENTER)
box(s, 0.6, 5.3, 5.8, 1.1, "Idle timeout 10 s → 2 s", f"entries a 1 s poller sees: {one['fivetuple']['fivetuple_entries_per_reply']['mean']:.1f} → {one['fivetuple_short']['fivetuple_entries_per_reply']['mean']:.1f}", PURPLE)
box(s, 6.7, 5.3, 6.0, 1.1, f"{pf / mc:,.0f}x more PacketIns", "665x to 1,752x in every paired run", AMBER, tsize=20)

# 6 novelty 3 (decision diamond)
s = slide("Novelty 3 · A high score is not proof of detection", "Validity")
chain(s, 1.9, [("Controller messages", "PacketIn · FlowMod · stats"), ("1 s windows", "22 features, 3 past windows"), ("MLP / XGBoost / logistic", "unseen captures"), (f"BAcc {w1['mlp_all']['bacc']['mean']:.3f}", "looks strong")], w=2.5, gap=0.55)
box(s, 0.6, 3.9, 3.6, 1.2, f"Trivial rule: any IP PacketIn", f"scores {triv1:.3f} inside attack sessions", RED)
arrow(s, 4.25, 4.5, 5.2, 4.5, RED)
box(s, 5.25, 3.7, 3.0, 1.6, "Is the score proof?", "", RED, shape=MSO_SHAPE.DIAMOND)
arrow(s, 8.3, 4.5, 9.2, 4.5, RED, "NO")
box(s, 9.25, 3.9, 3.5, 1.2, "Separate sessions", "benign and attack recorded apart: it may be recognising the session", AMBER)
box(s, 0.6, 5.6, 12.1, 0.95, "Fix: benign and attack traffic mixed in one session, labels for all controller-visible traffic", "", TEAL)
say(s, f"XGBoost {xg['xgb_all_history']['bacc']['mean']:.3f}, logistic {xg['linear_all_history']['bacc']['mean']:.3f}, MLP {xg['mlp_all']['bacc']['mean']:.3f} (5 s): no model gain. Host-side CSV {hs['bacc_mean']:.4f}: easy protocol.")

# 7 novelty 4 + 5
s = slide("Novelty 4 and 5 · A caught pitfall, a rerunnable package", "Method and reproducibility")
text(s, "Pitfall", 0.6, 1.8, 3, 0.4, 14, AMBER, bold=True)
chain(s, 2.2, [("First test app", "ping/ARP MAC-pair rules"), ("Rules shadow TCP", "most connections skip the controller"), (f"Effect looks {flawed:.0f}x", "wide interval"), ("Fixed app", f"{pf / mc:,.0f}x, reported both")], w=2.6, gap=0.55, color=AMBER)
text(s, "Reproducibility", 0.6, 4.1, 3, 0.4, 14, TEAL, bold=True)
chain(s, 4.5, [("Hashed raw captures", "SHA-256"), ("reproduce.sh", "rebuilds every result"), ("compare_results.py", "tolerance 1e-6"), ("verify_numbers.py", "paper numbers vs JSON")], w=2.6, gap=0.55)

# 8 architecture
s = slide("Study architecture: what goes in, what comes out", "Pipeline")
text(s, "A · InSDN captures (recorded, offline)", 0.6, 1.55, 6, 0.35, 13, TEAL, bold=True)
chain(s, 1.9, [("44 pcaps", "in: ONOS TCP 6653"), ("Parser", "out: PacketIn, FlowMod, stats"), ("Labels", "CSV flow IDs → tag per PacketIn"), ("Windows", "22 features per 1–5 s"), ("History", "88 inputs"), ("Models + tests", "10 seeds, CI, trivial rule")], w=1.78, h=1.5, gap=0.28)
text(s, "B · Live forwarding study (no InSDN data)", 0.6, 3.75, 6, 0.35, 13, AMBER, bold=True)
chain(s, 4.1, [("Ryu app", "3 forwarding modes"), ("Mininet", "1 or 3 switches, benign traffic"), ("Control-channel pcap", "one per run"), ("Counts per mode", "PacketIn, FlowMod, entries")], w=2.6, h=1.3, gap=0.55, color=AMBER)
box(s, 0.6, 5.75, 12.1, 0.8, "Both end as results/*.json → tables in the paper", "model input: 88 numbers about a few seconds of controller messages · output: attack / not attack per window · the CSV only supplies labels", PURPLE, ssize=12)

# 9 scope
s = slide("What is not new, what we did not do, what is next", "Honest scope")
for i, (t, items, c) in enumerate([("Not new", ["Control-plane telemetry for SDN IDS (LAN-SDN-NIDS, SDNFLow)", "The detector itself", "Stock Ryu behaviour"], AMBER),
                                   ("Not done", ["Benign + attack traffic in one session", "OpenDaylight / another dataset", "A re-implemented published detector"], RED),
                                   ("Next", ["Interleave benign and attack in one session", "Gap on a second controller family", "In-fold oversampling for rare classes"], TEAL)]):
    x = 0.6 + i * 4.15
    box(s, x, 2.0, 3.9, 0.8, t, "", c, tsize=20)
    for j, it in enumerate(items):
        box(s, x, 3.1 + j * 1.15, 3.9, 0.95, it, "", c, tsize=13, fill=BG)
        arrow(s, x + 1.95, 2.83 if j == 0 else 3.1 + (j - 1) * 1.15 + 0.95, x + 1.95, 3.1 + j * 1.15, c)
say(s, "Venue: workshop / conference as is; lower-quartile journal after revision.")

# 10 earlier proteus
s = slide("The earlier Proteus system: a prototype, not a claim", "Context")
chain(s, 1.9, [("SDN traffic", ""), ("Classify", "random forest"), ("Drift", "KS test"), ("WGAN-GP", "synthetic attacks"), ("Fidelity gate", "MMD check"), ("Retrain", "redeploy")], w=1.78, gap=0.28, color=PURPLE)
arrow(s, 12.0, 3.2, 12.0, 3.9, PURPLE)
arrow(s, 12.0, 3.9, 1.6, 3.9, PURPLE, "loop")
box(s, 0.6, 4.4, 5.8, 1.7, "Close prior work", "NetGuard (2025): generative adaptation for drifting, imbalanced IDS data", AMBER)
box(s, 6.9, 4.4, 5.8, 1.7, "Our own studies found no benefit", "the demo's gain came from oracle labels, not synthetic data", RED)
say(s, "So the research contribution is the InSDN study. Proteus code is kept as context and a /old console.")

# 11 takeaways
s = slide("Takeaways", "Close")
for i, (a, b, c) in enumerate([("Gap", "Controller rules never contained the labelled 5-tuples.", AMBER), ("Depends", "What a controller sees depends on the forwarding app.", TEAL), ("Careful", "On InSDN, controller-side scores are not detection accuracy.", PURPLE)]):
    x = 0.6 + i * 4.15
    box(s, x, 2.2, 3.9, 2.6, a, b, c, tsize=30, ssize=16)
    if i < 2:
        arrow(s, x + 3.93, 3.5, x + 4.2, 3.5, MUTED)
say(s, "Next: interleave benign and attack traffic in one session and test a second controller.")

prs.save(sys.argv[1])
print("saved", sys.argv[1])
