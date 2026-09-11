#!/usr/bin/env python3
"""Trivial Mininet topology for Proteus's live SDN deployment (Stage 5 of the paper-grade
scale-up). Deliberately simple: the point of this stage is a working live traffic path through
a real Ryu OpenFlow controller, not topology complexity.

    h1 --\\                          /-- h3
          s1 ======================= s2
    h2 --/                          \\-- h4

Two OVS switches (OpenFlow 1.3), two hosts per switch, one inter-switch link, one external
(remote) Ryu controller. h1/h2 stand in for one network segment, h3/h4 for another -- enough to
exercise cross-switch L2 forwarding and per-flow stats through two datapaths, without needing
more than 4 hosts to reason about.

Requires root (Mininet creates network namespaces at runtime) -- run with sudo, using the
SYSTEM python3 (Mininet 2.3.1b4 is installed there, not in .venv-ryu -- .venv-ryu is Ryu-only,
see CLAUDE.md's environment-discipline rule):

    sudo python3 sdn/topology/topo.py

or via the smoke test script (sdn/topology/smoke_test.sh), which also starts the Ryu controller
first. NOT run by this agent session -- no sudo access here (see STATUS.md). Import-checked
(`python3 -c "from mininet... import ..."` succeeds) and syntax-checked
(`python3 -m py_compile`), not yet executed against a live kernel.
"""
import argparse

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.topo import Topo


class ProteusTopo(Topo):
    """4 hosts, 2 switches, 1 inter-switch link, all under one external OpenFlow 1.3 controller."""

    def build(self):
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")

        h1 = self.addHost("h1", ip="10.0.0.1/24", mac="00:00:00:00:00:01")
        h2 = self.addHost("h2", ip="10.0.0.2/24", mac="00:00:00:00:00:02")
        h3 = self.addHost("h3", ip="10.0.0.3/24", mac="00:00:00:00:00:03")
        h4 = self.addHost("h4", ip="10.0.0.4/24", mac="00:00:00:00:00:04")

        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s2)
        self.addLink(h4, s2)
        self.addLink(s1, s2)


def run(controller_ip="127.0.0.1", controller_port=6653, autostart_cli=True):
    setLogLevel("info")

    topo = ProteusTopo()
    net = Mininet(
        topo=topo,
        switch=OVSKernelSwitch,
        link=TCLink,
        controller=None,  # added explicitly below so we can point at the external Ryu app
        autoSetMacs=True,
    )
    net.addController(
        "c0",
        controller=RemoteController,
        ip=controller_ip,
        port=controller_port,
    )

    info("*** Starting network\n")
    net.start()

    info("*** Testing connectivity (pingall)\n")
    loss = net.pingAll()
    if loss > 0:
        info(f"*** WARNING: pingAll reported {loss}% packet loss -- controller may not have "
             f"attached yet, or flows are not forwarding. Check the Ryu log.\n")
    else:
        info("*** pingAll: 0% loss -- controller path confirmed working end-to-end\n")

    if autostart_cli:
        info("*** Dropping to Mininet CLI. Type 'exit' to tear down.\n")
        CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-ip", default="127.0.0.1")
    parser.add_argument("--controller-port", type=int, default=6653)
    parser.add_argument("--no-cli", action="store_true",
                         help="Run pingAll then tear down immediately, no interactive CLI "
                              "(used by smoke_test.sh for a non-interactive pass/fail check).")
    args = parser.parse_args()
    run(controller_ip=args.controller_ip, controller_port=args.controller_port,
        autostart_cli=not args.no_cli)
