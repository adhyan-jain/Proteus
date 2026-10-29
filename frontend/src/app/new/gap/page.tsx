import { Bars } from "@/components/new-ui/charts";
import { COLORS } from "@/components/new-ui/colors";
import { Chip, Insight, J, PageHead, Section } from "@/components/new-ui/study";

export default function Gap() {
  const fm = J("flowmod_matches.json");
  const st = J("stock_ryu_flowmods.json");
  const gap = J("gap_attack_v2.json");
  const rows = Object.entries(gap)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .filter(([, v]) => (v as any).packet_in_per_target_packet != null)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .map(([k, v]) => ({ name: `${k.startsWith("Mets") ? "MS2" : "OVS"} ${(v as any).label}`, r: (v as any).packet_in_per_target_packet as number }));
  const label = (k: string) => (k === "in_port|eth_dst|eth_src" ? "MAC pair" : k === "eth_type" ? "EtherType" : "table-miss");
  const match = [...Object.entries(fm.total_by_match_structure).map(([k, v]) => ({ name: `InSDN · ${label(k)}`, v: v as number })), ...Object.entries(st.total_by_match_structure).map(([k, v]) => ({ name: `Ryu stock · ${label(k)}`, v: v as number }))];
  return (
    <>
      <PageHead kicker="Novelty 1" title="The controller never saw the labelled flows" intro="InSDN labels 5-tuple flows. We read every rule the controller installed." />
      <Section title="What the rules match on" desc={`${fm.flowmods.toLocaleString()} FlowMods in 44 captures, plus Ryu's stock app. IP/port fields: zero.`} tell="Every rule looked at MAC addresses or EtherType only, so no 5-tuple flow was ever visible to the controller.">
        <Bars horizontal log height={260} data={match} series={[{ key: "v", name: "FlowMods", color: COLORS.teal }]} cellColors={[COLORS.teal, COLORS.gray, COLORS.amber, COLORS.teal]} decimals={0} />
        <Chip>results/flowmod_matches.json</Chip>
      </Section>
      <Section title="PacketIns the controller got per target packet" desc="Each bar is one attack scenario. Around 1 means every packet went to the controller." tell="The controller sees a packet-by-packet stream (about 1 PacketIn per packet), not flows.">
        <Bars height={300} data={rows} series={[{ key: "r", name: "PacketIn per packet", color: COLORS.amber }]} decimals={2} />
        <Chip>results/gap_attack_v2.json</Chip>
      </Section>
      <Insight analogy="A guard who only checks door numbers cannot tell you who walked through. The visitor log that names people was written by someone else." gain="CSV-trained detectors describe numbers the controller never had, so they are not controller-side detectors." />
    </>
  );
}
