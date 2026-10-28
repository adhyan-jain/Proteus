"""Second-controller check: match structure of every FlowMod and PacketIn count in captures of Ryu's stock
simple_switch_13 (live/run_benign.py --modes stock). Usage: flowmod_stock.py <capture_dir> <out_json>"""
import collections
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ctrlfeat import OXM  # noqa: E402
from ofparse import of_messages  # noqa: E402

root, out = Path(sys.argv[1]), Path(sys.argv[2])
total, per = collections.Counter(), {}
for f in sorted(root.glob("stock_s*.pcap")):
    c, pin = collections.Counter(), 0
    for _ts, d, _v, t, b in of_messages(f):
        if t == 10 and d == "to_ctrl":
            pin += 1
        if t != 14 or d != "to_sw" or len(b) < 44:
            continue
        mlen = struct.unpack("!HH", b[40:44])[1]
        body, q, fields = b[44:40 + mlen], 0, []
        while q + 4 <= len(body):
            _cls, fld, flen = struct.unpack("!HBB", body[q:q + 4])
            fields.append(OXM.get(fld >> 1, str(fld >> 1)))
            q += 4 + flen
        c["|".join(fields) or "(table-miss)"] += 1
    per[f.name] = {"flowmods_by_match": dict(c), "packet_in": pin}
    total.update(c)
res = {"runs": len(per), "flowmods": int(sum(total.values())), "total_by_match_structure": dict(total),
       "ip_or_transport_fields_in_any_flowmod": any(k for k in total if any(x in k for x in ("ipv4_src", "tcp_src", "udp_src", "ip_proto"))),
       "packet_in_per_run": [v["packet_in"] for v in per.values()], "per_capture": per}
out.write_text(json.dumps(res, indent=1))
print(json.dumps({k: v for k, v in res.items() if k != "per_capture"}, indent=1))
