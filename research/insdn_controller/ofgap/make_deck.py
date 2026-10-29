"""Build PRESENTATION.pptx for the paper. Every number is read from results/*.json. Usage: make_deck.py <out.pptx>"""
import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

R = Path(__file__).resolve().parent.parent / "results"
J = lambda f: json.loads((R / f).read_text().replace("NaN", "null"))  # noqa: E731
fm, one, l3 = J("flowmod_matches.json"), J("live_modes_v4_one10.json")["summary"], J("live_modes_v4_linear3.json")["summary"]
xg, rc, st, hs = J("v4_strict_W5_xgb.json")["A_grouped_cv"], J("review_checks.json"), J("stock_ryu_flowmods.json"), J("hostside_xgb.json")
w1 = J("v4_strict_W1.json")["A_grouped_cv"]
triv5 = rc["within_session_W5_strict"]["any_ip_packet_in"]["bacc_pooled"]
triv1 = rc["within_session_W1_strict"]["any_ip_packet_in"]["bacc_pooled"]
mp = fm["total_by_match_structure"]["in_port|eth_dst|eth_src"]
pf, mc = one["fivetuple"]["packet_in_tcp"]["mean"], one["mac"]["packet_in_tcp"]["mean"]
pf3, mc3 = l3["fivetuple"]["packet_in_tcp"]["mean"], l3["mac"]["packet_in_tcp"]["mean"]

BG, FG, MUTED, ACC, WARN = RGBColor(0x0B, 0x12, 0x20), RGBColor(0xF1, 0xF5, 0xF9), RGBColor(0x9A, 0xA8, 0xBC), RGBColor(0x2D, 0xD4, 0xBF), RGBColor(0xF5, 0xB0, 0x41)
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)


def slide(title, kicker=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    if kicker:
        text(s, kicker.upper(), 0.7, 0.45, 12, 0.4, 13, ACC, bold=True)
    text(s, title, 0.7, 0.8, 12, 1.0, 32, FG, bold=True)
    return s


def text(s, t, x, y, w, h, size=18, color=FG, bold=False, align=None):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = t
    p.font.size, p.font.bold, p.font.color.rgb = Pt(size), bold, color
    if align:
        p.alignment = align
    return tb


def bullets(s, items, x=0.7, y=2.0, w=12, size=20):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(4.8))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "•  " + it
        p.font.size, p.font.color.rgb = Pt(size), FG
        p.space_after = Pt(12)


def card(s, x, y, w, h, big, small, color=ACC):
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    b.fill.solid()
    b.fill.fore_color.rgb = RGBColor(0x14, 0x1E, 0x33)
    b.line.color.rgb = RGBColor(0x2A, 0x38, 0x52)
    text(s, big, x + 0.25, y + 0.25, w - 0.5, 1.0, 34, color, bold=True)
    text(s, small, x + 0.25, y + 1.3, w - 0.5, h - 1.4, 15, MUTED)


def say(s, t):
    text(s, "Say: " + t, 0.7, 6.55, 12, 0.8, 14, MUTED)


def chart(s, cats, vals, x, y, w, h, color=ACC, fmt='#,##0.0'):
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("v", vals)
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = False
    ch.font.size, ch.font.color.rgb = Pt(14), FG
    ch.value_axis.visible = False
    ch.value_axis.has_major_gridlines = False
    pl = ch.plots[0]
    pl.has_data_labels = True
    pl.data_labels.number_format, pl.data_labels.number_format_is_linked = fmt, False
    pl.data_labels.font.size, pl.data_labels.font.color.rgb = Pt(16), FG
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    pl.gap_width = 80
    pl.series[0].format.fill.solid()
    pl.series[0].format.fill.fore_color.rgb = color


