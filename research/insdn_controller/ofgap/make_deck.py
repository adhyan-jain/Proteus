"""Build PRESENTATION.pptx (light, minimal). Every InSDN number is read from results/*.json. Usage: make_deck.py <out.pptx>"""
import json
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent.parent
R = HERE / "results"
J = lambda f: json.loads((R / f).read_text().replace("NaN", "null"))  # noqa: E731
fm, one, l3 = J("flowmod_matches.json"), J("live_modes_v4_one10.json")["summary"], J("live_modes_v4_linear3.json")["summary"]
rc, st, v2, pi = J("review_checks.json"), J("stock_ryu_flowmods.json"), J("live_modes_v2.json")["summary"], J("protocol_audit_insdn.json")
w1 = J("v4_strict_W1.json")
cv, fam = w1["A_grouped_cv"], w1["B_leave_one_attack_family_out"]
lit = json.loads((HERE / "literature_check.json").read_text())
ci = J("protocol_audit_cicids2017.json")
infl_ci = (ci["A_random_flow_split"]["mean"] - ci["B_source_ip_grouped_split"]["mean"]) * 100
dup_in, dup_ci = pi["E_test_rows_duplicating_train_row_splitA"]["mean"] * 100, ci["E_test_rows_duplicating_train_row_splitA"]["mean"] * 100
n_read, n_pap = sum(1 for q in lit["papers"] if q.get("read")), len(lit["papers"])
triv1 = rc["within_session_W1_strict"]["any_ip_packet_in"]["bacc_pooled"]
triv5 = rc["within_session_W5_strict"]["any_ip_packet_in"]["bacc_pooled"]
mac_n, ip_n = fm["total_by_match_structure"]["in_port|eth_dst|eth_src"], fm["total_by_match_structure"].get("eth_type", 0)
pf, mc = one["fivetuple"]["packet_in_tcp"]["mean"], one["mac"]["packet_in_tcp"]["mean"]
flawed = v2["fivetuple"]["packet_in_tcp"]["mean"] / v2["mac"]["packet_in_tcp"]["mean"]
fam_lo, fam_hi = min(v["mlp_all"]["bacc"]["mean"] for v in fam.values()), max(v["mlp_all"]["bacc"]["mean"] for v in fam.values())
infl = (pi["A_random_flow_split"]["mean"] - pi["B_source_ip_grouped_split"]["mean"]) * 100
worst = min(pi["B_source_ip_grouped_split"]["per_seed"])
macro_ratio = pf / mc

BG, FG, MUTED, LINE, PANEL = RGBColor(0xFF, 0xFF, 0xFF), RGBColor(0x11, 0x18, 0x27), RGBColor(0x6B, 0x72, 0x80), RGBColor(0xD1, 0xD5, 0xDB), RGBColor(0xF3, 0xF4, 0xF6)
ACC, RED, GREY = RGBColor(0x0F, 0x76, 0x6E), RGBColor(0xB9, 0x1C, 0x1C), RGBColor(0x9C, 0xA3, 0xAF)
FONT = "Calibri"
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
_n = [0]


def text(s, t, x, y, w, h, size=16, color=FG, bold=False, align=None, anchor=None):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    if anchor:
        tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.text = t
    p.font.name, p.font.size, p.font.bold, p.font.color.rgb = FONT, Pt(size), bold, color
    if align:
        p.alignment = align
    return tb


def slide(title, kicker):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    _n[0] += 1
    text(s, kicker.upper(), 0.6, 0.4, 9, 0.3, 12, ACC, bold=True)
    text(s, title, 0.6, 0.72, 12.1, 0.9, 28, FG, bold=True)
    text(s, "Proteus · What an SDN controller can observe", 0.6, 7.05, 8, 0.25, 10, MUTED)
    text(s, str(_n[0] + 1), 12.0, 7.05, 0.73, 0.25, 10, MUTED, align=PP_ALIGN.RIGHT)
    return s


def box(s, x, y, w, h, title, sub="", color=ACC, fill=PANEL, dashed=False, tsize=14, ssize=11):
    b = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    b.fill.solid()
    b.fill.fore_color.rgb = fill
    b.line.color.rgb = color
    b.line.width = Pt(1.25)
    if dashed:
        b.line.dash_style = MSO_LINE.DASH
    b.shadow.inherit = False
    tf = b.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Inches(0.08)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    p.text = title
    p.font.name, p.font.size, p.font.bold, p.font.color.rgb = FONT, Pt(tsize), True, FG
    if sub:
        q = tf.add_paragraph()
        q.alignment = PP_ALIGN.CENTER
        q.text = sub
        q.font.name, q.font.size, q.font.color.rgb = FONT, Pt(ssize), MUTED
    return b


