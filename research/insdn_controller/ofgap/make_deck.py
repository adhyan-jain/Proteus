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


def bullets(s, items, x=0.8, y=1.9, w=11.8, size=22):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(4.6))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "•  " + it
        p.font.size, p.font.color.rgb = Pt(size), FG
        p.space_after = Pt(16)


def big(s, number, caption, x, y, w=4.0, color=TEAL):
    text(s, number, x, y, w, 1.2, 54, color, bold=True)
    text(s, caption, x, y + 1.25, w, 1.2, 16, MUTED)


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
bullets(s, ["SDN papers say the controller has a global view, so build the detector there.",
            "But they test on CSV features computed at the victim host, then call it controller-based.",
            "Nobody checked what the controller actually receives.",
            "InSDN also recorded its controller's OpenFlow traffic. We opened those recordings."])

# 3 approach
s = slide("What we did: 44 recordings, three questions", "Approach")
bullets(s, ["Q1  Can the controller see the flows the dataset labels?",
            "Q2  Does what it sees depend on the forwarding app?  (Mininet + Ryu, 65 runs)",
            "Q3  Is a high score on the controller's view proof of detection?"], size=24)
text(s, "Data: 44 InSDN controller captures (11 benign, 33 attack) + our own Mininet/Ryu testbed", 0.8, 5.2, 12, 0.6, 16, MUTED)

# 4 novelty 1
s = slide("Novelty 1 · The controller never saw the labelled flows", "Gap in the benchmark")
big(s, "0 of %s" % f"{fm['flowmods']:,}", "FlowMods carry IP addresses or ports", 0.8, 2.0, 6.0, RED)
big(s, f"{st['flowmods']}", "FlowMods from Ryu's stock app: also MAC-pair only", 7.2, 2.0, 5.0, TEAL)
bullets(s, ["The dataset labels 5-tuple flows; the controller's rules only matched MAC pairs or EtherType.",
            "So CSV-trained detectors are not controller-side detectors."], y=4.6, size=20)

# 5 novelty 2
s = slide("Novelty 2 · The forwarding app decides what the controller sees", "Measured effect")
chart(s, ["MAC-pair", "Per-flow"], [mc, pf], 0.6, 1.8, 6.0, 4.6, [TEAL, AMBER], "#,##0")
text(s, "TCP PacketIns per run (1 switch, 10 runs)", 0.6, 6.35, 6.0, 0.4, 13, MUTED, align=PP_ALIGN.CENTER)
bullets(s, [f"Same traffic: {pf / mc:,.0f}x more PacketIns with per-flow rules.", "Holds on a 3-switch chain too.",
            f"A 2 s idle timeout hides most per-flow entries from a 1 s poller ({one['fivetuple']['fivetuple_entries_per_reply']['mean']:.0f} to {one['fivetuple_short']['fivetuple_entries_per_reply']['mean']:.0f})."], x=7.0, y=2.1, w=5.8, size=20)

# 6 novelty 3
s = slide("Novelty 3 · A high score is not proof of detection", "Validity")
chart(s, ["PacketIn-rate\nthreshold", "MLP", "Trivial rule:\nany IP PacketIn"], [w1["thr_packet_in_rate"]["bacc"]["mean"], w1["mlp_all"]["bacc"]["mean"], triv1], 0.6, 1.8, 6.6, 4.6, [AMBER, TEAL, RED], "0.000")
text(s, "Balanced accuracy, unseen captures, 1 s windows", 0.6, 6.35, 6.6, 0.4, 13, MUTED, align=PP_ALIGN.CENTER)
bullets(s, ["A one-line rule beats the model inside attack sessions.", "InSDN records benign and attack in separate sessions, so scores may reflect the session.",
            "Fix: benign and attack traffic mixed in one session."], x=7.5, y=2.1, w=5.3, size=20)

# 7 novelty 4 + 5
s = slide("Novelty 4 and 5 · A caught pitfall, a rerunnable package", "Method")
bullets(s, [f"Our first test app let ping/ARP rules hide TCP: the effect looked like {flawed:.0f}x instead of about {pf / mc:,.0f}x. We report both.",
            "Overlapping coarse rules can understate controller load by two orders of magnitude.",
            "One command rebuilds every result from hashed captures and checks the paper's numbers."], size=22)

# 8 architecture
s = slide("Study architecture: what goes in, what comes out", "Pipeline")
text(s, "A · InSDN captures (recorded, offline)", 0.6, 1.55, 6, 0.35, 13, TEAL, bold=True)
chain(s, 1.9, [("44 pcaps", "in: ONOS TCP 6653"), ("Parser", "out: PacketIn, FlowMod, stats"), ("Labels", "CSV flow IDs → tag per PacketIn"), ("Windows", "22 features per 1–5 s"), ("History", "88 inputs"), ("Models + tests", "10 seeds, CI, trivial rule")], w=1.78, h=1.5, gap=0.28)
text(s, "B · Live forwarding study (no InSDN data)", 0.6, 3.75, 6, 0.35, 13, AMBER, bold=True)
chain(s, 4.1, [("Ryu app", "3 forwarding modes"), ("Mininet", "1 or 3 switches, benign traffic"), ("Control-channel pcap", "one per run"), ("Counts per mode", "PacketIn, FlowMod, entries")], w=2.6, h=1.3, gap=0.55, color=AMBER)
box(s, 0.6, 5.75, 12.1, 0.8, "Both end as results/*.json → tables in the paper", "model input: 88 numbers about a few seconds of controller messages · output: attack / not attack per window · the CSV only supplies labels", PURPLE, ssize=12)

# 9 scope
s = slide("What is not new, what we did not do, what is next", "Honest scope")
for i, (t, items, col) in enumerate([("Not new", ["Control-plane telemetry for SDN IDS (LAN-SDN-NIDS, SDNFLow)", "The detector itself", "Stock Ryu behaviour"], AMBER),
                                     ("Not done", ["Benign + attack in one session", "OpenDaylight or another dataset", "A re-implemented published detector"], RED),
                                     ("Next", ["Interleave benign and attack traffic", "Gap on a second controller family", "In-fold oversampling for rare classes"], TEAL)]):
    x = 0.8 + i * 4.1
    text(s, t, x, 1.9, 3.8, 0.6, 26, col, bold=True)
    bullets(s, items, x=x, y=2.7, w=3.8, size=17)
text(s, "Venue: workshop / conference as is; lower-quartile journal after revision.", 0.8, 6.5, 12, 0.5, 14, MUTED)

# 10 earlier proteus
s = slide("The earlier Proteus system: a prototype, not a claim", "Context")
bullets(s, ["Built: WGAN-GP synthetic attacks, KS drift test, MMD fidelity gate, drift-triggered retraining, versioned releases.",
            "Close prior work exists (NetGuard 2025: generative adaptation for drifting, imbalanced IDS data).",
            "Our own studies found no benefit from the generative step; the demo's gain came from oracle labels.",
            "So the research contribution is the InSDN study; Proteus is kept as context (/old console)."], size=21)

# 11 takeaways
s = slide("Takeaways", "Close")
bullets(s, ["The controller's rules never contained the labelled 5-tuples.", "What a controller sees depends on the forwarding app.",
            "On InSDN, controller-side scores are not detection accuracy."], size=26)
text(s, "Next: interleave benign and attack traffic in one session; test a second controller.", 0.8, 5.6, 12, 0.6, 16, MUTED)

prs.save(sys.argv[1])
print("saved", sys.argv[1])
