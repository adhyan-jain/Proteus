#!/usr/bin/env python3
"""Traffic generators run *inside* Mininet hosts (via `net.get('h1').cmd(...)` or the Mininet
CLI's `h1 python3 ...`) by smoke_test.sh, using each host's own network namespace. Stdlib-only
(socket/subprocess) so it needs nothing beyond the system python3 already present in every
Mininet host -- no extra packages (hping3/nmap/scapy) to install first.

Usage (inside a Mininet host's namespace):
    python3 gen_traffic.py benign <dst_ip>          # a handful of normal-looking TCP connects
    python3 gen_traffic.py attack-like <dst_ip>      # a fast multi-port connection burst
                                                      # (port-scan-shaped traffic, the same
                                                      # broad pattern CICIDS2017/InSDN label as
                                                      # "PortScan"/"Probe")
"""
import socket
import sys
import time


def benign(dst_ip: str, n: int = 5, port: int = 80):
    """A handful of ordinary TCP connection attempts to one port, spaced out -- the traffic
    shape a normal client makes, not a scan."""
    print(f"[benign] {n} spaced TCP connects to {dst_ip}:{port}")
    for i in range(n):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect((dst_ip, port))
        except OSError as e:
            print(f"  connect {i}: {e} (expected -- no server listening; the point is the "
                  f"flow reaching the controller/switch path, not a successful app response)")
        time.sleep(0.5)


def attack_like(dst_ip: str, port_start: int = 1, port_end: int = 200, timeout: float = 0.05):
    """A fast sweep across many ports in quick succession -- the traffic shape CICIDS2017/InSDN
    label as a port-scan/probe attack: many short-lived connection attempts to one host across
    a wide port range in a short time window. Not hping3/nmap (neither is installed on this
    machine as of this writing -- see STATUS.md), but the same recognizable pattern using only
    the stdlib socket module already available in every Mininet host."""
    print(f"[attack-like] scanning {dst_ip} ports {port_start}-{port_end}")
    opened = 0
    for port in range(port_start, port_end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                result = s.connect_ex((dst_ip, port))
                if result == 0:
                    opened += 1
        except OSError:
            pass
    print(f"[attack-like] scan complete, {opened} ports responded open")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    mode, dst = sys.argv[1], sys.argv[2]
    if mode == "benign":
        benign(dst)
    elif mode == "attack-like":
        attack_like(dst)
    else:
        print(f"unknown mode: {mode}")
        sys.exit(1)