def arrow(s, x1, y1, x2, y2, color=GREY):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(1.5)
    ln = c.line._get_or_add_ln()
    etree.SubElement(ln, "{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd", type="triangle", w="med", len="med")


def bullets(s, items, x=0.6, y=2.0, w=6.0, size=18, gap=14):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(4.5))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = it
        p.font.name, p.font.size, p.font.color.rgb = FONT, Pt(size), FG
        p.space_after = Pt(gap)


def big(s, number, caption, x, y, w=5.0, color=ACC, size=54):
    text(s, number, x, y, w, 1.0, size, color, bold=True)
    text(s, caption, x, y + 1.05, w, 0.9, 16, MUTED)


def bar(s, cats, series, x, y, w, h, colors=None, labels=None, fmt="0.00", horizontal=False, log=False, legend=False, vmin=None, vmax=None, point_colors=None):
    """series: list of (name, values). labels: optional per-point label strings for the first series."""
    cd = CategoryChartData()
    cd.categories = cats
    for name, vals in series:
        cd.add_series(name, vals)
    kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    ch = s.shapes.add_chart(kind, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
    ch.font.name, ch.font.size, ch.font.color.rgb = FONT, Pt(12), FG
    ch.has_title = False
    ch.has_legend = legend
    if legend:
        ch.legend.position, ch.legend.include_in_layout = XL_LEGEND_POSITION.BOTTOM, False
        ch.legend.font.size = Pt(12)
    va, ca = ch.value_axis, ch.category_axis
    va.visible = False
    va.has_major_gridlines = False
    ca.format.line.color.rgb = LINE
    ca.has_major_gridlines = False
    ca.tick_labels.font.size = Pt(12)
    if horizontal:
        ca.reverse_order = True
    if vmin is not None:
        va.minimum_scale = vmin
    if vmax is not None:
        va.maximum_scale = vmax
    if log:
        sc = va._element.find("{http://schemas.openxmlformats.org/drawingml/2006/chart}scaling")
        sc.insert(0, etree.Element("{http://schemas.openxmlformats.org/drawingml/2006/chart}logBase", val="10"))
    pl = ch.plots[0]
    pl.gap_width = 60
    pl.has_data_labels = True
    dl = pl.data_labels
    dl.number_format, dl.number_format_is_linked = fmt, False
    dl.font.size, dl.font.name, dl.font.color.rgb = Pt(13), FONT, FG
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    for si, ser in enumerate(pl.series):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = (colors or [ACC, GREY])[si]
        if point_colors and si == 0:
            for i, pc in enumerate(point_colors):
                pt = ser.points[i]
                pt.format.fill.solid()
                pt.format.fill.fore_color.rgb = pc
        if labels and si == 0:
            for i, lab in enumerate(labels):
                dlab = ser.points[i].data_label
                dlab.text_frame.text = lab
                f = dlab.text_frame.paragraphs[0].font
                f.size, f.name, f.color.rgb = Pt(13), FONT, FG
                dlab.position = XL_LABEL_POSITION.OUTSIDE_END
    return ch


# 1 title
s = prs.slides.add_slide(prs.slide_layouts[6])
s.background.fill.solid()
s.background.fill.fore_color.rgb = BG
rule = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.9), Inches(0.9), Inches(0.07))
rule.fill.solid()
rule.fill.fore_color.rgb = ACC
rule.line.fill.background()
text(s, "What an SDN Controller Can Actually Observe", 0.8, 2.2, 11.5, 1.6, 42, FG, bold=True)
text(s, "A measurement and validity study of the InSDN OpenFlow control channel", 0.8, 3.9, 11.5, 0.6, 20, MUTED)
text(s, "Adhyan Jain · Atharva Sheersh Pandey · Kshitij Manikshete", 0.8, 5.5, 11.5, 0.4, 16, FG)
text(s, "Vellore Institute of Technology, Vellore", 0.8, 5.9, 11.5, 0.4, 14, MUTED)

# 2 problem
s = slide("Detectors are scored on data the controller never sees", "The problem")
bullets(s, ["SDN papers justify detection by the controller's global view.",
            "They then evaluate on CSV features computed at the victim host.",
            "Nobody checked what the controller actually receives.",
            "InSDN also recorded its controller's OpenFlow traffic. We parsed all 44 of those captures."], w=5.6, size=19, y=2.0, gap=16)
box(s, 7.0, 2.0, 5.7, 1.5, "What papers score on", "CICFlowMeter 5-tuple flow records\nwith 80+ statistics, computed at the target host", GREY)
box(s, 7.0, 4.2, 5.7, 1.5, "What a controller observes", "PacketIn messages, FlowMod decisions,\nper-entry counters of the rules its app installed", ACC)
text(s, "≠", 9.55, 3.55, 0.6, 0.6, 34, RED, bold=True, align=PP_ALIGN.CENTER)

