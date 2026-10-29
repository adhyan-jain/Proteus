import { ci, DT, J, MODE, PageHead, Section, Why } from "@/components/new-ui/study";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function modeRows(s: any) {
  return ["mac", "fivetuple", "fivetuple_short"].map((m) => [MODE[m], ci(s[m].packet_in_tcp), ci(s[m].flow_mods), ci(s[m].fivetuple_entries_per_reply)]);
}
const HEAD = ["Forwarding mode", "TCP PacketIns / run", "FlowMods / run", "Per-flow entries per 1 s poll"];

export default function Forwarding() {
  const one = J("live_modes_v4_one10.json").summary;
  const l3 = J("live_modes_v4_linear3.json").summary;
  const v2 = J("live_modes_v2.json").summary;
  const st = J("stock_ryu_flowmods.json");
  return (
    <>
      <PageHead kicker="Novelty 2 and 4" title="The forwarding app decides what the controller sees" intro="A small Mininet network with Open vSwitch and a Ryu controller, benign traffic only: five hosts fetch files (16 KB to 1 MB) from an HTTP server or ping it, for 90 s per run. The controller is a learning switch whose rule granularity we set. Nothing else changes between modes, so any difference is caused by the forwarding setting." />
      <Section title="The three forwarding modes">
        <p><b>MAC-pair:</b> one rule per pair of MAC addresses (what ONOS installed in InSDN). <b>Per-flow, 10 s idle:</b> one rule per TCP or UDP 5-tuple, removed after 10 s without traffic. <b>Per-flow, 2 s idle:</b> the same with a 2 s idle timeout. The controller also polls flow statistics once per second, like a monitoring app would.</p>
      </Section>
      <Section title="One switch" desc="10 runs per mode, mean ± 95% CI">
        <Why>PacketIn is the controller&apos;s workload: every new connection under per-flow rules sends the controller a message, while MAC-pair rules need only a handful. The last column is how many per-flow entries a 1 s poller sees in one statistics reply; a shorter timeout makes entries expire between polls.</Why>
        <DT head={HEAD} rows={modeRows(one)} />
        <p className="text-muted-foreground">Per-flow forwarding sent 665× to 1,752× more TCP PacketIns than MAC-pair in every paired run. With a 2 s idle timeout a 1 s poller sees about a quarter of the entries (ratio 0.234 to 0.246 in all ten pairs). In MAC-pair mode statistics replies contain only the table-miss rule and MAC-pair entries.</p>
      </Section>
      <Section title="Three-switch chain" desc="10 runs per mode; hosts h1 to h6, server two hops from h1 and h2">
        <Why>Repeats the study on a loop-free chain of three switches to check the effect is not an artefact of a single switch. It holds; the ratio is smaller only because the MAC-pair baseline rises with the extra hops.</Why>
        <DT head={HEAD} rows={modeRows(l3)} />
      </Section>
      <Section title="A second controller application: Ryu's stock simple_switch_13" desc={`${st.runs} runs of 60 s, unmodified code`}>
        <Why>Checks that MAC-pair behaviour is not a quirk of our own app. Ryu&apos;s own example installs only MAC-pair rules, so the controller never sees IP or port detail. This follows from the application&apos;s code; it does not test OpenDaylight or ONOS under other apps.</Why>
        <DT head={["Rule matches on", "FlowMods"]} rows={Object.entries(st.total_by_match_structure).map(([k, v]) => [k, String(v)])} />
        <p className="text-muted-foreground">PacketIns per run: {st.packet_in_per_run.join(", ")}.</p>
      </Section>
      <Section title="The flawed first campaign (Novelty 4)" desc="Reported on purpose">
        <Why>Our first app also installed MAC-pair rules for ping and ARP in every mode. Those rules also matched later TCP between the same hosts, so most connections never reached the controller. The result looked like a 4× effect with a wide interval, instead of hundreds of times.</Why>
        <DT head={["App version", "Per-flow TCP PacketIns", "MAC-pair TCP PacketIns", "Ratio"]} rows={[
          ["First app (flawed, 5 runs)", ci(v2.fivetuple.packet_in_tcp), ci(v2.mac.packet_in_tcp), (v2.fivetuple.packet_in_tcp.mean / v2.mac.packet_in_tcp.mean).toFixed(1) + "×"],
          ["Fixed app (10 runs)", ci(one.fivetuple.packet_in_tcp), ci(one.mac.packet_in_tcp), (one.fivetuple.packet_in_tcp.mean / one.mac.packet_in_tcp.mean).toFixed(0) + "×"],
        ]} />
        <p className="text-muted-foreground">Lesson for anyone measuring a controller: an overlapping coarse rule can hide traffic from it by two orders of magnitude, regardless of the mode&apos;s nominal granularity.</p>
      </Section>
    </>
  );
}