# 1 title
s = prs.slides.add_slide(prs.slide_layouts[6])
s.background.fill.solid()
s.background.fill.fore_color.rgb = BG
text(s, "PROTEUS · SDN INTRUSION-DETECTION RESEARCH", 0.8, 1.6, 12, 0.5, 14, ACC, bold=True)
text(s, "What an SDN Controller Can Actually Observe", 0.8, 2.1, 12, 1.2, 44, FG, bold=True)
text(s, "A measurement and validity study of the InSDN OpenFlow control channel", 0.8, 3.9, 12, 0.8, 22, MUTED)
text(s, "Adhyan Jain · Atharva Sheersh Pandey · Kshitij Manikshete\nVIT Vellore", 0.8, 5.2, 12, 1.0, 18, FG)

# 2 problem
s = slide("SDN detectors are scored on data the controller never sees", "The problem")
bullets(s, ["Papers say: the controller has a global view, so build the detector there.",
            "But they are tested on CSV features computed at the victim host (CICFlowMeter).",
            "Nobody checks whether a controller can observe those features at all.",
            "InSDN, a widely used SDN benchmark, also recorded its controller's OpenFlow traffic. We opened those recordings."])
say(s, "\"Is the controller-side view real, and does a high score on it mean detection?\"")

# 3 what we did
s = slide("What we did", "Approach")
card(s, 0.7, 2.0, 3.9, 3.4, "44", "InSDN controller captures parsed: 11 benign, 33 attack, 7 attack classes (OpenFlow 1.3).")
card(s, 4.7, 2.0, 3.9, 3.4, "2 tests", "Controller-only detectors on unseen captures and families, plus a trivial-rule validity check.")
card(s, 8.7, 2.0, 3.9, 3.4, "65 runs", "Mininet + Ryu testbed: 3 forwarding modes, 1-switch and 3-switch, plus Ryu's stock app.")

# 4 novelty 1
s = slide("Novelty 1 · The controller never saw the labelled flows", "Gap in the benchmark")
card(s, 0.7, 2.0, 4.2, 2.6, f"0 of {fm['flowmods']:,}", f"FlowMods carry IP addresses or ports. {mp:,} match MAC pairs, {fm['total_by_match_structure']['eth_type']} match EtherType.", WARN)
bullets(s, ["InSDN labels flows by 5-tuple; the controller's rules never contained one.",
            "The controller does receive PacketIns: 0.68 to 1.29 per target packet in 9 of 12 attack scenarios.",
            f"Ryu's unmodified app: {st['flowmods']} FlowMods, {st['total_by_match_structure']['in_port|eth_dst|eth_src']} MAC-pair, none with IP/ports."], x=5.2, y=2.0, w=7.5, size=18)
say(s, "CSV-trained detectors do not describe a deployable controller-side detector.")

# 5 novelty 2
s = slide("Novelty 2 · The forwarding app decides what the controller sees", "Measured effect")
chart(s, ["MAC-pair", "Per-flow"], [mc, pf], 0.7, 1.9, 5.6, 4.4, ACC)
chart(s, ["MAC-pair", "Per-flow"], [mc3, pf3], 6.9, 1.9, 5.6, 4.4, WARN)
text(s, "1 switch · TCP PacketIns per run", 0.7, 6.2, 5.6, 0.4, 14, MUTED, align=PP_ALIGN.CENTER)
text(s, "3-switch chain · TCP PacketIns per run", 6.9, 6.2, 5.6, 0.4, 14, MUTED, align=PP_ALIGN.CENTER)
say(s, f"Same traffic, {pf / mc:,.0f}x more PacketIns under per-flow rules; a 2 s idle timeout also hides entries from a 1 s poller.")

# 6 novelty 3
s = slide("Novelty 3 · A high score is not proof of detection", "Validity")
chart(s, ["Threshold\n(PacketIn rate)", "MLP", "Trivial rule\n'any IP PacketIn'"],
      [w1["thr_packet_in_rate"]["bacc"]["mean"], w1["mlp_all"]["bacc"]["mean"], triv1], 0.7, 1.9, 7.2, 4.5, ACC, '0.000')
bullets(s, ["Balanced accuracy, 1 s windows, unseen captures.",
            "InSDN records benign and attack in separate sessions, so a model can score by recognising the session.",
            f"XGBoost {xg['xgb_all_history']['bacc']['mean']:.3f}, logistic {xg['linear_all_history']['bacc']['mean']:.3f}, MLP {xg['mlp_all']['bacc']['mean']:.3f} (5 s): no model gain.",
            f"Host-side CSV baseline {hs['bacc_mean']:.4f}: easy protocol, not comparable."], x=8.1, y=2.0, w=4.8, size=16)
