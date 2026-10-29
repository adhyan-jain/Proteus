import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/new-ui/card";
import { J, PageHead, Stat, Why } from "@/components/new-ui/study";

const PAGES: [string, string, string][] = [
  ["/new/novelty", "Novelty points", "The five contributions in plain words, with analogy, evidence, source files and the sentence to say."],
  ["/new/gap", "1 · The gap", "What fields the controller's rules actually matched, and PacketIns per target packet in each attack scenario."],
  ["/new/forwarding", "2 · Forwarding", "Same traffic under three forwarding settings: PacketIns, FlowMods and what a poller sees."],
  ["/new/validity", "3 · Validity", "Detector scores, withheld families, cross-deployment, and why a trivial rule undermines the score."],
  ["/new/pipeline", "Pipeline", "Input, process and output of every step, with the file that does it."],
  ["/new/faq", "Q&A and scope", "Likely questions, what is not new, and what we did not do."],
  ["/new/reproduce", "Reproduce", "Commands, result files, hashes and where raw data lives."],
];

export default function Overview() {
  const fm = J("flowmod_matches.json");
  const one = J("live_modes_v4_one10.json").summary;
  const cv = J("v4_strict_W5_xgb.json").A_grouped_cv;
  const rc = J("review_checks.json").within_session_W5_strict.any_ip_packet_in;
  const mp = fm.total_by_match_structure["in_port|eth_dst|eth_src"];
  return (
    <>
      <PageHead
        kicker="Measurement and validity study · VIT Vellore"
        title="What an SDN controller can actually observe"
        intro="SDN intrusion-detection papers say the controller has a global view, yet they score detectors on CSV features computed at the victim host. InSDN's authors also recorded their ONOS controller's OpenFlow traffic. We parsed all 44 recordings and asked three questions: what can the controller see, does that depend on the forwarding app, and does a high score on the controller's view mean detection? Every number on these pages is read from the study's result files."
      />
      <section className="grid gap-4 md:grid-cols-3">
        <Stat title="1 · Flows the controller saw" value={`0 of ${fm.flowmods.toLocaleString()}`} note={`FlowMods carry IP or port fields. ${mp.toLocaleString()} match MAC pairs only, so the 5-tuple flows the dataset labels were never visible to the controller.`} />
        <Stat title="2 · PacketIns per run" value={`${Math.round(one.fivetuple.packet_in_tcp.mean).toLocaleString()} vs ${one.mac.packet_in_tcp.mean.toFixed(1)}`} note="Per-flow versus MAC-pair forwarding on identical traffic, 10 runs each: what the controller sees depends on the forwarding app." />
        <Stat title="3 · Score vs trivial rule (5 s)" value={`${cv.mlp_all.bacc.mean.toFixed(3)} vs ${rc.bacc_pooled.toFixed(3)}`} note="Model balanced accuracy versus a one-line rule inside attack sessions. The score is not proof of detection." />
      </section>
      <Why>The three numbers above are the three novelty points. Everything else in the paper supports one of them. We claim a measurement and a validity warning, not a new detector.</Why>
      <section className="grid gap-4 md:grid-cols-2">
        {PAGES.map(([h, t, d]) => (
          <Link key={h} href={h}>
            <Card className="h-full transition-colors hover:bg-accent">
              <CardHeader>
                <CardTitle>{t}</CardTitle>
                <CardDescription>{d}</CardDescription>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">Open →</CardContent>
            </Card>
          </Link>
        ))}
      </section>
    </>
  );
}
