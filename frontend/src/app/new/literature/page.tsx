import fs from "node:fs";
import path from "node:path";
import { Bars } from "@/components/new-ui/charts";
import { COLORS } from "@/components/new-ui/colors";
import { Insight, J, PageHead, Section } from "@/components/new-ui/study";

export default function Literature() {
  const lit = JSON.parse(fs.readFileSync(path.resolve(process.cwd(), "..", "research", "insdn_controller", "literature_check.json"), "utf8"));
  const hs = J("hostside_xgb.json");
  const cv = J("v4_strict_W1.json").A_grouped_cv;
  const pi = J("protocol_inflation.json");
  return (
    <>
      <PageHead kicker="Published results" title="How InSDN papers report, and what our result says about it" intro="Four published InSDN papers. We quote what the authors report, and say exactly what we could verify. We did not re-run anyone's detector." />
      <Section title="What they report" desc="Authors' own numbers, not re-run by us" tell="Published InSDN accuracies sit at 96 to 99.7%. We could read the full text of only one paper.">
        <div className="flex flex-col gap-3">
          {lit.papers.map((p: { paper: string; reported: string; verified: string; read: boolean; url: string }) => (
            <div key={p.url} className="rounded-lg border border-border p-3">
              <a href={p.url} className="font-medium underline">{p.paper}</a>
              <p className="mt-1"><span className="text-muted-foreground">Reported: </span>{p.reported}</p>
              <p className="mt-1"><span className="rounded bg-secondary px-1.5 py-0.5 text-xs font-semibold">{p.read ? "FULL TEXT READ" : "NOT VERIFIED"}</span> {p.verified}</p>
            </div>
          ))}
        </div>
        <p className="text-muted-foreground">{lit.note}</p>
      </Section>
      <Section title="Our numbers on the same data" desc="Same InSDN CSV, two protocols" tell="The usual row-split protocol gets 0.9998 here, about as high as published accuracies; the controller view gets 0.946.">
        <Bars height={260} data={[{ name: "Host-side CSV, random row split (ours)", v: hs.bacc_mean }, { name: "Controller view, unseen captures (ours)", v: cv.mlp_all.bacc.mean }]} series={[{ key: "v", name: "Balanced accuracy", color: COLORS.teal }]} cellColors={[COLORS.amber, COLORS.teal]} decimals={4} />
      </Section>
      <Section title="We tested the protocol: does a random flow split overstate the score?" desc={`Same GPU XGBoost classifier on InSDN (${pi.rows.toLocaleString()} flows, ${pi.features} features), benign vs attack, 10 seeds`} tell={`Holding out source hosts drops the score from ${pi.A_random_flow_split.mean.toFixed(4)} to ${pi.B_source_ip_grouped_split.mean.toFixed(3)} ± ${pi.B_source_ip_grouped_split.ci95.toFixed(3)}, so the random split overstates generalization to unseen hosts by about ${((pi.A_random_flow_split.mean - pi.B_source_ip_grouped_split.mean) * 100).toFixed(0)} points.`}>
        <Bars height={300} data={[{ name: "Random flow split (Towhid protocol)", v: pi.A_random_flow_split.mean }, { name: "Held-out source hosts", v: pi.B_source_ip_grouped_split.mean }, { name: "Time-ordered per file", v: pi.C_time_ordered_split.mean }, { name: "IPs and ports only", v: pi.D_identifier_only_random_split.mean }]} series={[{ key: "v", name: "Balanced accuracy", color: COLORS.teal }]} cellColors={[COLORS.amber, COLORS.red, COLORS.teal, COLORS.purple]} decimals={4} />
        <p className="text-muted-foreground">Benign flows exist only in one CSV file and every attack flow in the other two, so the label is fully confounded with the recording; IP addresses and ports alone separate the classes perfectly ({pi.D_identifier_only_random_split.mean.toFixed(4)}). A time-ordered split per file shows no drop, so the leakage is through hosts, not adjacent flows. This tests the protocol on the CSV features; Towhid et al. used 9 packet-derived features, so their exact 98.84% is not re-run.</p>
      </Section>
      <Section title="What this does and does not say">
        <p><b>It supports:</b> near-perfect scores are what the easy protocol produces on InSDN (our host-side run gives {hs.bacc_mean.toFixed(4)}). In the one paper we read, all flows were split 70:30 with no grouping by capture or session mentioned, the setup in which separate benign and attack sessions can leak across the split. Any claim that such a detector runs at the controller is undercut by our gap result.</p>
        <p><b>It does not show:</b> that any of these papers is wrong. For three of four we could not read the split or features, and for the fourth the paper simply does not discuss session separation. We can only say the benchmark cannot support a controller-side claim.</p>
      </Section>
      <Insight analogy="Several students score near-perfect on a quiz drawn from the worksheet they practised on." gain="Treat InSDN CSV accuracies as flow-feature results, not as evidence of controller-side detection." />
    </>
  );
}
