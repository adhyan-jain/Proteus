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
import socket
import dpkt
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent))
from ofparse import of_messages
from ofsim import _key
from ctrlfeat import _pin_frame

def reconstruct_flows_from_packetins(pcap_path: Path, idle_timeout: float = 120.0, max_duration: float = 120.0):
    """Reconstruct bidirectional 5-tuple flows from OFPT_PACKET_IN messages
    enforcing CICFlowMeter flow-expiration semantics (120s activity/flow timeout and TCP FIN/RST termination)."""
    active_flows = {}
    completed_flows = []
    total_pin = 0
    ip_pin = 0
    truncated_pin = 0

    for ts, direction, ver, mtype, b in of_messages(pcap_path):
        if mtype != 10 or direction != "to_ctrl":
            continue
        total_pin += 1
        if len(b) < 24:
            continue
        
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
        s_ip = socket.inet_ntoa(k[0])
        d_ip = socket.inet_ntoa(k[1])
        s_pt = int(k[3])
        d_pt = int(k[4])
        proto = int(k[2])
        flow_key = (
            min(s_ip, d_ip), max(s_ip, d_ip),
            min(s_pt, d_pt), max(s_pt, d_pt),
            proto
        )
        
        is_fin_rst = False
        tcp_flags = collections.Counter()
        if isinstance(ip.data, dpkt.tcp.TCP):
            tcp = ip.data
            for flag_name, bit in [("SYN", dpkt.tcp.TH_SYN), ("ACK", dpkt.tcp.TH_ACK), 
                                  ("PSH", dpkt.tcp.TH_PUSH), ("RST", dpkt.tcp.TH_RST), 
                                  ("FIN", dpkt.tcp.TH_FIN)]:
                if tcp.flags & bit:
                    tcp_flags[flag_name] += 1
            if tcp.flags & (dpkt.tcp.TH_FIN | dpkt.tcp.TH_RST):
                is_fin_rst = True
                
        if flow_key in active_flows:
            cur = active_flows[flow_key]
            if (ts - cur["last_ts"] > idle_timeout) or (ts - cur["start_ts"] > max_duration):
                completed_flows.append(cur)
                cur = {
                    "flow_key": flow_key,
                    "start_ts": ts,
                    "last_ts": ts,
                    "ts": [ts],
                    "lengths": [len(eth)],
                    "dirs": [1 if is_rev else 0],
                    "tcp_flags": tcp_flags
                }
                active_flows[flow_key] = cur
            else:
                cur["ts"].append(ts)
                cur["lengths"].append(len(eth))
                cur["dirs"].append(1 if is_rev else 0)
                cur["last_ts"] = ts
                for fl, cnt in tcp_flags.items():
                    cur["tcp_flags"][fl] += cnt
                if is_fin_rst:
                    completed_flows.append(cur)
                    del active_flows[flow_key]
        else:
            cur = {
                "flow_key": flow_key,
                "start_ts": ts,
                "last_ts": ts,
                "ts": [ts],
                "lengths": [len(eth)],
                "dirs": [1 if is_rev else 0],
                "tcp_flags": tcp_flags
            }
            if is_fin_rst:
                completed_flows.append(cur)
            else:
                active_flows[flow_key] = cur

    for cur in active_flows.values():
        completed_flows.append(cur)

    flow_summaries = []
    for f in completed_flows:
        ts_arr = np.array(f["ts"])
        lens = np.array(f["lengths"])
        dur = float(f["last_ts"] - f["start_ts"])
        iats = np.diff(ts_arr) if len(ts_arr) > 1 else np.array([0.0])
        
        n_fwd = sum(1 for d in f["dirs"] if d == 0)
        n_bwd = sum(1 for d in f["dirs"] if d == 1)
        k = f["flow_key"]
        
        flow_summaries.append({
            "flow_key": [str(k[0]), str(k[1]), int(k[2]), int(k[3]), int(k[4])],
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
        "distinct_flows": len(flow_summaries),
        "flows": flow_summaries
    }

def main():
    pcap_root = Path(sys.argv[1])
    out_file = Path(sys.argv[2])
    csv_dir = Path(__file__).resolve().parents[3] / "data/raw/insdn_official/extracted/InSDN_DatasetCSV"
    
    target_scenarios = [
        ("OVS_DDoS", "OVS_Group/DDoS/ONOS-DDoS-SYN.pcap", csv_dir / "OVS.csv", "DDoS"),
        ("OVS_Probe", "OVS_Group/Probe/ONOS_Probe-Docker.pcap", csv_dir / "OVS.csv", "Probe"),
        ("OVS_Web", "OVS_Group/web_attack/ONOS_SQL-Injection.pcap", csv_dir / "OVS.csv", "Web-Attack"),
        ("MS2_DoS", "Metsplotable-2_Group/metasploitable-2_dos/ONOS_DoS-SYN.pcapng", csv_dir / "metasploitable-2.csv", "DoS"),
        ("MS2_Probe", "Metsplotable-2_Group/metasploitable-2_probe/ONOS__probe_msf__scan.pcap", csv_dir / "metasploitable-2.csv", "Probe"),
        ("Normal_1", "Normal_Group/Normal_1/Normal-ONOS_1.pcap", csv_dir / "Normal_data.csv", "Normal"),
    ]
    
    results = {}
    for name, rel_path, csv_path, label in target_scenarios:
        full_path = pcap_root / rel_path
        if not full_path.exists():
            continue
        print(f"Reassembling flows for {name} ({rel_path})...", flush=True)
        summary = reconstruct_flows_from_packetins(full_path)
        
        recon_dict = collections.defaultdict(list)
        for f in summary["flows"]:
            recon_dict[tuple(f["flow_key"])].append(f)
            
        pkt_counts = [f["packets"] for f in summary["flows"]]
        durations = [f["duration"] for f in summary["flows"]]
        single = sum(1 for p in pkt_counts if p == 1)
        
        # Load CSV flows
        csv_dict = collections.defaultdict(list)
        csv_pkts = []
        csv_durs = []
        if csv_path.exists():
            df = pd.read_csv(csv_path, low_memory=False)
            df_sub = df[df["Label"].astype(str).str.strip() == label]
            for idx, r in df_sub.iterrows():
                s_ip, d_ip = str(r["Src IP"]), str(r["Dst IP"])
                s_pt, d_pt = int(r["Src Port"]), int(r["Dst Port"])
                proto = int(r["Protocol"])
                fkey = (min(s_ip, d_ip), max(s_ip, d_ip), min(s_pt, d_pt), max(s_pt, d_pt), proto)
                p_cnt = int(r["Tot Fwd Pkts"]) + int(r["Tot Bwd Pkts"])
                d_sec = float(r["Flow Duration"]) / 1e6
                csv_dict[fkey].append({"packets": p_cnt, "duration": d_sec})
                csv_pkts.append(p_cnt)
                csv_durs.append(d_sec)
        
        common = set(recon_dict.keys()) & set(csv_dict.keys())
        corr_p, corr_d = None, None
        spear_p, spear_d, ratio_p, med_rel_err_p = None, None, None, None
        mean_p_recon, mean_p_csv = None, None
        mean_d_recon, mean_d_csv = None, None
        if common:
            r_p = [float(np.mean([x["packets"] for x in recon_dict[k]])) for k in common]
            c_p = [float(np.mean([x["packets"] for x in csv_dict[k]])) for k in common]
            r_d = [float(np.mean([x["duration"] for x in recon_dict[k]])) for k in common]
            c_d = [float(np.mean([x["duration"] for x in csv_dict[k]])) for k in common]
            mean_p_recon = round(float(np.mean(r_p)), 2)
            mean_p_csv = round(float(np.mean(c_p)), 2)
            mean_d_recon = round(float(np.mean(r_d)), 2)
            mean_d_csv = round(float(np.mean(c_d)), 2)
            if len(common) > 1 and np.std(r_p) > 0 and np.std(c_p) > 0:
                corr_p = round(float(np.corrcoef(r_p, c_p)[0, 1]), 3)
            if len(common) > 1 and np.std(r_d) > 0 and np.std(c_d) > 0:
                corr_d = round(float(np.corrcoef(r_d, c_d)[0, 1]), 3)
            # rank correlation (robust to heavy tails) and magnitude bias, on the matched 5-tuples only
            if len(common) > 2 and np.std(r_p) > 0 and np.std(c_p) > 0:
                spear_p = round(float(stats.spearmanr(r_p, c_p)[0]), 3)
            if len(common) > 2 and np.std(r_d) > 0 and np.std(c_d) > 0:
                spear_d = round(float(stats.spearmanr(r_d, c_d)[0]), 3)
            ratio_p = round(float(np.sum(r_p) / np.sum(c_p)), 3) if np.sum(c_p) > 0 else None
            med_rel_err_p = round(float(np.median([(a - b) / b for a, b in zip(r_p, c_p) if b > 0])), 3)

        results[name] = {
            "total_packet_in": summary["total_packet_in"],
            "ip_packet_in": summary["ip_packet_in"],
            "distinct_reconstructed_flows": summary["distinct_flows"],
            "flows_with_single_packet": single,
            "flows_ge_2_packets": len(summary["flows"]) - single,
            "pct_single_packet_flows": round(100.0 * single / len(summary["flows"]), 1) if summary["flows"] else 0.0,
            "median_packets_per_flow": float(np.median(pkt_counts)) if pkt_counts else 0.0,
            "max_packets_per_flow": int(np.max(pkt_counts)) if pkt_counts else 0,
            "median_duration_s": round(float(np.median(durations)), 4) if durations else 0.0,
            "max_duration_s": float(np.max(durations)) if durations else 0.0,
            "csv_flows_total": len(df_sub) if csv_path.exists() else 0,
            "csv_distinct_5tuples": len(csv_dict),
            "csv_single_packet_pct": round(100.0 * sum(1 for p in csv_pkts if p == 1) / len(csv_pkts), 1) if csv_pkts else 0.0,
            "csv_median_packets": float(np.median(csv_pkts)) if csv_pkts else 0.0,
            "csv_median_duration_s": round(float(np.median(csv_durs)), 3) if csv_durs else 0.0,
            "matching_5tuples": len(common),
            "matching_recon_flows": sum(len(recon_dict[k]) for k in common),
            "matched_share_of_reconstructed_pct": round(100.0 * sum(len(recon_dict[k]) for k in common) / max(summary["distinct_flows"], 1), 1),
            "matched_share_of_csv_5tuples_pct": round(100.0 * len(common) / max(len(csv_dict), 1), 1),
            "packet_count_correlation": corr_p,
            "duration_correlation": corr_d,
            "packet_count_spearman": spear_p,
            "duration_spearman": spear_d,
            "packet_sum_ratio_recon_over_csv": ratio_p,
            "packet_median_relative_error": med_rel_err_p,
            "mean_packets_recon": mean_p_recon,
            "mean_packets_csv": mean_p_csv,
            "mean_duration_recon_s": mean_d_recon,
            "mean_duration_csv_s": mean_d_csv,
        }
        print(f"  {name}: {summary['distinct_flows']} flows reconstructed; {results[name]['pct_single_packet_flows']}% single-packet (CSV matching 5-tuples: {len(common)}, pkt corr: {corr_p}, dur corr: {corr_d})")
        
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as fp:
        json.dump(results, fp, indent=2)
    print("Done. Wrote results to", out_file)

if __name__ == "__main__":
    main()
