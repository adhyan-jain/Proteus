"""Controller-native window features from real OpenFlow 1.3 control-channel captures (InSDN ONOS_*).

Per capture file and window W seconds:
  message counts: PACKET_IN, PACKET_OUT, FLOW_MOD, FLOW_REMOVED, flow-stats replies
  PACKET_IN header stats (frame embedded in PACKET_IN data): distinct src/dst MAC, src/dst IP,
    dst ports; TCP/UDP/ICMP/ARP fractions; TCP SYN-only fraction; mean frame length; entropies
  flow-stats deltas: sum/max per-entry packet & byte deltas since the previous reply, #entries
Also emits the static per-file inventory used for the granularity measurement.
"""
from __future__ import annotations

import collections
import json
import math
import socket
import struct
import sys
from pathlib import Path

import dpkt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from ofparse import of_messages  # noqa: E402
from ofsim import _key, flow_id  # noqa: E402

OXM = {0: "in_port", 3: "eth_dst", 4: "eth_src", 5: "eth_type", 10: "ip_proto", 11: "ipv4_src",
       12: "ipv4_dst", 13: "tcp_src", 14: "tcp_dst", 15: "udp_src", 16: "udp_dst", 19: "icmp_type"}
ATTACK_ONLY_IPS = set(json.loads((Path(__file__).parent.parent / "attacker_ips.json").read_text()))
LABCOLS = ["att_csv", "att_ip", "norm_csv", "unm_ip", "nonip", "unparsed"]
FEATS = ["n_pin", "n_pout", "n_fmod", "n_frem", "n_stats",
         "pin_src_mac", "pin_dst_mac", "pin_src_ip", "pin_dst_ip", "pin_dport",
         "f_tcp", "f_udp", "f_icmp", "f_arp", "f_syn", "mean_len", "h_src_ip", "h_dport",
         "st_entries", "st_dpkts", "st_dbytes", "st_max_dpkts"]


def _entropy(c: collections.Counter):
    n = sum(c.values())
    return -sum(v / n * math.log2(v / n) for v in c.values()) if n else 0.0


def _flow_stats(b):
    """Yield (match_key, duration_s, packet_count, byte_count, idle, hard, priority, fields)."""
    p = 8
    while p + 56 <= len(b):
        ln, = struct.unpack("!H", b[p:p + 2])
        if ln == 0:
            break
        ds, dn, pri, it, ht, _fl = struct.unpack("!IIHHHH", b[p + 4:p + 20])
        pc, bc = struct.unpack("!QQ", b[p + 32:p + 48])
        _mt, ml = struct.unpack("!HH", b[p + 48:p + 52])
        mb = b[p + 52:p + 48 + ml]
        q, fields = 0, []
        while q + 4 <= len(mb):
            _cls, fld, flen = struct.unpack("!HBB", mb[q:q + 4])
            fields.append(OXM.get(fld >> 1, str(fld >> 1)))
            q += 4 + flen
        yield (pri, mb), ds + dn / 1e9, pc, bc, it, ht, pri, tuple(fields)
        p += ln


def _pin_frame(b):
    if len(b) < 24:
        return None
    _ml = struct.unpack("!H", b[18:20])[0]
    off = 16 + (_ml + 7) // 8 * 8 + 2
    try:
        return dpkt.ethernet.Ethernet(b[off:])
    except (dpkt.UnpackError, struct.error):
        return None


