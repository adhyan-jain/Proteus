import Link from "next/link";
import { Bars } from "@/components/new-ui/charts";
import { COLORS } from "@/components/new-ui/colors";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/new-ui/card";
import { Flow, J, PageHead, Stat } from "@/components/new-ui/study";

export default function Overview() {
  const fm = J("flowmod_matches.json");
  const one = J("live_modes_v4_one10.json").summary;
  const cv = J("v4_strict_W1.json").A_grouped_cv;
  const rc = J("review_checks.json").within_session_W1_strict.any_ip_packet_in;
  const mp = fm.total_by_match_structure["in_port|eth_dst|eth_src"];
  const NAV: [string, string, string][] = [
    ["/new/gap", "1 · Gap", "What the controller's rules could see"],
    ["/new/forwarding", "2 · Forwarding", "Same traffic, different view"],
    ["/new/validity", "3 · Validity", "Why a high score is not proof"],
    ["/new/pipeline", "Pipeline", "Inputs and outputs, step by step"],
    ["/new/novelty", "Novelty", "The five points, plainly"],
    ["/new/faq", "Q&A", "Questions and honest scope"],
  ];
  return (
    <>
      <PageHead kicker="Measurement and validity study · VIT Vellore" title="What an SDN controller can actually observe" intro="Detectors are scored on features from the victim host, then called controller-based. We opened InSDN's own controller recordings to see what the controller really saw." />
      <section className="grid gap-4 md:grid-cols-3">
        <Stat title="1 · Flows the controller saw" value={`0 of ${fm.flowmods.toLocaleString()}`} note={`FlowMods with IP or port fields. ${mp.toLocaleString()} match MAC pairs only.`} />
        <Stat title="2 · PacketIns per run" value={`${Math.round(one.fivetuple.packet_in_tcp.mean).toLocaleString()} vs ${one.mac.packet_in_tcp.mean.toFixed(1)}`} note="Per-flow vs MAC-pair forwarding, same traffic." />
        <Stat title="3 · Score vs trivial rule" value={`${cv.mlp_all.bacc.mean.toFixed(3)} vs ${rc.bacc_pooled.toFixed(3)}`} note="Model vs a one-line rule. Not proof of detection." />
      </section>
      <Card>
        <CardHeader>
          <CardTitle>The study in one picture</CardTitle>
          <CardDescription>Two pipelines, one paper</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Flow steps={[{ title: "44 controller captures", sub: "InSDN, ONOS" }, { title: "Parse OpenFlow", sub: "PacketIn, FlowMod" }, { title: "Windows", sub: "22 features" }, { title: "Models + tests", sub: "10 seeds, CI" }, { title: "Result files", sub: "→ paper tables" }]} />
          <Flow steps={[{ title: "Ryu app, 3 modes", sub: "MAC-pair / per-flow", tone: "amber" }, { title: "Mininet network", sub: "1 or 3 switches", tone: "amber" }, { title: "Control-channel capture", sub: "pcap", tone: "amber" }, { title: "Counts per mode", sub: "→ paper tables", tone: "amber" }]} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Per-flow forwarding floods the controller</CardTitle>
          <CardDescription>TCP PacketIns per run, log scale, 10 runs per mode</CardDescription>
        </CardHeader>
        <CardContent>
          <Bars log height={240} data={[{ name: "MAC-pair", v: one.mac.packet_in_tcp.mean }, { name: "Per-flow, 2 s idle", v: one.fivetuple_short.packet_in_tcp.mean }, { name: "Per-flow, 10 s idle", v: one.fivetuple.packet_in_tcp.mean }]} series={[{ key: "v", name: "PacketIns", color: COLORS.teal }]} cellColors={[COLORS.teal, COLORS.amber, COLORS.amber]} decimals={0} />
        </CardContent>
      </Card>
      <section className="grid gap-4 md:grid-cols-3">
        {NAV.map(([h, t, d]) => (
          <Link key={h} href={h}>
            <Card className="h-full transition-colors hover:bg-accent">
              <CardHeader>
                <CardTitle>{t}</CardTitle>
                <CardDescription>{d}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </section>
    </>
  );
}