# 3 primer
s = slide("Background: how an OpenFlow controller sees traffic", "Primer")
box(s, 0.6, 2.2, 2.4, 1.3, "Host", "sends a packet", GREY)
box(s, 5.4, 2.2, 2.4, 1.3, "Switch", "flow table of rules", ACC)
box(s, 10.3, 2.2, 2.4, 1.3, "Controller", "ONOS or Ryu + forwarding app", ACC)
arrow(s, 3.04, 2.85, 5.36, 2.85)
arrow(s, 7.84, 2.55, 10.26, 2.55)
arrow(s, 10.26, 3.15, 7.84, 3.15)
text(s, "PacketIn: table miss sends the packet's headers up", 7.9, 1.75, 2.4, 0.7, 11, MUTED, align=PP_ALIGN.CENTER)
text(s, "FlowMod / PacketOut: install a rule, release the packet", 7.9, 3.25, 2.4, 0.7, 11, MUTED, align=PP_ALIGN.CENTER)
for i, (t, d) in enumerate([("What it receives", "PacketIns for packets that miss the table, and packet and byte counters for the entries that exist."),
                            ("What decides the view", "The forwarding app chooses the rules. Coarse rules (MAC pair) hide flows; per-flow rules expose them."),
                            ("What papers assume", "Per-flow statistics such as inter-arrival times and flag counts, which are not in this vocabulary.")]):
    x = 0.6 + i * 4.15
    text(s, t, x, 4.5, 3.8, 0.4, 16, ACC, bold=True)
    text(s, d, x, 4.95, 3.8, 1.5, 14, FG)

# 4 questions and method
s = slide("Three questions, three kinds of evidence", "Approach")
cards = [("Q1 · Can the controller see the labelled flows?", "Parse all 44 ONOS captures. Read every FlowMod and flow-statistics reply and list the match fields.", "Slides 7, 8"),
         ("Q2 · Does the forwarding app change the view?", "Mininet + Ryu, three forwarding modes, 10 runs each on 1 and 3 switches, plus Ryu's stock app.", "Slides 11, 12"),
         ("Q3 · Is a high score proof of detection?", "Controller-only models on unseen captures and attack families, against a trivial rule and different split protocols.", "Slides 9, 10, 13")]
for i, (q, m, ref) in enumerate(cards):
    x = 0.6 + i * 4.15
    box(s, x, 2.0, 3.85, 3.3, "", "", ACC)
    text(s, q, x + 0.2, 2.2, 3.45, 1.0, 17, ACC, bold=True)
    text(s, m, x + 0.2, 3.35, 3.45, 1.6, 14, FG)
    text(s, ref, x + 0.2, 4.95, 3.45, 0.3, 12, MUTED)
text(s, "Everything is measured on recorded or locally generated captures. No synthetic base data, no cloud, 10 seeds with 95% confidence intervals.", 0.6, 5.8, 12.1, 0.7, 15, MUTED)

# 5 thesis
s = slide("Two phases, one lesson: evaluation is the weak point", "Thesis")
text(s, "PHASE 1 · PROTEUS: DOZENS OF ARCHITECTURES", 0.6, 1.75, 5.9, 0.3, 12, MUTED, bold=True)
text(s, "PHASE 2 · INSDN VALIDITY STUDY", 7.0, 1.75, 5.7, 0.3, 12, ACC, bold=True)
p1 = [("oracle labels", "The 5.91x headline gain came from labels, not from synthetic data"),
      ("0.000", "Synthetic-dose controller vs plain adaptation: difference [0.000, 0.000], 10 seeds"),
      ("97.55% vs 0.00%", "Recall of a 9-feature model vs a zero-filled 77-feature model"),
      ("56% to 100%", "Drift alarms on unchanged traffic after adaptation (stale reference)")]
p2 = [("0 of %s" % f"{fm['flowmods']:,}", "FlowMods match IP addresses or ports"),
      (f"{triv1:.3f}", f"A one-line rule vs {cv['mlp_all']['bacc']['mean']:.3f} for the MLP, inside attack sessions"),
      (f"≈{infl:.0f} points", "Score inflation from a random flow split vs held-out source hosts")]
for i, (a, b) in enumerate(p1):
    y = 2.15 + i * 0.95
    text(s, a, 0.6, y, 2.5, 0.8, 18, FG, bold=True)
    text(s, b, 3.15, y, 3.4, 0.8, 13, MUTED)
