"""Minimal OpenFlow 1.3 control-channel parser for real ONOS<->OVS captures (TCP 6653)."""
from __future__ import annotations

import collections
import struct
import sys
from pathlib import Path

import dpkt

sys.path.insert(0, str(Path(__file__).parent))
from ofsim import _iter_packets  # noqa: E402

OF_PORTS = (6633, 6653)


def _plausible(b: bytes, i: int) -> bool:
    """OpenFlow 1.3 header at b[i:]: version 4, known message type, sane length."""
    if i + 8 > len(b):
        return False
    ver, typ, ln, _xid = struct.unpack("!BBHI", b[i:i + 8])
    return ver == 4 and typ <= 30 and 8 <= ln <= 65535


def _resync(b: bytes):
    """Offset of the next position that starts a chain of two plausible headers (or one that runs to the
    end of the buffer); None if the buffer holds no such position."""
    for i in range(1, len(b) - 7):
        if not _plausible(b, i):
            continue
        ln = struct.unpack("!H", b[i + 2:i + 4])[0]
        j = i + ln
        if j == len(b) or _plausible(b, j):
            return i
    return None


def of_messages(path: Path, stats=None):
    """Yield (ts, direction, version, type, body_bytes). TCP reassembly per direction, in-order, dedup by seq.
    stats (dict, optional) accumulates: messages, desyncs, dropped_bytes, dup_segments."""
    stats = {} if stats is None else stats
    for k in ("messages", "desyncs", "dropped_bytes", "dup_segments"):
        stats.setdefault(k, 0)
    bufs = collections.defaultdict(bytes)
    seen = collections.defaultdict(set)
    for ts, ip in _iter_packets(path):
        t = ip.data
        if not isinstance(t, dpkt.tcp.TCP) or not t.data:
            continue
        if t.sport not in OF_PORTS and t.dport not in OF_PORTS:
            continue
        key = (ip.src, t.sport, ip.dst, t.dport)
        if t.seq in seen[key]:
            stats["dup_segments"] += 1
            continue
        seen[key].add(t.seq)
        direction = "to_ctrl" if t.dport in OF_PORTS else "to_sw"
        bufs[key] += bytes(t.data)
        b = bufs[key]
        while len(b) >= 8:
            ver, typ, ln, _xid = struct.unpack("!BBHI", b[:8])
            if ln < 8 or ver not in (1, 4, 5, 6):
                stats["desyncs"] += 1
                skip = _resync(b)
                if skip is None:  # no plausible header in the buffered bytes yet: keep the tail, drop the rest
                    stats["dropped_bytes"] += max(len(b) - 7, 0)
                    b = b[-7:]
                    break
                stats["dropped_bytes"] += skip
                b = b[skip:]
                continue
            if len(b) < ln:
                break
            stats["messages"] += 1
            yield ts, direction, ver, typ, b[8:ln]
            b = b[ln:]
        bufs[key] = b


if __name__ == "__main__":
    for f in sys.argv[1:]:
        c = collections.Counter()
        for ts, d, v, t, body in of_messages(Path(f)):
            sub = struct.unpack("!H", body[:2])[0] if t in (18, 19) and len(body) >= 2 else None
            c[(d, v, t, sub)] += 1
        print(f, sorted(c.items(), key=lambda x: -x[1])[:12])