def extract(path: Path, W: float, labels=None, exclude_attack=False):
    """labels: InSDN Flow ID -> label. exclude_attack drops attack-matched PACKET_INs (background view)."""
    wins = collections.defaultdict(lambda: {"cnt": collections.Counter(), "smac": set(), "dmac": set(),
                                            "sip": collections.Counter(), "dip": set(),
                                            "dport": collections.Counter(), "len": [], "proto": collections.Counter(),
                                            "syn": 0, "st": [], "lab": collections.Counter()})
    last = {}
    inv = {"match_sets": collections.Counter(), "timeouts": collections.Counter(), "stats_times": [],
           "pin": 0, "fmod": 0, "parser": {}, "pin_truncated": 0}
    t0 = None
    for ts, d, _v, t, b in of_messages(path, inv["parser"]):
        t0 = ts if t0 is None else t0
        w = wins[int((ts - t0) // W)]
        if t == 10 and d == "to_ctrl":
            e = _pin_frame(b)
            if e is not None and len(b) >= 6 and struct.unpack("!H", b[4:6])[0] > len(e):
                inv["pin_truncated"] += 1
            lab = _label(e, labels) if labels is not None else "unparsed"
            w["lab"][lab] += 1
            if exclude_attack and lab in ("att_csv", "att_ip"):
                continue
            w["cnt"]["pin"] += 1
            inv["pin"] += 1
            if e is None:
                continue
            w["smac"].add(e.src)
            w["dmac"].add(e.dst)
            w["len"].append(len(e))
            ip = e.data
            if isinstance(ip, dpkt.arp.ARP):
                w["proto"]["arp"] += 1
            elif isinstance(ip, dpkt.ip.IP):
                w["sip"][ip.src] += 1
                w["dip"].add(ip.dst)
                l4 = ip.data
                if isinstance(l4, dpkt.tcp.TCP):
                    w["proto"]["tcp"] += 1
                    w["dport"][l4.dport] += 1
                    if l4.flags & dpkt.tcp.TH_SYN and not l4.flags & dpkt.tcp.TH_ACK:
                        w["syn"] += 1
                elif isinstance(l4, dpkt.udp.UDP):
                    w["proto"]["udp"] += 1
                    w["dport"][l4.dport] += 1
                elif isinstance(l4, dpkt.icmp.ICMP):
                    w["proto"]["icmp"] += 1
        elif t == 13:
            w["cnt"]["pout"] += 1
        elif t == 14:
            w["cnt"]["fmod"] += 1
            inv["fmod"] += 1
        elif t == 11:
            w["cnt"]["frem"] += 1
        elif t == 19 and len(b) >= 2 and struct.unpack("!H", b[:2])[0] == 1:
            w["cnt"]["stats"] += 1
            inv["stats_times"].append(ts)
            for key, _dur, pc, bc, it, ht, pri, fields in _flow_stats(b):
                inv["match_sets"][fields] += 1
                inv["timeouts"][(it, ht, pri)] += 1
                if key in last:
                    dp, db = pc - last[key][0], bc - last[key][1]
                    if dp >= 0 and db >= 0:
                        w["st"].append((dp, db))
                last[key] = (pc, bc)
    if t0 is None:
        return np.zeros((0, len(FEATS)), np.float32), inv, np.zeros((0, len(LABCOLS)), np.float32)
    rows, labs = [], []
    for i in range(max(wins) + 1):
        w = wins.get(i)
        if w is None:
            rows.append([0.0] * len(FEATS))
            labs.append([0] * len(LABCOLS))
            continue
        lc = w["lab"]
        labs.append([lc[k] for k in LABCOLS])
        c, pr = w["cnt"], w["proto"]
        n_fr = max(sum(pr.values()), 1)
        st = np.array(w["st"]) if w["st"] else np.zeros((0, 2))
        rows.append([c["pin"], c["pout"], c["fmod"], c["frem"], c["stats"],
                     len(w["smac"]), len(w["dmac"]), len(w["sip"]), len(w["dip"]), len(w["dport"]),
                     pr["tcp"] / n_fr, pr["udp"] / n_fr, pr["icmp"] / n_fr, pr["arp"] / n_fr,
                     w["syn"] / max(pr["tcp"], 1), float(np.mean(w["len"])) if w["len"] else 0.0,
                     _entropy(w["sip"]), _entropy(w["dport"]),
                     len(st), st[:, 0].sum() if len(st) else 0, st[:, 1].sum() if len(st) else 0,
                     st[:, 0].max() if len(st) else 0])
    return np.asarray(rows, np.float32), inv, np.asarray(labs, np.float32)


def _label(e, labels):
    """Category of a PACKET_IN frame (one of LABCOLS):
    att_csv/norm_csv: 5-tuple (either direction) matches an attack/Normal InSDN CSV Flow ID;
    att_ip: unmatched, but involves an IP occurring only in attack-labelled CSV flows (sensitivity rule);
    unm_ip: other IP packet; nonip: ARP/LLDP/other; unparsed: frame could not be decoded."""
    if e is None:
        return "unparsed"
    if not isinstance(e.data, dpkt.ip.IP):
        return "nonip"
    k, _ = _key(e.data)
    f1, f2 = flow_id(k)
    lab = labels.get(f1) or labels.get(f2)
    if lab:
        return "norm_csv" if lab == "Normal" else "att_csv"
    if socket.inet_ntoa(k[0]) in ATTACK_ONLY_IPS or socket.inet_ntoa(k[1]) in ATTACK_ONLY_IPS:
        return "att_ip"
    return "unm_ip"


def label_of(path: Path) -> str:
    g = path.parent.name.lower()
    if "normal" in str(path).lower():
        return "normal"
    for k in ("brute", "ddos", "dos", "exploit", "probe", "web", "botnet", "bot"):
        if k in g:
            return k
    return g


if __name__ == "__main__":
    from build import load_labels
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    labels = load_labels()
    meta = {}
    files = sorted(p for p in root.rglob("*") if p.is_file() and "onos" in p.name.lower())
    for i, f in enumerate(files):
        for W in (1.0, 5.0):
            X, inv, L = extract(f, W, labels)
            np.save(out / f"c{i:03d}_W{W:g}.npy", X)
            np.save(out / f"c{i:03d}_W{W:g}_lab.npy", L)
            Xb, _, _ = extract(f, W, labels, exclude_attack=True)
            np.save(out / f"c{i:03d}_W{W:g}_bg.npy", Xb)
            if W == 1.0:
                L1, inv1 = L, inv
        gaps = np.diff(sorted(inv1["stats_times"]))
        meta[f"c{i:03d}"] = {"file": str(f.relative_to(root)), "label": label_of(f), "windows_1s": int(len(L1)),
            "packet_in": inv1["pin"], "flow_mod": inv1["fmod"], "stats_replies": len(inv1["stats_times"]),
            "packet_in_by_category": {k: int(L1[:, j].sum()) for j, k in enumerate(LABCOLS)},
            "packet_in_truncated": inv1["pin_truncated"], "parser": inv1["parser"],
            "stats_gap_median_s": float(np.median(gaps)) if len(gaps) else None,
            "match_sets": {"|".join(k): v for k, v in inv1["match_sets"].items()},
            "timeouts_idle_hard_prio": {str(k): v for k, v in inv1["timeouts"].items()}}
        m = meta[f"c{i:03d}"]
        print(i, m["label"], m["windows_1s"], m["packet_in"], json.dumps(m["packet_in_by_category"]),
              json.dumps(m["parser"]), m["packet_in_truncated"], flush=True)
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