for i, (a, b) in enumerate(p2):
    y = 2.15 + i * 0.95
    text(s, a, 7.0, y, 2.5, 0.8, 18, ACC, bold=True)
    text(s, b, 9.55, y, 3.2, 0.8, 13, MUTED)
text(s, "Then", 7.0, 5.0, 2.5, 0.8, 18, GREY, bold=True)
text(s, f"Split audit on InSDN and CICIDS2017, and a full read of {n_read} papers, 9 on InSDN (slides 13 to 16)", 9.55, 5.0, 3.2, 0.8, 13, MUTED)
ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(6.75), Inches(2.0), Inches(6.75), Inches(5.7))
ln.line.color.rgb, ln.line.width = LINE, Pt(1)
text(s, "Strong-looking results kept dissolving under strict evaluation. We then measured the same failure in a published benchmark.", 0.6, 6.05, 12.1, 0.7, 16, FG, bold=True)
text(s, "Phase 1 figures are quoted from archived study results (repository README), not re-run here.", 0.6, 6.7, 12.1, 0.3, 11, MUTED)

# 6 architecture
s = slide("Architecture: two evidence sources, one pipeline", "Architecture")
CW, GAP, X0 = 1.65, 0.45, 0.6
col = lambda i: X0 + i * (CW + GAP)  # noqa: E731
laneA = [("44 pcaps", "ONOS control channel\n11 benign · 33 attack"), ("OpenFlow 1.3 parser", "PacketIn · FlowMod · stats"),
         ("Window labels", "from InSDN CSV flow IDs"), ("22 features", "per 1 to 5 s window"), ("History", "88 model inputs"), ("Models + baselines", "10 seeds · 95% CI · trivial rule")]
laneB = [("Ryu app", "3 forwarding modes"), ("Mininet", "1 or 3 switches\nbenign traffic"), ("Control pcap", "one per run"), ("Counts per mode", "PacketIn · FlowMod · entries"), ("Stock Ryu", "second controller, 5 runs")]
text(s, "A · RECORDED  (InSDN, offline)", 0.6, 1.5, 6, 0.3, 12, ACC, bold=True)
for i, (t, sub) in enumerate(laneA):
    box(s, col(i), 1.85, CW, 1.2, t, sub, ACC, tsize=13, ssize=10)
    if i < 5:
        arrow(s, col(i) + CW + 0.04, 2.45, col(i + 1) - 0.04, 2.45)
text(s, "B · LIVE  (our testbed, no InSDN data)", 0.6, 3.4, 6, 0.3, 12, ACC, bold=True)
for i, (t, sub) in enumerate(laneB):
    box(s, col(i), 3.75, CW, 1.2, t, sub, ACC, tsize=13, ssize=10, dashed=(i == 4))
    if i < 4:
        arrow(s, col(i) + CW + 0.04, 4.35, col(i + 1) - 0.04, 4.35)
text(s, "C · OUTPUT", 0.6, 5.3, 6, 0.3, 12, ACC, bold=True)
box(s, X0, 5.65, 12.15, 0.95, "results/*.json  →  tables and figures  →  paper", "checked by compare_results.py (tolerance 1e-6) and verify_numbers.py · every capture SHA-256 hashed", FG, fill=BG, tsize=14, ssize=11)
arrow(s, col(5) + CW / 2, 3.1, col(5) + CW / 2, 5.6)
arrow(s, col(4) + CW / 2, 5.0, col(4) + CW / 2, 5.6)

# 7 contribution 1
s = slide("Contribution 1 · The controller never saw the labelled flows", "Observability gap")
big(s, "0 of %s" % f"{fm['flowmods']:,}", "FlowMods in the 44 captures match IP addresses or transport ports", 0.6, 1.9, 5.4, RED)
bar(s, ["MAC pair", "EtherType", "IP / ports"], [("FlowMods", [mac_n, ip_n, 0])], 6.6, 1.9, 6.1, 3.6, labels=[f"{mac_n:,}", f"{ip_n}", "0"], horizontal=True, point_colors=[ACC, ACC, RED], vmax=4500, vmin=0)
text(s, "FlowMods by match structure", 6.6, 5.5, 6.1, 0.3, 12, MUTED, align=PP_ALIGN.CENTER)
text(s, f"Ryu's stock learning switch agrees: {st['flowmods']} FlowMods in 5 captures, none with IP or transport fields. The dataset's 5-tuple flows are not counters a controller can read.", 0.6, 5.0, 5.4, 1.4, 14, FG)

