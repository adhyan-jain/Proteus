# Phase 1 lab spec: interleaved labelled testbed

Owner of attack traffic: the lab owner (isolated Mininet + OVS lab). Everything below is local-only.

1. Topology/controller: `live/run_benign.py` topology (1 switch, h1-h5 clients, h6 server), controller `live/ryu_fwd.py`,
   `FWD_MODE` in {mac, fivetuple, fivetuple_short}.
2. Each run = ONE session containing benign AND attack traffic concurrently. Benign clients and the lab owner's attack tool
   both wrap every flow they start in `live/flowlog.py` (`with log.flow(src,dst,proto,dport,"attack","<family>"): ...`),
   writing `<run>_flows.jsonl`. Attack family list is chosen by the lab owner and recorded per flow.
3. Capture simultaneously: control channel (TCP 6653, existing sniffer) and data-plane pcap per switch port.
4. >= 5 independent runs (seeds) per forwarding mode; add every capture and flow log to `capture_hashes.sha256`
   (`sha256sum`), never edit afterwards.
5. Label: `python ofgap/label_windows.py <run>.pcap <run>_flows.jsonl <W> <out>.json` gives per-window attack labels and the
   trivial "any IP PACKET_IN" baseline. Success criterion: the detector beats that baseline within a session, mean + 95% CI
   over runs; otherwise drop detection claims (plan decision gate).
