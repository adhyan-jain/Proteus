"""Proteus's Ryu 4.34 controller app for Stage 5 (live SDN deployment) of the paper-grade
scale-up.

Two jobs:
  1. Basic L2 learning-switch forwarding, so the Mininet topology in topo.py actually carries
     traffic (built directly on `ryu.app.simple_switch_13.SimpleSwitch13`, Ryu's own reference
     app, confirmed working on this machine per STATUS.md -- extended, not reinvented).
  2. Periodic live OpenFlow flow-stats export, mapped onto Stage 1's unified feature schema via
     `feature_mapper.map_flow_stat_to_schema()` (see that module's docstring for exactly which
     schema columns can/cannot be populated from a live stat poll and why).

Run (requires the dedicated Ryu venv -- see sdn/setup_ryu_venv.sh):

    .venv-ryu/bin/ryu-manager sdn/topology/ryu_ids_app.py --verbose

This does NOT need root and does NOT need Mininet running to load -- `ryu-manager` will start
and bind its OpenFlow listener (default 0.0.0.0:6653) waiting for a switch to connect. Verified
in this session: `ryu-manager --verbose` loads this module cleanly (imports resolve, app
registers, listener binds) with no Mininet/root involved. What could NOT be verified without
root: an actual OVS switch (from topo.py, run with sudo) connecting to it and real flow-stats
replies arriving -- that needs the repo owner's sudo session, see STATUS.md.

## Extension point for Stage 6 (live classifier inference)

`on_schema_row(dpid, flow_key, schema_row)` below is the single hook a future stage should wire
a trained classifier into. It is called once per (datapath, flow) per poll interval with the
best-effort unified-schema dict from feature_mapper. Right now it just logs. Stage 6's job is to
replace/extend this with: reindex schema_row against
`proteus.data_full.get_feature_schema()['feature_columns']` (filling columns this mapper can't
populate with whatever missing-value convention the trained model expects), run inference, and
route drift-detector-flagged samples onward -- deliberately not done here per the Stage 5 scope
in the brief.
"""
import sys
from operator import attrgetter

from ryu.app import simple_switch_13
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, DEAD_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import ether_types, ethernet, ipv4, packet, tcp, udp

sys.path.insert(0, __file__.rsplit("/", 1)[0])  # allow `import feature_mapper` when run via
                                                  # ryu-manager from the repo root
from feature_mapper import map_flow_stat_to_schema  # noqa: E402

POLL_INTERVAL_SEC = 10


class ProteusIDSApp(simple_switch_13.SimpleSwitch13):
    """L2 learning switch (inherited as-is from Ryu's reference app) + periodic flow-stats
    export mapped onto the unified feature schema."""

    OFP_VERSIONS = simple_switch_13.SimpleSwitch13.OFP_VERSIONS

    def __init__(self, *args, **kwargs):
        super(ProteusIDSApp, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.monitor_thread = hub.spawn(self._monitor)

    # -- datapath lifecycle (same pattern as ryu.app.simple_monitor_13) -------------------------

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.info("datapath connected: %016x", datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.info("datapath disconnected: %016x", datapath.id)
                del self.datapaths[datapath.id]

    def _monitor(self):
        while True:
            for dp in list(self.datapaths.values()):
                self._request_flow_stats(dp)
            hub.sleep(POLL_INTERVAL_SEC)

    def _request_flow_stats(self, datapath):
        parser = datapath.ofproto_parser
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

    # -- flow-stats export, mapped onto the unified schema ---------------------------------------

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        dpid = ev.msg.datapath.id
        for stat in ev.msg.body:
            # Skip the table-miss entry itself (priority 0, wildcard match) -- it aggregates
            # every unmatched packet across all flows, not one flow, so it isn't a meaningful
            # row in the unified schema.
            if stat.priority == 0:
                continue

            match = stat.match
            raw = {
                "duration_sec": stat.duration_sec,
                "duration_nsec": stat.duration_nsec,
                "packet_count": stat.packet_count,
                "byte_count": stat.byte_count,
                "ip_proto": match.get("ip_proto"),
                "tcp_dst": match.get("tcp_dst"),
                "udp_dst": match.get("udp_dst"),
            }
            schema_row = map_flow_stat_to_schema(raw)

            flow_key = (
                match.get("in_port"), match.get("eth_src"), match.get("eth_dst"),
                match.get("ipv4_src"), match.get("ipv4_dst"),
            )
            self.on_schema_row(dpid, flow_key, schema_row)

    def on_schema_row(self, dpid, flow_key, schema_row):
        """Extension point -- see module docstring. Stage 6 (live classifier inference) replaces
        this method's body; Stage 5's job is just getting a correctly-mapped row here reliably."""
        self.logger.info("[schema-row] dpid=%016x flow=%s -> %s", dpid, flow_key, schema_row)

    # -- forwarding: install richer (L3/L4-aware) match fields on top of the inherited L2 miss
    #    handling, so flow-stats entries carry protocol/port info feature_mapper can use ---------

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = self._build_match(parser, in_port, eth, pkt)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            else:
                self.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                   in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    @staticmethod
    def _build_match(parser, in_port, eth, pkt):
        """L2-baseline match (in_port, eth_src, eth_dst), widened with L3/L4 fields when the
        triggering packet has them, so the resulting flow-table entry -- and therefore its
        flow-stats -- carries protocol/port info feature_mapper can map onto the unified schema.
        Falls back to the plain L2 match for non-IP traffic (ARP, etc.), same as
        simple_switch_13's behaviour."""
        fields = {"in_port": in_port, "eth_src": eth.src, "eth_dst": eth.dst}

        ip = pkt.get_protocol(ipv4.ipv4)
        if ip is None:
            return parser.OFPMatch(**fields)

        fields["eth_type"] = ether_types.ETH_TYPE_IP
        fields["ipv4_src"] = ip.src
        fields["ipv4_dst"] = ip.dst
        fields["ip_proto"] = ip.proto

        tcp_pkt = pkt.get_protocol(tcp.tcp)
        udp_pkt = pkt.get_protocol(udp.udp)
        if tcp_pkt is not None:
            fields["tcp_src"] = tcp_pkt.src_port
            fields["tcp_dst"] = tcp_pkt.dst_port
        elif udp_pkt is not None:
            fields["udp_src"] = udp_pkt.src_port
            fields["udp_dst"] = udp_pkt.dst_port

        return parser.OFPMatch(**fields)