# 8 contribution 2
s = slide("Contribution 2 · A pipeline from raw captures to labelled windows", "Reproducible pipeline")
inv = w1["inventory"]
order = ["dos", "probe", "ddos", "botnet", "web", "brute", "exploit"]
nice = {"dos": "DoS", "ddos": "DDoS"}
bar(s, [nice.get(k, k.title()) for k in order], [("attack windows", [inv[k]["attack_windows"] for k in order])], 6.4, 1.8, 6.3, 4.4, labels=[f"{inv[k]['attack_windows']:,}" for k in order], horizontal=True, fmt="#,##0", vmin=0, vmax=2600, colors=[ACC])
text(s, "Attack-labelled 1 s windows per family (strict labels)", 6.4, 6.2, 6.3, 0.3, 12, MUTED, align=PP_ALIGN.CENTER)
bullets(s, ["OpenFlow 1.3 parser with reported parser loss.", "Window labels grounded in InSDN's own flow labels.",
            "22 controller-observable features, up to 88 inputs with history.", "Labels cover only part of the controller-visible traffic, which matters on the next slides."], w=5.4, size=17, y=2.0, gap=14)

# 9 contribution 3
s = slide(f"Contribution 3 · Controller-side models score high ({cv['mlp_all']['bacc']['mean']:.2f})", "Feasibility")
keys = [("PacketIn-rate\nthreshold", cv["thr_packet_in_rate"]), ("Source-IP entropy\nthreshold", cv["thr_src_ip_entropy"]), ("Logistic", cv["linear_all_history"]), ("MLP", cv["mlp_all"])]
bar(s, [k for k, _ in keys], [("balanced accuracy", [d["bacc"]["mean"] for _, d in keys])], 0.6, 1.8, 7.0, 4.4, labels=[f"{d['bacc']['mean']:.3f} ± {d['bacc']['ci95']:.3f}" for _, d in keys], fmt="0.000", vmin=0, vmax=1.15, point_colors=[GREY, GREY, ACC, ACC])
text(s, "Balanced accuracy on unseen captures, 1 s windows, 10 seeds, 95% CI", 0.6, 6.2, 7.0, 0.3, 12, MUTED, align=PP_ALIGN.CENTER)
big(s, f"{fam_lo:.2f} to {fam_hi:.2f}", "MLP balanced accuracy on each of six withheld attack families", 8.2, 2.0, 4.5, ACC, 38)
bullets(s, ["Logistic regression matches the neural network.", "Offered as feasibility, not as a detector."], x=8.2, y=4.1, w=4.5, size=16)

# 10 contribution 4
s = slide("Contribution 4 · A one-line rule matches the model", "Validity")
cats = ["PacketIn-rate\nthreshold", "MLP", "Trivial rule:\nany IP PacketIn"]
vals = [cv["thr_packet_in_rate"]["bacc"]["mean"], cv["mlp_all"]["bacc"]["mean"], triv1]
bar(s, cats, [("balanced accuracy", vals)], 0.6, 1.8, 6.6, 4.4, labels=[f"{v:.3f}" for v in vals], fmt="0.000", vmin=0, vmax=1.15, point_colors=[GREY, ACC, RED])
text(s, "Balanced accuracy, strict labels, 1 s windows (rule: inside attack sessions)", 0.6, 6.2, 6.6, 0.3, 12, MUTED, align=PP_ALIGN.CENTER)
bullets(s, [f"The rule scores {triv1:.3f} (1 s) and {triv5:.3f} (5 s) with no learning.", "InSDN records benign and attack traffic in separate sessions, so a score can reflect the session, not the attack.",
            "We do not claim a detector. We report a validity threat for controller-side evaluation on InSDN.", "Fix: benign and attack traffic interleaved in one session."], x=7.6, y=2.0, w=5.1, size=16, gap=12)

# 11 contribution 5
s = slide("Contribution 5 · The forwarding app sets the view", "Forwarding case study")
modes = [("mac", "MAC-pair"), ("fivetuple_short", "Per-flow, 2 s idle"), ("fivetuple", "Per-flow, 10 s idle")]
bar(s, [lab for _, lab in modes], [("1 switch", [one[m]["packet_in_tcp"]["mean"] for m, _ in modes]), ("3-switch chain", [l3[m]["packet_in_tcp"]["mean"] for m, _ in modes])], 0.6, 1.8, 7.6, 4.5,
    colors=[ACC, GREY], fmt="#,##0", log=True, legend=True, vmin=1, vmax=60000)
text(s, "TCP PacketIns per run, log scale, 10 runs per mode", 0.6, 6.3, 7.6, 0.3, 12, MUTED, align=PP_ALIGN.CENTER)
big(s, f"{macro_ratio:,.0f}×", "more PacketIns with per-flow rules on identical traffic", 8.7, 1.9, 4.0, ACC, 44)
bullets(s, [f"A 2 s idle timeout cuts the entries a 1 s poller sees from {one['fivetuple']['fivetuple_entries_per_reply']['mean']:.0f} to {one['fivetuple_short']['fivetuple_entries_per_reply']['mean']:.0f} per reply.",
            f"Our first app let ping/ARP rules shadow TCP and showed {flawed:.0f}×. We report both."], x=8.7, y=3.9, w=4.0, size=14, gap=10)

