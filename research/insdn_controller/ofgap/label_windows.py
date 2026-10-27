"""Label control-channel windows from a source-side flow log (live/flowlog.py), not from IP heuristics.

For each W-second window (aligned to the first OpenFlow message, as in ctrlfeat.extract) count PACKET_INs whose embedded
frame matches a logged flow (src/dst IP, proto, dst port, PACKET_IN time within [t0 - slack, t1 + slack]) by class.
y = 1 iff the window has >= 1 PACKET_IN matched to an attack flow. Also emits the trivial baseline ("any IP PACKET_IN").
Usage: label_windows.py capture.pcap flows.jsonl W out.json
"""
import json
import sys
from pathlib import Path

import dpkt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from ctrlfeat import _pin_frame  # noqa: E402
from ofparse import of_messages  # noqa: E402

SLACK = 2.0


def load_flows(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def _match(flows, ts, src, dst, proto, dport):
    for fl in flows:
        if (fl["t0"] - SLACK <= ts <= fl["t1"] + SLACK and fl["src_ip"] == src and fl["dst_ip"] == dst
                and fl["proto"] == proto and (fl["dport"] is None or fl["dport"] == dport)):
            return fl["cls"]
    return None


def label_windows(pcap, flows, W):
    rows, t0 = {}, None
    for ts, d, _v, t, b in of_messages(Path(pcap)):
        t0 = ts if t0 is None else t0
        r = rows.setdefault(int((ts - t0) // W), dict(n_pin=0, n_ip_pin=0, attack=0, benign=0, unmatched=0))
        if t != 10 or d != "to_ctrl":
            continue
        r["n_pin"] += 1
        e = _pin_frame(b)
        ip = e.data if e is not None and isinstance(e.data, dpkt.ip.IP) else None
        if ip is None:
            continue
        r["n_ip_pin"] += 1
        tr = ip.data
        proto = {6: "tcp", 17: "udp", 1: "icmp"}.get(ip.p, str(ip.p))
        dport = getattr(tr, "dport", None)
        cls = _match(flows, ts, ".".join(map(str, ip.src)), ".".join(map(str, ip.dst)), proto, dport)
        r[cls or "unmatched"] += 1
    n = max(rows) + 1 if rows else 0
    A = np.array([[rows.get(i, {}).get(k, 0) for k in ("n_pin", "n_ip_pin", "attack", "benign", "unmatched")]
                  for i in range(n)])
    return dict(W=W, t0=t0, n_pin=A[:, 0].tolist(), y=(A[:, 2] > 0).astype(int).tolist(),
                trivial=(A[:, 1] > 0).astype(int).tolist(), unmatched=A[:, 4].tolist())


def bacc(y, p):
    y, p = np.asarray(y), np.asarray(p)
    if not (y == 1).any() or not (y == 0).any():
        return float("nan")
    return float((p[y == 1].mean() + (1 - p[y == 0].mean())) / 2)


if __name__ == "__main__":
    pcap, flows, W, out = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
    res = label_windows(pcap, load_flows(flows), W)
    res["trivial_bacc"] = bacc(res["y"], res["trivial"])
    Path(out).write_text(json.dumps(res))
    print(f"{sum(res['y'])}/{len(res['y'])} attack windows; trivial BAcc={res['trivial_bacc']:.3f}")
