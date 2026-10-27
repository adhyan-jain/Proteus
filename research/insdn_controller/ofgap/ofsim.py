"""OpenFlow 1.3 flow-table + stats-polling simulator over real PCAPs.

Models a reactive 5-tuple forwarding app (one unidirectional entry per 5-tuple, installed on
PacketIn, removed on idle timeout) and a controller polling flow stats every T seconds with a
given phase. Emits, per entry:
  - snapshots: what OFPFlowStatsReply gives at each poll (first K polls of the entry)
  - final: what OFPFlowRemoved gives (complete counters) -- the "benchmark view"
Only controller-observable quantities are recorded.
"""
from __future__ import annotations

import socket
import struct
from pathlib import Path

import dpkt
import numpy as np

SNAP_COLS = [
    "entry", "poll_idx", "t_poll", "t_start", "proto", "sport", "dport",
    "duration", "pkts", "bytes", "d_pkts", "d_bytes",
    "rev_present", "rev_pkts", "rev_bytes",
    "first_len", "first_flags",
]
FINAL_COLS = [
    "entry", "t_end", "t_start", "proto", "sport", "dport",
    "duration", "pkts", "bytes", "rev_present", "rev_pkts", "rev_bytes",
    "first_len", "first_flags",
]


def _iter_packets(path: Path):
    """Yield (ts, ip_packet) for IPv4 packets in a pcap/pcapng file."""
    with open(path, "rb") as f:
        magic = f.read(4)
        f.seek(0)
        rdr = dpkt.pcapng.Reader(f) if magic == b"\x0a\x0d\x0d\x0a" else dpkt.pcap.Reader(f)
        dl = rdr.datalink()
        for ts, buf in rdr:
            try:
                if dl == dpkt.pcap.DLT_EN10MB:
                    ip = dpkt.ethernet.Ethernet(buf).data
                elif dl == 113:  # Linux cooked
                    ip = dpkt.sll.SLL(buf).data
                elif dl == 276:
                    ip = dpkt.sll2.SLL2(buf).data
                elif dl in (12, 101, 228):
                    ip = dpkt.ip.IP(buf)
                else:
                    raise ValueError(f"unsupported datalink {dl} in {path}")
            except (dpkt.UnpackError, IndexError, struct.error):
                continue
            if isinstance(ip, dpkt.ip.IP):
                yield float(ts), ip


def _key(ip):
    l4 = ip.data
    sport = dport = 0
    flags = 0
    if isinstance(l4, (dpkt.tcp.TCP, dpkt.udp.UDP)):
        sport, dport = l4.sport, l4.dport
        if isinstance(l4, dpkt.tcp.TCP):
            flags = l4.flags
    return (ip.src, ip.dst, ip.p, sport, dport), flags


def simulate(paths, T: float, idle: float, phase: float, max_polls: int = 5):
    """Run one pcap timeline (files concatenated in time order). Returns (snaps, finals, keys)."""
    table = {}       # key -> [entry_id, t0, last, pkts, bytes, first_len, first_flags, polls, lp, lb]
    snaps, finals, keys = [], [], []
    next_id = 0
    next_poll = None

    def remove(k, e, t_end):
        r = table.get((k[1], k[0], k[2], k[4], k[3]))
        finals.append([e[0], t_end, e[1], k[2], k[3], k[4], t_end - e[1], e[3], e[4],
                       int(r is not None), r[3] if r else 0, r[4] if r else 0, e[5], e[6]])
        del table[k]

    def poll(t):
        for k in [k for k, e in table.items() if t - e[2] > idle]:
            remove(k, table[k], table[k][2] + idle)
        for k, e in table.items():
            if e[7] >= max_polls:
                continue
            r = table.get((k[1], k[0], k[2], k[4], k[3]))
            snaps.append([e[0], e[7], t, e[1], k[2], k[3], k[4], t - e[1], e[3], e[4],
                          e[3] - e[8], e[4] - e[9], int(r is not None),
                          r[3] if r else 0, r[4] if r else 0, e[5], e[6]])
            e[7] += 1
            e[8], e[9] = e[3], e[4]

    for p in paths:
        for ts, ip in _iter_packets(p):
            if next_poll is None:
                next_poll = ts + phase
            while next_poll <= ts:
                poll(next_poll)
                next_poll += T
            k, flags = _key(ip)
            e = table.get(k)
            if e is not None and ts - e[2] > idle:
                remove(k, e, e[2] + idle)
                e = None
            if e is None:
                e = [next_id, ts, ts, 0, 0, ip.len, flags, 0, 0, 0]
                keys.append(k)
                next_id += 1
                table[k] = e
            e[2] = ts
            e[3] += 1
            e[4] += ip.len
    if next_poll is not None:
        for k in list(table):
            remove(k, table[k], table[k][2] + idle)
    return (np.asarray(snaps, dtype=np.float64).reshape(-1, len(SNAP_COLS)),
            np.asarray(finals, dtype=np.float64).reshape(-1, len(FINAL_COLS)),
            keys)


def flow_id(k) -> str:
    """InSDN/CICFlowMeter-style canonical Flow ID candidates for a 5-tuple."""
    s, d = socket.inet_ntoa(k[0]), socket.inet_ntoa(k[1])
    return f"{s}-{d}-{k[3]}-{k[4]}-{k[2]}", f"{d}-{s}-{k[4]}-{k[3]}-{k[2]}"
