"""Software Flow Reconstruction from Controller PacketIns.

Reassembles bidirectional 5-tuple flows from OpenFlow 1.3 OFPT_PACKET_IN streams
across InSDN ONOS captures, extracts flow-level features (duration, packet counts,
byte volumes, IAT moments, TCP flags), and compares them against target-side ground truth.

Usage: python packetin_reconstruction.py <pcap_root> <out_json>
"""
import collections
import json
import struct
import sys
from pathlib import Path
import dpkt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from ofparse import of_messages
from ofsim import _key
from ctrlfeat import _pin_frame

def reconstruct_flows_from_packetins(pcap_path: Path):
    """Reconstruct bidirectional 5-tuple flows from OFPT_PACKET_IN messages."""
    flows = collections.defaultdict(lambda: {
        "ts": [],
        "lengths": [],
        "dirs": [],
        "tcp_flags": collections.Counter(),
        "is_ip": False
    })
    total_pin = 0
    ip_pin = 0
    truncated_pin = 0

    for ts, direction, ver, mtype, b in of_messages(pcap_path):
        if mtype != 10 or direction != "to_ctrl":
            continue
        total_pin += 1
        if len(b) < 24:
            continue
        
        # Check truncation via total_len field
        tot_len = struct.unpack("!H", b[4:6])[0]
        eth = _pin_frame(b)
        if eth is None:
            continue
        if tot_len > len(eth):
            truncated_pin += 1
            
        ip = eth.data
        if not isinstance(ip, dpkt.ip.IP):
            continue
            
        ip_pin += 1
        k, is_rev = _key(ip)
        flow_key = (
            min(k[0], k[1]), max(k[0], k[1]),
            min(k[3], k[4]), max(k[3], k[4]),
            k[2]
        )
        
        f = flows[flow_key]
        f["is_ip"] = True
        f["ts"].append(ts)
        f["lengths"].append(len(eth))
        f["dirs"].append(1 if is_rev else 0)
        
        if isinstance(ip.data, dpkt.tcp.TCP):
            tcp = ip.data
            for flag_name, bit in [("SYN", dpkt.tcp.TH_SYN), ("ACK", dpkt.tcp.TH_ACK), 
                                  ("PSH", dpkt.tcp.TH_PUSH), ("RST", dpkt.tcp.TH_RST), 
                                  ("FIN", dpkt.tcp.TH_FIN)]:
                if tcp.flags & bit:
                    f["tcp_flags"][flag_name] += 1

    flow_summaries = []
    for k, f in flows.items():
        ts_arr = np.array(f["ts"])
        lens = np.array(f["lengths"])
        dur = float(ts_arr[-1] - ts_arr[0]) if len(ts_arr) > 1 else 0.0
        iats = np.diff(ts_arr) if len(ts_arr) > 1 else np.array([0.0])
        
        n_fwd = sum(1 for d in f["dirs"] if d == 0)
        n_bwd = sum(1 for d in f["dirs"] if d == 1)
        
        flow_summaries.append({
            "flow_key": [str(x) for x in k],
            "packets": len(ts_arr),
            "bytes": int(np.sum(lens)),
            "duration": dur,
            "fwd_packets": n_fwd,
            "bwd_packets": n_bwd,
            "mean_len": float(np.mean(lens)),
            "mean_iat": float(np.mean(iats)),
            "syn": f["tcp_flags"]["SYN"],
            "ack": f["tcp_flags"]["ACK"],
            "rst": f["tcp_flags"]["RST"],
        })
        
    return {
        "total_packet_in": total_pin,
        "ip_packet_in": ip_pin,
        "truncated_packet_in": truncated_pin,
        "distinct_flows": len(flows),
        "flows": flow_summaries
    }

def main():
    pcap_root = Path(sys.argv[1])
    out_file = Path(sys.argv[2])
    
    target_scenarios = [
        ("OVS_DDoS", "OVS_Group/DDoS/ONOS-DDoS-SYN.pcap"),
        ("OVS_Probe", "OVS_Group/Probe/ONOS_Probe-Docker.pcap"),
        ("OVS_Web", "OVS_Group/web_attack/ONOS_SQL-Injection.pcap"),
        ("MS2_DoS", "Metsplotable-2_Group/metasploitable-2_dos/ONOS_DoS-SYN.pcapng"),
        ("MS2_Probe", "Metsplotable-2_Group/metasploitable-2_probe/ONOS__probe_msf__scan.pcap"),
        ("Normal_1", "Normal_Group/Normal_1/Normal-ONOS_1.pcap"),
    ]
    
    results = {}
    for name, rel_path in target_scenarios:
        full_path = pcap_root / rel_path
        if not full_path.exists():
            continue
        print(f"Reassembling flows for {name} ({rel_path})...", flush=True)
        summary = reconstruct_flows_from_packetins(full_path)
        
        pkt_counts = [f["packets"] for f in summary["flows"]]
        durations = [f["duration"] for f in summary["flows"]]
        
        results[name] = {
            "total_packet_in": summary["total_packet_in"],
            "ip_packet_in": summary["ip_packet_in"],
            "distinct_reconstructed_flows": summary["distinct_flows"],
            "flows_with_single_packet": sum(1 for p in pkt_counts if p == 1),
            "flows_ge_2_packets": sum(1 for p in pkt_counts if p >= 2),
            "pct_single_packet_flows": round(100.0 * sum(1 for p in pkt_counts if p == 1) / len(pkt_counts), 1) if pkt_counts else 0.0,
            "median_packets_per_flow": float(np.median(pkt_counts)) if pkt_counts else 0.0,
            "max_packets_per_flow": int(np.max(pkt_counts)) if pkt_counts else 0,
            "median_duration_s": float(np.median(durations)) if durations else 0.0,
            "max_duration_s": float(np.max(durations)) if durations else 0.0,
        }
        print(f"  {name}: {summary['distinct_flows']} flows reconstructed; {results[name]['pct_single_packet_flows']}% single-packet (median pkts/flow: {results[name]['median_packets_per_flow']})")
        
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as fp:
        json.dump(results, fp, indent=2)
    print("Done. Wrote results to", out_file)

if __name__ == "__main__":
    main()
