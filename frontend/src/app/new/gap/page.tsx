import { DT, J, Mono, PageHead, Section, Why } from "@/components/new-ui/study";

export default function Gap() {
  const fm = J("flowmod_matches.json");
  const st = J("stock_ryu_flowmods.json");
  const gap = J("gap_attack_v2.json");
  const rows = Object.entries(gap).map(([k, v]) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const d = v as any;
    return [k.split("/")[1] ?? k, d.label, (d.target?.packets ?? null)?.toLocaleString() ?? "n/a", d.controller.packet_in.toLocaleString(), d.packet_in_per_target_packet == null ? "n/a" : d.packet_in_per_target_packet.toFixed(2), d.controller.flow_mod.toLocaleString(), Object.keys(d.controller.entry_observations_by_match).join(" ; ")];
  });
  return (
    <>
      <PageHead kicker="Novelty 1" title="The gap between what is labelled and what the controller saw" intro="InSDN labels 5-tuple flows computed at the target. The controller, however, only ever installed and reported coarse rules. This page shows exactly which header fields its rules matched, and how many PacketIns it received per packet that reached the target." />
      <Section title="Which fields do the controller's rules match?" desc={`All ${fm.flowmods.toLocaleString()} FlowMods in the 44 ONOS captures, and 5 runs of Ryu's stock app`}>
        <Why>A FlowMod is the controller telling the switch &quot;install this rule&quot;. The match fields say what the rule looks at. Without IP and port fields, a rule cannot count one 5-tuple flow separately from another between the same two hosts.</Why>
        <DT head={["Source", "Rule matches on", "FlowMods"]} rows={[
          ...Object.entries(fm.total_by_match_structure).map(([k, v]) => ["InSDN (ONOS)", <Mono key={k}>{k}</Mono>, String(v)]),
          ...Object.entries(st.total_by_match_structure).map(([k, v]) => ["Ryu stock app", <Mono key={"s" + k}>{k}</Mono>, String(v)]),
        ]} />
        <p className="text-muted-foreground">The same holds for flow-statistics replies: only two match structures ever appear (<Mono>eth_type</Mono> and <Mono>in_port|eth_src|eth_dst</Mono>). A 5-tuple flow, the unit InSDN labels, is never a counter the controller can read.</p>
      </Section>
      <Section title="PacketIns the controller received per scenario" desc="Target-side capture vs controller capture of the same scenario">
        <Why>The controller cannot count 5-tuple flows, but it does receive a PacketIn for packets that miss the switch table. In most scenarios that is roughly one PacketIn per packet at the target (0.68 to 1.29 in 9 of 12). The two recordings are separate, so the ratios are indicative, not exact.</Why>
        <DT head={["Scenario", "Class", "Target packets", "Controller PacketIns", "PacketIn / packet", "FlowMods", "Entry match types in stats replies"]} rows={rows} />
        <p className="text-muted-foreground">The OVS DDoS scenario shows a ratio near 0.08 (6.5M target packets against 541k PacketIns), consistent with control-channel saturation under a spoofed flood; this was not tested directly.</p>
      </Section>
      <Section title="What this means">
        <p>A model trained on InSDN&apos;s CSV consumes statistics (inter-arrival moments, per-direction length moments, flag counts per 5-tuple) that this controller never receives. The deployable signal is the PacketIn header stream plus coarse MAC-pair counters. This describes the ONOS forwarding configuration used in InSDN; it is not a property of OpenFlow in general.</p>
      </Section>
    </>
  );
}
