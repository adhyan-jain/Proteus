import { Bars } from "@/components/new-ui/charts";
import { COLORS } from "@/components/new-ui/colors";
import { Chip, Insight, J, PageHead, Section } from "@/components/new-ui/study";

export default function Forwarding() {
  const one = J("live_modes_v4_one10.json").summary;
  const l3 = J("live_modes_v4_linear3.json").summary;
  const v2 = J("live_modes_v2.json").summary;
  const st = J("stock_ryu_flowmods.json");
  const M = [["mac", "MAC-pair"], ["fivetuple_short", "Per-flow, 2 s idle"], ["fivetuple", "Per-flow, 10 s idle"]];
  const pin = M.map(([k, n]) => ({ name: n, one: one[k].packet_in_tcp.mean, three: l3[k].packet_in_tcp.mean }));
  const ent = M.slice(1).map(([k, n]) => ({ name: n, one: one[k].fivetuple_entries_per_reply.mean, three: l3[k].fivetuple_entries_per_reply.mean }));
  const ratio = [{ name: "First app (flawed)", r: v2.fivetuple.packet_in_tcp.mean / v2.mac.packet_in_tcp.mean }, { name: "Fixed app", r: one.fivetuple.packet_in_tcp.mean / one.mac.packet_in_tcp.mean }];
  const S = [{ key: "one", name: "1 switch", color: COLORS.teal }, { key: "three", name: "3-switch chain", color: COLORS.amber }];
  return (
    <>
      <PageHead kicker="Novelty 2 and 4" title="The forwarding app decides what the controller sees" intro="Mininet + Ryu, identical benign traffic, three forwarding settings, 10 runs each." />
      <Section title="TCP PacketIns per run" desc="Log scale. Per-flow rules send every new connection to the controller." tell="Same traffic, but per-flow rules send the controller about 850 times more PacketIns.">
        <Bars log height={300} data={pin} series={S} decimals={0} />
        <Chip>live_modes_v4_one10.json · live_modes_v4_linear3.json</Chip>
      </Section>
      <Section title="Per-flow entries a 1 s poller sees" desc="A shorter idle timeout makes entries expire between polls, hiding them." tell="A 2 s idle timeout hides about three quarters of the per-flow entries from a 1 s poller.">
        <Bars height={260} data={ent} series={S} decimals={1} />
      </Section>
      <Section title="A pitfall we caught in ourselves" desc="Ping/ARP MAC-pair rules also matched TCP, hiding it from the controller." tell="One shadowing rule made a roughly 850 times effect look like 4 times.">
        <Bars height={240} data={ratio} series={[{ key: "r", name: "Per-flow ÷ MAC-pair", color: COLORS.red }]} cellColors={[COLORS.red, COLORS.teal]} decimals={0} />
        <Chip>live_modes_v2.json (flawed, 5 runs)</Chip>
      </Section>
      <Section title="Second controller app: Ryu's stock switch" desc={`${st.flowmods} FlowMods over ${st.runs} runs: ${st.total_by_match_structure["in_port|eth_dst|eth_src"]} MAC-pair, ${st.total_by_match_structure["(table-miss)"]} table-miss, none with IP or ports.`}>
        <Chip>stock_ryu_flowmods.json</Chip>
      </Section>
      <Insight analogy="A receptionist who asks everyone for ID at every door is flooded; one who only checks which building you belong to is barely asked." gain="What a controller observes is set by the forwarding app, so a detector's inputs must be defined together with it." />
    </>
  );
}
