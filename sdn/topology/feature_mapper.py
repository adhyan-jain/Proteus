"""Maps live OpenFlow 1.3 flow-stats entries onto Stage 1's unified feature schema
(`proteus/data_full.py`'s `get_feature_schema()` / column-naming convention).

Deliberately stdlib-only (no `ryu` import) so it can be unit-tested under the main `.venv`
(Python 3.12) as well as `.venv-ryu` (Python 3.8), and so the mapping logic is testable in
isolation from a running controller. `ryu_ids_app.py` builds the plain-dict input this module
expects from live `OFPFlowStatsReply` bodies and calls `map_flow_stat_to_schema()` directly.

## What a single OpenFlow flow-stats entry actually is

An OVS/OpenFlow 1.3 flow-table entry aggregates counters (`packet_count`, `byte_count`,
`duration_sec`/`duration_nsec`) for everything matching one flow-mod's match fields, since that
entry was installed, polled on demand (we poll every `POLL_INTERVAL_SEC` seconds from
`ryu_ids_app.py`). This is NOT the same object CICFlowMeter (the tool that generated the
CICIDS2017/InSDN unified schema) emits: CICFlowMeter tracks one full bidirectional flow
(5-tuple, both directions, from first packet to a completion/idle timeout) and computes ~80
statistical features over its inter-arrival times, packet-length distribution, TCP flags, etc.
A single live OpenFlow flow-stats entry gives us far less: essentially a running total, not a
completed-flow distribution.

## What this mapper CAN populate, and how

The L2-switch app installs flows matched on `(in_port, eth_src, eth_dst)` plus whatever L3/L4
fields are present in the packet that triggered the table-miss (`ip_proto`, `ipv4_src`,
`ipv4_dst`, `tcp_src`/`tcp_dst` or `udp_src`/`udp_dst`) -- see `ryu_ids_app.py`'s
`add_flow_from_packet_in`. Each such entry is effectively a coarse proxy for one *direction* of
a 5-tuple flow. From that we can honestly derive:

  - `flow_duration`   <- `duration_sec` (+ `duration_nsec`/1e9), converted to the same unit
                         CICFlowMeter uses (microseconds) -- see `_DURATION_UNIT_NOTE` below.
  - `protocol`         <- `ip_proto` (IANA protocol number; CICIDS2017's raw `Protocol` column
                         is already numeric -- 6/TCP, 17/UDP, 0/other -- so no conversion needed,
                         this passes straight through the schema's `protocol` categorical column
                         convention).
  - `dst_port`          <- `tcp_dst` or `udp_dst` from the match, when present.
  - `total_fwd_packet`  <- `packet_count`, *under the explicit assumption that this entry is the
                         forward direction* (the direction that triggered the initial
                         packet-in). See limitation below -- this is a real assumption, not a
                         verified fact about which side initiated the flow.
  - `total_length_of_fwd_packet` <- `byte_count`, same forward-direction assumption.
  - `flow_bytes_per_s`  <- `byte_count / duration_sec` (when duration_sec > 0).
  - `flow_packets_per_s`, `fwd_packets_per_s` <- `packet_count / duration_sec` (same value for
                         both under the forward-direction assumption, since we have no separate
                         backward counter here).
  - `average_packet_size`, `packet_length_mean` <- `byte_count / packet_count` (a coarse mean;
                         CICFlowMeter's version also folds in header-vs-payload accounting we
                         don't have access to here).

## What this mapper CANNOT populate from a live OpenFlow stat poll alone, and why

Left as `None` (schema columns present, value explicitly missing, never fabricated):

  - **Backward-direction columns** (`total_bwd_packets`, `total_length_of_bwd_packet`,
    `bwd_packets_per_s`, `bwd_header_length`, `bwd_iat_*`, `bwd_seg_size_avg`, ...): would
    require pairing this entry with the reverse-5-tuple flow-table entry (swapped src/dst) and
    is not implemented in this stage -- a real, documented gap, not an oversight. The extension
    point in `ryu_ids_app.py` is where that pairing would be added.
  - **Any inter-arrival-time statistic** (`flow_iat_mean/std/max/min`, `fwd_iat_*`, `bwd_iat_*`,
    `active_*`, `idle_*`): OpenFlow flow-stats give only aggregate counters at poll time, not
    per-packet timestamps. Would require packet-level capture (e.g. a `packet_in` timestamp
    log per flow), out of scope for this stage.
  - **TCP flag counts** (`fin_flag_count`, `syn_flag_count`, `rst_flag_count`, `psh_flag_count`,
    `ack_flag_count`, `urg_flag_count`, `cwr_flag_count`, `ece_flag_count`): standard OpenFlow
    flow-stats do not count flag occurrences within a matched flow; would require per-packet
    inspection at the controller (expensive at line rate, and not what a flow-stats poll gives).
  - **Header-length, subflow, bulk-transfer, and TCP-window columns**
    (`fwd_header_length`, `bwd_header_length`, `subflow_*`, `*_bulk_*`, `fwd_init_win_bytes`,
    `bwd_init_win_bytes`, `fwd_seg_size_*`, `bwd_seg_size_avg`, `fwd_act_data_pkts`): not exposed
    by OpenFlow flow-stats counters at all.
  - **Packet-length distribution stats** (`packet_length_std/min/max/variance`,
    `fwd_packet_length_*`, `bwd_packet_length_*`): only a mean is derivable (byte_count /
    packet_count); no per-packet length samples are available from an aggregate counter.

This is intentionally a partial, honestly-labeled mapping -- see the module docstring above and
`STATUS.md` for the summary. Extending it (flow pairing, packet-in-timestamp IAT tracking) is
future work, not silently faked here.
"""
from __future__ import annotations