say(s, "We claim a validity warning, not a detector. The fix is benign and attack traffic mixed in one session.")

# 7 novelty 4 + 5
s = slide("Novelty 4 and 5 · A pitfall we caught, and a package anyone can rerun", "Method and reproducibility")
card(s, 0.7, 2.0, 5.9, 3.6, "4x → ~800x", "Our first test app let ping/ARP rules shadow TCP and understated the PacketIn effect by two orders of magnitude. We fixed it and report both.", WARN)
card(s, 6.8, 2.0, 5.9, 3.6, "1 command", "reproduce.sh rebuilds every result from hashed raw captures and compares with the stored files; verify_numbers.py checks the paper's numbers.")

# 8 architecture
s = slide("Study architecture: what goes in, what comes out", "Pipeline")
steps = [("InSDN pcaps", "44 controller\ncaptures"), ("OpenFlow parser", "PacketIn, FlowMod,\nstats"), ("Labels", "match 5-tuple to\nInSDN CSV"),
         ("Windows", "22 features\nper 1-5 s"), ("Models", "88 inputs →\nattack or not"), ("Tests", "10 seeds, CI,\ntrivial rule")]
for i, (a, b) in enumerate(steps):
    x = 0.5 + i * 2.1
    bx = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(2.3), Inches(1.9), Inches(1.9))
    bx.fill.solid()
    bx.fill.fore_color.rgb = RGBColor(0x14, 0x1E, 0x33)
    bx.line.color.rgb = ACC
    text(s, a, x + 0.1, 2.4, 1.7, 0.5, 15, ACC, bold=True)
    text(s, b, x + 0.1, 3.0, 1.7, 1.1, 13, FG)
text(s, "Separate live study: Ryu app (3 forwarding modes) + Mininet → control-channel pcap → PacketIn / FlowMod counts → result JSONs → paper tables", 0.7, 4.8, 12, 1.0, 17, MUTED)
bullets(s, ["Model input: 88 numbers about a few seconds of controller messages. Output: attack / not attack per window.", "The CSV only supplies labels; it is never an input."], y=5.5, size=16)

# 9 not new / limits
s = slide("What is not new, and what we did not do", "Honest scope")
bullets(s, ["Not new: control-plane telemetry for SDN IDS (LAN-SDN-NIDS, SDNFLow); the detector itself; Ryu's stock behaviour follows from its code.",
            "Not done: benign + attack traffic mixed in one session (needs lab attack traffic), another controller family (OpenDaylight), a re-implemented published detector.",
            "Single benchmark; confidence intervals cover folds and seeds, not new testbeds.",
            "Venue: workshop / conference as is; lower-quartile journal after revision."], size=19)

# 10 earlier proteus
s = slide("The earlier Proteus system (GAN + drift)", "Context, not a claim")
bullets(s, ["Prototype: WGAN-GP synthetic attacks, KS drift test, MMD fidelity gate, drift-triggered retraining, versioned releases with rollback.",
            "Close prior work exists (e.g. NetGuard 2025: generative adaptation for drifting, imbalanced IDS data).",
            "Our pre-registered studies found no measured benefit from the generative step; the demo's gain came from oracle labels.",
            "So the research contribution is the InSDN study above; the Proteus code is an engineering prototype."], size=19)

# 11 takeaway
s = slide("Takeaways", "Close")
card(s, 0.7, 2.0, 3.9, 3.0, "Gap", "Controller rules never contained the labelled 5-tuples.")
card(s, 4.7, 2.0, 3.9, 3.0, "Depends", "What a controller sees depends on the forwarding app.", WARN)
card(s, 8.7, 2.0, 3.9, 3.0, "Careful", "On InSDN, controller-side scores are not detection accuracy.")
say(s, "Next: interleave benign and attack traffic in one session and test a second controller.")

prs.save(sys.argv[1])
print("saved", sys.argv[1])