# 12 contribution 6
s = slide("Contribution 6 · A second controller and a rerunnable package", "Replication")
big(s, f"{st['flowmods']}", "FlowMods from Ryu's unmodified simple_switch_13 in 5 captures: MAC pairs and table-miss only, no IP or ports", 0.6, 1.9, 5.8, ACC, 54)
for i, (t, sub) in enumerate([("Hashed captures", "SHA-256 for every pcap used"), ("One command", "reproduce.sh rebuilds every result"), ("Automatic comparison", "compare_results.py, tolerance 1e-6"), ("Number check", "verify_numbers.py on the paper text")]):
    box(s, 7.0, 1.9 + i * 1.15, 5.7, 0.95, t, sub, ACC, tsize=14, ssize=11)

# 13 split protocol
s = slide(f"Random splits inflate scores: {infl:.0f} points on InSDN, {infl_ci:.0f} on CICIDS2017", "Split-protocol audit")
pcats = ["Random flow split", "Held-out source hosts", "IP addresses and ports only"]
keyp = ["A_random_flow_split", "B_source_ip_grouped_split", "D_identifier_only_random_split"]
bar(s, pcats, [("InSDN", [pi[k]["mean"] for k in keyp]), ("CICIDS2017", [ci[k]["mean"] for k in keyp])], 0.6, 1.8, 7.6, 4.4, colors=[ACC, GREY], fmt="0.000", legend=True, vmin=0, vmax=1.15)
text(s, f"Balanced accuracy, GPU XGBoost, 10 seeds, benign vs attack. {pi['rows']:,} / {ci['rows']:,} flows", 0.6, 6.2, 7.6, 0.3, 12, MUTED, align=PP_ALIGN.CENTER)
big(s, f"{dup_in:.0f}% / {dup_ci:.0f}%", "of random-split test rows are exact duplicates of a training row (InSDN / CICIDS2017)", 8.6, 1.8, 4.2, RED, 40)
Bi, Bc = pi["B_source_ip_grouped_split"], ci["B_source_ip_grouped_split"]
bullets(s, [f"Held-out hosts: {Bi['mean']:.3f} ± {Bi['ci95']:.3f} (InSDN, worst seed {min(Bi['per_seed']):.2f}), {Bc['mean']:.3f} ± {Bc['ci95']:.3f} (CICIDS2017).",
            "Identifiers alone reach 1.000 on both, so a random split rewards memorising hosts.",
            "Known already: Engelen 2021, Flood 2024. New: the paired gap with CIs on an SDN dataset."], x=8.6, y=4.0, w=4.2, size=13, gap=8)

# 13b published InSDN papers
s = slide("What published InSDN papers report vs how they split", "Protocol audit of the literature")
SHORT = {"Towhid": ("Towhid et al.", "RF 98.84%", "70:30, all flows", None, "Not stated"),
         "Intrusion detection in software defined network using deep": ("Ataa et al. 2024", "99.02%", "Not described (shuffled)", None, "No (stated)"),
         "OptiXGB": ("OptiXGB-IDS 2026", "99.87%", "80:20 random", None, "Ports"),
         "Software defined network intrusion system": ("PeerJ CS 2025", "99.93%", "train_test_split", None, "Not stated"),
         "Sajid": ("Sajid et al. 2025", "99.98%", "Not described", None, "Dst Port"),
         "SDNGuardStack": ("SDNGuardStack 2026", "99.98%", "80/20", None, "Flow ID, IPs, ports"),
         "Malik": ("Malik et al. 2026", "81.60% (CV)", "Stratified 5-fold", None, "Not stated"),
         "LightIDS": ("LightIDS-SDN 2026", "98.73%", "Ratios 60:40 to 90:10", None, "Not stated"),
         "SICA": ("SICA 2026", "99.61%", "70/20/10", None, "No (stated)")}
rows = []
for q in lit["papers"]:
    if not q.get("read"):
        continue
    k = next((k for k in SHORT if k in q["paper"]), None)
    if k is None or "InSDN" not in q.get("dataset", "InSDN"):
        continue
    nm, acc, sp, _, ids = SHORT[k]
    g = {True: "Yes", False: "No", None: "Not stated"}[q.get("grouped")] if "grouped" in q else "No"
    rows.append((nm, acc, sp, g, ids))