from typing import Optional, TypedDict

# CICFlowMeter (the tool behind the CICIDS2017/InSDN unified schema) reports Flow Duration in
# microseconds. OpenFlow's duration_sec/duration_nsec is wall-clock seconds since the flow entry
# was installed. We convert to microseconds so the value is at least unit-comparable with the
# schema's `flow_duration` column, though note this measures "time since flow-mod install" (a
# proxy skewed by whatever `POLL_INTERVAL_SEC` the entry has been alive for), not CICFlowMeter's
# "time from first packet to flow completion/timeout" -- a real semantic difference, documented
# here rather than glossed over.
_DURATION_UNIT_NOTE = (
    "flow_duration is derived from OpenFlow's duration_sec/duration_nsec (time since the "
    "flow-mod was installed), converted to microseconds to match CICFlowMeter's unit -- it is "
    "NOT the same measurement as CICFlowMeter's first-packet-to-completion duration."
)

# Every column this mapper is capable of ever producing a numeric value for. Every other
# unified-schema column is intentionally left absent from the returned dict (never set to 0.0,
# which would look like a real measured zero rather than "not derivable from this data source").
POPULATED_COLUMNS = (
    "flow_duration",
    "protocol",
    "dst_port",
    "total_fwd_packet",
    "total_length_of_fwd_packet",
    "flow_bytes_per_s",
    "flow_packets_per_s",
    "fwd_packets_per_s",
    "average_packet_size",
    "packet_length_mean",
)

# Representative sample of unified-schema columns this mapper cannot populate from a live
# OpenFlow flow-stats poll alone (see the module docstring for the full breakdown and why).
# Not exhaustive of all 80 columns -- exhaustive would just be "everything not in
# POPULATED_COLUMNS above" -- kept here so a caller/reader has concrete examples without reading
# the full docstring.
KNOWN_UNPOPULATED_COLUMNS = (
    "total_bwd_packets", "total_length_of_bwd_packet", "bwd_packets_per_s",
    "flow_iat_mean", "flow_iat_std", "fwd_iat_mean", "bwd_iat_mean",
    "active_mean", "idle_mean",
    "fin_flag_count", "syn_flag_count", "rst_flag_count", "psh_flag_count",
    "ack_flag_count", "urg_flag_count", "cwr_flag_count", "ece_flag_count",
    "fwd_header_length", "bwd_header_length",
    "subflow_fwd_packets", "subflow_bwd_packets",
    "fwd_init_win_bytes", "bwd_init_win_bytes",
    "packet_length_std", "packet_length_max", "packet_length_min", "packet_length_variance",
)


class RawFlowStat(TypedDict, total=False):
    """Plain-dict shape `ryu_ids_app.py` builds from a live `OFPFlowStatsReply` entry (`stat`)
    before calling `map_flow_stat_to_schema()`. Kept as a plain dict (not a ryu type) so this
    module has zero dependency on ryu being importable."""
    duration_sec: int
    duration_nsec: int
    packet_count: int
    byte_count: int
    ip_proto: Optional[int]
    tcp_dst: Optional[int]
    udp_dst: Optional[int]


def map_flow_stat_to_schema(raw: RawFlowStat) -> dict:
    """Maps one live OpenFlow flow-stats entry onto unified-schema column names.

    Returns a dict containing only the columns this mapper can honestly derive (see
    `POPULATED_COLUMNS`) -- every other unified-schema column is simply absent from the result,
    never filled with a fabricated 0.0/None-as-zero. Callers that need every schema column
    present (e.g. to build a fixed-width feature vector for a classifier) should reindex against
    `proteus.data_full.get_feature_schema()`'s `feature_columns` and fill the gaps with an
    explicit missing-value sentinel appropriate to that use, not this module's job.
    """
    duration_sec = raw.get("duration_sec", 0) or 0
    duration_nsec = raw.get("duration_nsec", 0) or 0
    duration_s = duration_sec + duration_nsec / 1e9

    packet_count = raw.get("packet_count", 0) or 0
    byte_count = raw.get("byte_count", 0) or 0

    dst_port = raw.get("tcp_dst")
    if dst_port is None:
        dst_port = raw.get("udp_dst")

    out: dict = {
        "flow_duration": duration_s * 1e6,  # seconds -> microseconds, see _DURATION_UNIT_NOTE
        "protocol": raw.get("ip_proto"),
        "dst_port": dst_port,
        "total_fwd_packet": packet_count,
        "total_length_of_fwd_packet": byte_count,
    }

    if duration_s > 0:
        out["flow_bytes_per_s"] = byte_count / duration_s
        out["flow_packets_per_s"] = packet_count / duration_s
        out["fwd_packets_per_s"] = packet_count / duration_s
    else:
        # A just-installed flow entry can report duration_sec == 0 on the very first poll.
        # CICFlowMeter would never emit a rate feature for a zero-duration flow either (this is
        # exactly the +/-inf case proteus/data_full.py's cleaning step already guards against
        # for the offline dataset) -- so we leave these absent here rather than divide by zero
        # or fabricate a rate.
        pass

    if packet_count > 0:
        mean_len = byte_count / packet_count
        out["average_packet_size"] = mean_len
        out["packet_length_mean"] = mean_len

    return out
