"""Audit OpenFlow 1.3 multipart flow-statistics entries across all 44 InSDN ONOS captures.

Decodes:
- Match fields and EtherTypes (IPv4 0x800, ARP 0x806, LLDP 0x88cc, BDDP 0x8942)
- Instructions and Actions (specifically OFPAT_OUTPUT to OFPP_CONTROLLER vs physical ports)
- Rule priorities and counts per capture

Usage: python flowtable_audit.py <pcap_root> <out_json>
"""
import collections
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ofparse import of_messages  # noqa: E402
from ctrlfeat import OXM  # noqa: E402

OFPP_CONTROLLER = 0xfffffffd


def parse_instructions(b):
    """Parse OpenFlow 1.3 instructions and actions from instruction segment b."""
    q = 0
    actions = []
    while q + 4 <= len(b):
        itype, ilen = struct.unpack("!HH", b[q:q + 4])
        if ilen == 0:
            break
        ibody = b[q:q + ilen]
        if itype in (3, 4):  # OFPIT_WRITE_ACTIONS, OFPIT_APPLY_ACTIONS
            aq = 8
            while aq + 4 <= len(ibody):
                atype, alen = struct.unpack("!HH", ibody[aq:aq + 4])
                if alen == 0:
                    break
                abody = ibody[aq:aq + alen]
                if atype == 0:  # OFPAT_OUTPUT
                    port, max_len = struct.unpack("!IH", abody[4:10])
                    actions.append(("OUTPUT", port, max_len))
                else:
                    actions.append(("ACT", atype))
                aq += alen
        else:
            actions.append(("INST", itype))
        q += ilen
    return actions


def audit_captures(pcap_root: Path):
    files = sorted(p for p in pcap_root.rglob("*") if p.is_file() and "onos" in p.name.lower())
    per_capture = {}
    total_eth_type_counts = collections.Counter()
    total_mac_pair_counts = 0
    action_types = collections.Counter()
    captures_with_ipv4_punt = 0
    priority_by_kind = collections.defaultdict(collections.Counter)   # rule kind -> {priority: entry observations}

    for f in files:
        rel = str(f.relative_to(pcap_root))
        cap_stats = {
            "flow_stats_replies": 0,
            "total_entries": 0,
            "eth_type_entries": collections.Counter(),
            "mac_pair_entries": 0,
            "has_ipv4_controller_punt": False,
        }
        for ts, d, v, t, b in of_messages(f):
            if t == 19 and len(b) >= 2 and struct.unpack("!H", b[:2])[0] == 1:
                cap_stats["flow_stats_replies"] += 1
                p = 8
                while p + 56 <= len(b):
                    ln, = struct.unpack("!H", b[p:p + 2])
                    if ln == 0:
                        break
                    pri, = struct.unpack("!H", b[p + 12:p + 14])   # ofp_flow_stats: len, table, pad, dur_s, dur_ns, priority
                    mt, ml = struct.unpack("!HH", b[p + 48:p + 52])
                    mb = b[p + 52:p + 48 + ml]
                    q, fields = 0, []
                    eth_val = None
                    while q + 4 <= len(mb):
                        cls, fld, flen = struct.unpack("!HBB", mb[q:q + 4])
                        fname = OXM.get(fld >> 1, str(fld >> 1))
                        val = mb[q + 4:q + 4 + flen]
                        if fname == "eth_type" and flen == 2:
                            eth_val = struct.unpack("!H", val)[0]
                        fields.append(fname)
                        q += 4 + flen

                    inst_off = p + 48 + ((ml + 7) // 8 * 8)
                    acts = parse_instructions(b[inst_off:p + ln])
                    is_to_ctrl = any(a[0] == "OUTPUT" and a[1] == OFPP_CONTROLLER for a in acts)

                    cap_stats["total_entries"] += 1
                    if "eth_type" in fields and len(fields) == 1:
                        hex_eth = hex(eth_val) if eth_val else "unknown"
                        cap_stats["eth_type_entries"][hex_eth] += 1
                        total_eth_type_counts[hex_eth] += 1
                        priority_by_kind["eth_type_" + hex_eth][pri] += 1
                        if eth_val == 0x0800 and is_to_ctrl:
                            cap_stats["has_ipv4_controller_punt"] = True
                    elif "in_port" in fields and "eth_src" in fields and "eth_dst" in fields:
                        cap_stats["mac_pair_entries"] += 1
                        total_mac_pair_counts += 1
                        priority_by_kind["mac_pair"][pri] += 1

                    for a in acts:
                        action_types[a[0] if a[0] != "OUTPUT" else ("OUTPUT_CTRL" if a[1] == OFPP_CONTROLLER else "OUTPUT_PORT")] += 1
                    p += ln

        if cap_stats["has_ipv4_controller_punt"]:
            captures_with_ipv4_punt += 1
        cap_stats["eth_type_entries"] = dict(cap_stats["eth_type_entries"])
        per_capture[rel] = cap_stats

    summary = {
        "total_captures": len(files),
        "captures_with_flow_stats": sum(1 for c in per_capture.values() if c["flow_stats_replies"] > 0),
        "captures_with_ipv4_controller_punt": captures_with_ipv4_punt,
        "total_eth_type_entries": sum(total_eth_type_counts.values()),
        "eth_type_breakdown": dict(total_eth_type_counts),
        "total_mac_pair_entries": total_mac_pair_counts,
        "action_types": dict(action_types),
        "priority_by_kind": {k: {str(p): n for p, n in sorted(v.items())} for k, v in sorted(priority_by_kind.items())},
        "per_capture": per_capture,
    }
    return summary


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: flowtable_audit.py <pcap_root> <out_json>")
        sys.exit(1)
    pcap_dir = Path(sys.argv[1])
    out_file = Path(sys.argv[2])
    res = audit_captures(pcap_dir)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as fp:
        json.dump(res, fp, indent=2)
    print("Done. Wrote flowtable audit summary to", out_file)
    print(f"Total captures: {res['total_captures']}, with IPv4 punt: {res['captures_with_ipv4_controller_punt']}")
    print(f"EthType breakdown: {res['eth_type_breakdown']}")