assert len(rows) == 9, len(rows)
hdr = ("Paper", "Reported", "Split", "Grouped by host", "IDs / ports as inputs")
tbl = s.shapes.add_table(len(rows) + 1, 5, Inches(0.6), Inches(1.65), Inches(12.1), Inches(4.2)).table
for j, w in enumerate([2.6, 1.7, 3.0, 2.0, 2.8]):
    tbl.columns[j].width = Inches(w)
for i, r in enumerate([hdr] + rows):
    tbl.rows[i].height = Inches(0.42)
    for j, v in enumerate(r):
        c = tbl.cell(i, j)
        c.fill.solid()
        c.fill.fore_color.rgb = ACC if i == 0 else (PANEL if i % 2 == 0 else BG)
        c.margin_top = c.margin_bottom = Inches(0.03)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        pp = c.text_frame.paragraphs[0]
        pp.text = v
        bad = i > 0 and j >= 3 and v not in ("No (stated)", "Not stated") and v != "No" or (i > 0 and j == 4 and v not in ("No (stated)", "Not stated"))
        pp.font.name, pp.font.size, pp.font.bold = FONT, Pt(12), (i == 0)
        pp.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF) if i == 0 else (RED if (j == 4 and v not in ("No (stated)", "Not stated")) else FG)
text(s, f"{n_read} of {n_pap} papers read in full; the {n_pap - n_read} unread ones are not characterised. Table: the 9 read papers that use InSDN (one more read paper is not on InSDN). Numbers are the authors' own, not re-run. None groups by host; none evaluates a real controller.", 0.6, 6.0, 12.1, 0.9, 13, MUTED)

# 14b published feature recipes, two splits
rr = J("recipe_replication.json")
RECS = [("numeric", "Numeric flow features"), ("numeric+port", "Numeric + ports"), ("ids_all", "All columns incl. IDs"), ("top15_mi_ids", "Top-15 by mutual info")]
rv = {r: [rr[f"{r}|{sp}"]["multiclass_acc"] for sp in ("random", "grouped_src_ip")] for r, _ in RECS}
s = slide("Published feature recipes, two splits", "Recipe replication on InSDN")
bar(s, [n for _, n in RECS], [("Random split", [rv[r][0]["mean"] for r, _ in RECS]), ("Held-out source hosts", [rv[r][1]["mean"] for r, _ in RECS])], 0.6, 1.7, 7.8, 4.4, colors=[ACC, RED], fmt="0.0000", legend=True, vmin=0, vmax=1.15)
text(s, "8-class accuracy, GPU XGBoost, 80:20, 10 seeds, 343,889 flows", 0.6, 6.15, 7.8, 0.3, 12, MUTED, align=PP_ALIGN.CENTER)
lo = min(v[1]["mean"] for v in rv.values()); hi = max(v[1]["mean"] for v in rv.values())
rlo = min(v[0]["mean"] for v in rv.values())
cimin = min(v[1]["ci95"] for v in rv.values()); cimax = max(v[1]["ci95"] for v in rv.values())
bullets(s, [f"Random split: at least {rlo:.3f} for every recipe.",
            f"Held-out hosts: {lo:.2f} to {hi:.2f}, with 95% CIs of ±{cimin:.2f} to ±{cimax:.2f}.",
            f"Adding ports lowers the held-out-host score ({rv['numeric'][1]['mean']:.2f} to {rv['numeric+port'][1]['mean']:.2f}) while the random-split score rises."], x=8.8, y=1.9, w=4.0, size=15, gap=12)
text(s, "Caveat: one classifier (XGBoost) and approximate recipes of the published feature choices, not the papers' models or code. Grouping by source host is a stress test, not a deployment estimate.", 0.6, 6.5, 12.1, 0.5, 12, MUTED)

# 14c host structure and leave-one-host-out
import re
lh = J("leave_one_host_out.json")
dl_ = J("dedup_ladder.json")
rp1 = J("replicate_papers.json")["paper1"]
cats, vals, pcs = [], [], []
for ip, h in lh["hosts"].items():
    if h["recall_attack"] is not None:
        cats.append(f"{ip} (attack recall)"); vals.append(h["recall_attack"]); pcs.append(RED if h["recall_attack"] < 0.6 else ACC)
for ip, h in lh["hosts"].items():
    if h["fpr_benign"] is not None:
        cats.append(f"{ip} (benign FPR)"); vals.append(h["fpr_benign"]); pcs.append(RED if 0.3 < h["fpr_benign"] < 0.5 else GREY)
