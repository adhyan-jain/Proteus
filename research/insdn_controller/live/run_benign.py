#!/usr/bin/env python3
"""Benign-traffic forwarding-app study: how the forwarding application changes what an IDS can observe.

For each FWD_MODE (see ryu_fwd.py) this starts a Ryu controller, a 1-switch / 6-host Mininet network, generates
ONLY benign traffic (HTTP downloads between hosts plus pings, random pacing), and records the OpenFlow control
channel (loopback TCP 6653) to a pcap with a stdlib raw-socket sniffer. No attack traffic is generated here.

Requires root (Mininet, raw socket) and system python3 with Mininet (not the repo venvs):
    sudo python3 live/run_benign.py --out live/out --modes mac fivetuple fivetuple_short --repeats 3 --duration 90
"""
import argparse
import os
import random
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path

from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.topo import Topo

HERE = Path(__file__).resolve().parent
RYU = HERE.parent.parent.parent / ".venv-ryu" / "bin" / "ryu-manager"
STOCK_APP = HERE.parent.parent.parent / ".venv-ryu/lib/python3.8/site-packages/ryu/app/simple_switch_13.py"


class OneSwitch(Topo):
    def build(self, n=6):
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        for i in range(1, n + 1):
            self.addLink(self.addHost(f"h{i}"), s1, cls=TCLink, bw=50)


class Linear3(Topo):
    """s1 - s2 - s3 (loop-free). h1,h2 on s1; h3,h4 on s2; h5,h6 on s3 (server h6 is two hops from h1/h2)."""
    def build(self, n=6):
        sw = [self.addSwitch(f"s{i}", protocols="OpenFlow13") for i in (1, 2, 3)]
        self.addLink(sw[0], sw[1], cls=TCLink, bw=50)
        self.addLink(sw[1], sw[2], cls=TCLink, bw=50)
        for i in range(1, n + 1):
            self.addLink(self.addHost(f"h{i}"), sw[(i - 1) // 2], cls=TCLink, bw=50)


TOPOS = {"one": OneSwitch, "linear3": Linear3}


class Sniffer(threading.Thread):
    """Write TCP port-6653 frames seen on loopback to a pcap (Ethernet linktype)."""

    def __init__(self, path):
        super().__init__(daemon=True)
        self.path, self.stop_flag = path, threading.Event()
        self.sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(3))
        self.sock.bind(("lo", 0))
        self.sock.settimeout(0.5)

    def run(self):
        with open(self.path, "wb") as f:
            f.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
            while not self.stop_flag.is_set():
                try:
                    buf = self.sock.recv(65535)
                except socket.timeout:
                    continue
                if len(buf) < 54 or buf[12:14] != b"\x08\x00" or buf[23] != 6:
                    continue
                ihl = (buf[14] & 0x0F) * 4
                sport, dport = struct.unpack("!HH", buf[14 + ihl:18 + ihl])
                if 6653 not in (sport, dport):
                    continue
                t = time.time()
                f.write(struct.pack("<IIII", int(t), int((t % 1) * 1e6), len(buf), len(buf)) + buf)

    def stop(self):
        self.stop_flag.set()
        self.join(timeout=3)


CLIENT = '''import random, subprocess, sys, time, urllib.request
host, seed, duration, log = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
random.seed(seed)
end, ok, fail, why = time.time() + duration, 0, 0, {}
while time.time() < end:
    try:
        if random.random() < 0.8:
            urllib.request.urlopen("http://%s:8000/f%d.bin" % (host, random.randint(0, 3)), timeout=3).read()
        else:
            subprocess.run(["ping", "-c", "1", "-W", "1", host], stdout=subprocess.DEVNULL, check=True)
        ok += 1
    except Exception as e:
        fail += 1
        k = "%s:%s" % (type(e).__name__, str(e)[:40])
        why[k] = why.get(k, 0) + 1
    time.sleep(random.uniform(0.05, 0.8))
open(log, "w").write("ok=%d fail=%d why=%r\\n" % (ok, fail, why))
'''


def one_run(mode, seed, duration, out_dir, topo="one"):
    out_dir.mkdir(parents=True, exist_ok=True)
    pcap = out_dir / f"{mode}_s{seed}.pcap"
    www = out_dir / "www"
    www.mkdir(exist_ok=True)
    for i in range(4):
        (www / f"f{i}.bin").write_bytes(os.urandom(2 ** (14 + 2 * i)))
    env = dict(os.environ, FWD_MODE=mode, POLL_S="1.0")
    app = STOCK_APP if mode == "stock" else HERE / "ryu_fwd.py"  # "stock": Ryu's bundled simple_switch_13, unmodified
    ryu = subprocess.Popen([str(RYU), str(app), "--ofp-tcp-listen-port", "6653"], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)
    sniff = Sniffer(str(pcap))
    sniff.start()
    net = Mininet(topo=TOPOS[topo](), switch=OVSKernelSwitch, controller=None, autoSetMacs=True)
    net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)
    net.start()
    try:
        time.sleep(3)
        server = net.get("h6")
        server.cmd(f"cd {www} && python3 -m http.server 8000 >/dev/null 2>&1 &")
        time.sleep(1)
        script = HERE / "_client.py"
        script.write_text(CLIENT)
        logs = [out_dir / f"clients_{mode}_s{seed}_h{i}.log" for i in range(1, 6)]
        for i in range(1, 6):
            net.get(f"h{i}").cmd(f"python3 {script} {server.IP()} {seed * 100 + i} {duration} {logs[i - 1]} "
                                 f">/dev/null 2>&1 &")
        time.sleep(duration + 4)
        done = [l.read_text().strip() for l in logs if l.exists()]
        print("  clients:", done if done else "NO CLIENT LOGS (traffic generation failed)", flush=True)
        if not done or all("ok=0 " in d for d in done):
            raise SystemExit("clients produced no successful requests; aborting (see " + str(out_dir) + ")")
    finally:
        net.stop()
        sniff.stop()
        ryu.terminate()
        ryu.wait(timeout=10)
        subprocess.run(["mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return pcap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--modes", nargs="+", default=["mac", "fivetuple", "fivetuple_short"])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--duration", type=int, default=90)
    ap.add_argument("--topo", choices=sorted(TOPOS), default="one")
    ap.add_argument("--seed-start", type=int, default=0)
    a = ap.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("run with sudo")
    setLogLevel("warning")
    random.seed(0)
    for seed in range(a.seed_start, a.seed_start + a.repeats):
        for mode in a.modes:
            print("run", mode, seed, flush=True)
            print("  ->", one_run(mode, seed, a.duration, a.out, a.topo), flush=True)


if __name__ == "__main__":
    main()
