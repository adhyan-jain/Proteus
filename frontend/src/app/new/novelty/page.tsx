import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/new-ui/card";
import { Chip, J, PageHead } from "@/components/new-ui/study";

export default function Novelty() {
  const fm = J("flowmod_matches.json");
  const one = J("live_modes_v4_one10.json").summary;
  const cv = J("v4_strict_W1.json").A_grouped_cv;
  const rc = J("review_checks.json").within_session_W1_strict.any_ip_packet_in;
  const v2 = J("live_modes_v2.json").summary;
  const pts: { n: string; t: string; num: string; analogy: string; gain: string; href?: string; files: string }[] = [
    { n: "1", t: "The controller never saw the labelled flows", num: `0 of ${fm.flowmods.toLocaleString()} FlowMods`, analogy: "A guard who checks door numbers cannot name who walked through.", gain: "CSV-trained detectors are not controller-side detectors.", href: "/new/gap", files: "flowmod_check.py · gap_measure.py" },
    { n: "2", t: "The forwarding app decides the view", num: `${Math.round(one.fivetuple.packet_in_tcp.mean).toLocaleString()} vs ${one.mac.packet_in_tcp.mean.toFixed(1)} PacketIns`, analogy: "A receptionist asking ID at every door vs one who checks the building.", gain: "Define a detector's inputs together with the forwarding setup.", href: "/new/forwarding", files: "ryu_fwd.py · live_table.py" },
    { n: "3", t: "A high score is not proof of detection", num: `${cv.mlp_all.bacc.mean.toFixed(3)} vs ${rc.bacc_pooled.toFixed(3)} (trivial rule)`, analogy: "Sick patients photographed in one room, healthy in another: recognising the room scores full marks.", gain: "Evaluate with benign and attack traffic mixed in one session.", href: "/new/validity", files: "exp_ctrl2.py · review_checks.py" },
    { n: "4", t: "A pitfall we caught in ourselves", num: `${(v2.fivetuple.packet_in_tcp.mean / v2.mac.packet_in_tcp.mean).toFixed(0)}× instead of ~${(one.fivetuple.packet_in_tcp.mean / one.mac.packet_in_tcp.mean).toFixed(0)}×`, analogy: "A coarse rule at the front door hid the rest of the traffic.", gain: "Overlapping coarse rules can understate controller load by two orders of magnitude.", files: "ryu_fwd_v1.py · live_modes_v2.json" },
    { n: "5", t: "Everything can be rebuilt and checked", num: "1 command", analogy: "Every figure comes with its receipt.", gain: "Anyone can regenerate and verify the numbers (support, not the headline).", files: "reproduce.sh · verify_numbers.py" },
  ];
  return (
    <>
      <PageHead kicker="Novelty points" title="Five contributions" intro="We say 'as far as our searches show', never 'first'. Combining known tools in a new way still counts: we claim the measurement and the combination, not a new algorithm." />
      {pts.map((p) => (
        <Card key={p.n}>
          <CardHeader>
            <CardDescription>Novelty {p.n}</CardDescription>
            <CardTitle className="text-lg">{p.t}</CardTitle>
            <p className="text-2xl font-semibold tabular-nums">{p.num}</p>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm md:grid-cols-2">
            <div className="rounded-lg border border-border p-3"><b>Analogy.</b> {p.analogy}</div>
            <div className="rounded-lg border border-border bg-secondary/40 p-3"><b>What we get.</b> {p.gain}</div>
            <div className="flex items-center gap-3 md:col-span-2"><Chip>{p.files}</Chip>{p.href && <Link href={p.href} className="text-muted-foreground underline">Charts →</Link>}</div>
          </CardContent>
        </Card>
      ))}
    </>
  );
}
