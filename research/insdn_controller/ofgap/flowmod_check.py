"""Tabulate the match fields of every OFPT_FLOW_MOD the controller sent, per capture (OpenFlow 1.3).

Complements the flow-statistics view: a flow entry that lives shorter than the polling gap never appears in a stats
reply, but its FlowMod does cross the control channel.
Usage: flowmod_check.py <ex_root> <out_json>
"""
import collections
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ctrlfeat import OXM  # noqa: E402
from ofparse import of_messages  # noqa: E402

root, out = Path(sys.argv[1]), Path(sys.argv[2])
total = collections.Counter()
per = {}
for f in sorted(p for p in root.rglob("*") if p.is_file() and "onos" in p.name.lower()):
    c = collections.Counter()
    for _ts, d, _v, t, b in of_messages(f):
        if t != 14 or d != "to_sw" or len(b) < 44:
            continue
        mtype, mlen = struct.unpack("!HH", b[40:44])
        body = b[44:40 + mlen]
        q, fields = 0, []
        while q + 4 <= len(body):
            _cls, fld, flen = struct.unpack("!HBB", body[q:q + 4])
            fields.append(OXM.get(fld >> 1, str(fld >> 1)))
            q += 4 + flen
        c["|".join(fields)] += 1
    per[str(f.relative_to(root))] = dict(c)
    total.update(c)
res = {"total_by_match_structure": dict(total), "flowmods": int(sum(total.values())),
       "ip_or_transport_fields_in_any_flowmod": any(("ipv4_src" in k or "tcp_src" in k or "udp_src" in k or
                                                      "ip_proto" in k) for k in total),
       "per_capture": per}
out.write_text(json.dumps(res, indent=1))
print(json.dumps({k: v for k, v in res.items() if k != "per_capture"}, indent=1))