n_att = sum(1 for h in lh["hosts"].values() if h["recall_attack"] is not None)
s = slide("Only about 3 attacker hosts: held-out-host detection collapses", "Host structure and leave-one-host-out")
text(s, f"{lh['distinct_src_ips']:,} source IPs, {lh['single_flow_src_ips']:,} with a single flow; {lh['hosts_ge_500_flows']} hosts with 500 or more flows hold {lh['rows_in_hosts_ge_500']:,} of {lh['rows']:,} rows.", 0.6, 1.5, 12.1, 0.4, 14, MUTED)
bar(s, cats, [("Held-out host", vals)], 0.6, 1.95, 7.4, 4.45, colors=[ACC], fmt="0.00", horizontal=True, vmin=0, vmax=1.2, point_colors=pcs)
text(s, "Train on all other hosts, test on the held-out host. Teal: attack recall; grey: benign false-positive rate; red: highlighted.", 0.6, 6.45, 7.4, 0.5, 11, MUTED)
ddm = dl_["random|dedup"]["mean"]; ddf = 1 - dl_["rows_after_dedup"] / dl_["rows"]
text(s, f"Duplicates are not the mechanism: dropping {ddf:.0%} exact duplicates leaves random-split BAcc at {ddm:.4f}.", 8.4, 1.95, 4.4, 0.9, 14, FG)
text(s, "SDNGuardStack approximation (5 seeds)", 8.4, 3.0, 4.4, 0.35, 14, ACC, bold=True)
a, b = rp1["a_random_ids|all_rows"]["acc"], rp1["b_grouped_ids|all_rows"]["acc"]
b2 = rp1["b_grouped_ids|train_only"]["acc"]
rep = re.search(r"Paper1 reported[^:]*: accuracy ([\d.]+)%", " ".join(J("replicate_papers.json")["notes"])).group(1)
for i, (num, cap, col) in enumerate([(f"{a['mean']:.4f}", f"Random split (reported {rep}%)", ACC),
        (f"{b2['mean']:.2f} to {b['mean']:.2f}", "Source-IP grouped", RED),
        (f"±{max(b['ci95'], b2['ci95']):.2f}", "Largest 95% CI, grouped", GREY)]):
    y = 3.45 + i * 0.75
    text(s, num, 8.4, y, 2.1, 0.6, 22, col, bold=True)
    text(s, cap, 10.55, y + 0.08, 2.3, 0.6, 12, MUTED)
text(s, "Reproduces under its own protocol; does not hold for unseen hosts.", 8.4, 5.8, 4.4, 0.6, 14, FG, bold=True)

# 14 limits
s = slide("Limitations we state ourselves", "Honest scope")
bullets(s, ["Controller study: one dataset (InSDN) and one recorded controller (ONOS); Ryu is checked only on our own benign traffic.",
            "We generated no attack traffic; benign and attack are never interleaved in one session.",
            "Labels cover only part of the controller-visible traffic, so session identity and unlisted attacks cannot be separated.",
            f"Literature check: {n_read} of {n_pap} papers read in full; the rest are not characterised. Reported numbers are the authors' own.",
            "The split audit covers two datasets, one model family (XGBoost) and binary labels; UKMDDoSDN has no benign class and was unusable.",
            "Phase 1 figures come from archived studies and are not re-run here.",
            "Our literature search (October 2026) is evidence, not proof, that no one has measured this on an SDN dataset."], w=12.1, size=18, y=2.0, gap=14)

# 15 scope
s = slide("Contributions: what is new and what is known", "Novelty and scope")
cols = [("Already known", ["Identifier columns are shortcut features (Engelen 2021)", "Random splits leak on NIDS data (Flood 2024)", "Control-plane telemetry for SDN IDS (LAN-SDN-NIDS, SDNFLow)"], MUTED),
        ("New here", ["Paired random vs host-held-out gap on InSDN and CICIDS2017, 10 seeds, CIs", "Audit of 9 published InSDN papers: none groups by host, none uses a real controller", "Published feature recipes on InSDN: ~0.999 random vs 0.69 to 0.84 held-out hosts", "Host structure and leave-one-host-out: about 3 attacker hosts", "Controller-telemetry gap: 0 FlowMods with IPs or ports"], ACC),
        ("Not done", ["Interleaved benign and attack traffic in one session", "A second SDN dataset or controller family", "Unread InSDN papers not characterised"], RED),
        ("Takeaways", ["Random-split scores on InSDN do not measure detection", "What a controller sees depends on the forwarding app", "On InSDN, controller-side scores are not detection accuracy"], FG)]
for i, (t, items, c) in enumerate(cols):
    x = 0.6 + i * 3.1
    text(s, t, x, 1.9, 2.9, 0.5, 20, c, bold=True)
    bullets(s, items, x=x, y=2.6, w=2.85, size=13, gap=10)

prs.save(sys.argv[1])
print("saved", sys.argv[1])
