"""ORIGINAL application used for the first campaign (live/campaign): ICMP/ARP get MAC-pair entries in every
mode, which shadow TCP between the same hosts. Superseded by ryu_fwd.py; kept for reproducibility.

Ryu OpenFlow 1.3 learning switch whose flow-entry granularity is chosen by FWD_MODE.

  mac        : entries match (in_port, eth_src, eth_dst)       -- what ONOS `fwd` installed in InSDN
  fivetuple  : IPv4 TCP/UDP entries match the 5-tuple          -- falls back to MAC pair for non-IP
  fivetuple_short : like fivetuple with a 2 s idle timeout (flow-table pressure vs. visibility)

POLL_S (default 1.0) sets the flow-statistics polling period. Run with the Ryu venv (Python 3.8):
    FWD_MODE=mac .venv-ryu/bin/ryu-manager live/ryu_fwd.py --ofp-tcp-listen-port 6653
Benign forwarding only; contains no traffic generation.
"""
import os

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import ether_types, ethernet, ipv4, packet, tcp, udp
from ryu.ofproto import ofproto_v1_3

MODE = os.environ.get("FWD_MODE", "mac")
POLL_S = float(os.environ.get("POLL_S", "1.0"))
IDLE = {"mac": 10, "fivetuple": 10, "fivetuple_short": 2}[MODE]


class Fwd(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        hub.spawn(self._poll)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _features(self, ev):
        dp = ev.msg.datapath
        self.datapaths[dp.id] = dp
        p, ofp = dp.ofproto_parser, dp.ofproto
        actions = [p.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self._add(dp, 0, p.OFPMatch(), actions, idle=0)

    def _add(self, dp, prio, match, actions, idle):
        p, ofp = dp.ofproto_parser, dp.ofproto
        inst = [p.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(p.OFPFlowMod(datapath=dp, priority=prio, match=match, instructions=inst, idle_timeout=idle))

    def _match(self, dp, in_port, pkt, eth):
        p = dp.ofproto_parser
        ip = pkt.get_protocol(ipv4.ipv4)
        if MODE != "mac" and ip is not None:
            t, u = pkt.get_protocol(tcp.tcp), pkt.get_protocol(udp.udp)
            if t is not None:
                return p.OFPMatch(in_port=in_port, eth_type=0x0800, ipv4_src=ip.src, ipv4_dst=ip.dst,
                                  ip_proto=6, tcp_src=t.src_port, tcp_dst=t.dst_port)
            if u is not None:
                return p.OFPMatch(in_port=in_port, eth_type=0x0800, ipv4_src=ip.src, ipv4_dst=ip.dst,
                                  ip_proto=17, udp_src=u.src_port, udp_dst=u.dst_port)
        return p.OFPMatch(in_port=in_port, eth_src=eth.src, eth_dst=eth.dst)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in(self, ev):
        msg = ev.msg
        dp, ofp, p = msg.datapath, msg.datapath.ofproto, msg.datapath.ofproto_parser
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        if eth.ethertype in (ether_types.ETH_TYPE_LLDP, ether_types.ETH_TYPE_IPV6):
            return
        table = self.mac_to_port.setdefault(dp.id, {})
        table[eth.src] = in_port
        out_port = table.get(eth.dst, ofp.OFPP_FLOOD)
        actions = [p.OFPActionOutput(out_port)]
        if out_port != ofp.OFPP_FLOOD:
            self._add(dp, 1, self._match(dp, in_port, pkt, eth), actions, IDLE)
        dp.send_msg(p.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=in_port,
                                   actions=actions, data=msg.data))

    def _poll(self):
        while True:
            hub.sleep(POLL_S)
            for dp in list(self.datapaths.values()):
                dp.send_msg(dp.ofproto_parser.OFPFlowStatsRequest(dp))
