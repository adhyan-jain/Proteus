import fs from "node:fs";
import path from "node:path";
import { Bars } from "@/components/new-ui/charts";
import { COLORS } from "@/components/new-ui/colors";
import { DT, Insight, J, PageHead, Section } from "@/components/new-ui/study";

export default function Literature() {
  const lit = JSON.parse(fs.readFileSync(path.resolve(process.cwd(), "..", "research", "insdn_controller", "literature_check.json"), "utf8"));
  const hs = J("hostside_xgb.json");
  const cv = J("v4_strict_W1.json").A_grouped_cv;
  return (
    <>
      <PageHead kicker="Published results" title="How InSDN papers report, and what our result says about it" intro="An abstract-level check of five InSDN papers. We read what the authors state; we did not read full texts or re-run their detectors." />
      <Section title="What they report" desc="Authors' own numbers, not verified by us" tell="Published InSDN results sit at 96 to 99.98% accuracy, all on the dataset's CSV features.">
        <DT head={["Paper", "Reported"]} rows={lit.papers.map((p: { paper: string; reported: string; url: string }) => [<a key={p.url} href={p.url} className="underline">{p.paper}</a>, p.reported])} />
        <p className="text-muted-foreground">All five use the InSDN CSV features. Their train/test split procedure is not visible in the search snippets, so we cannot say whether sessions leak across it.</p>
      </Section>
      <Section title="Our numbers on the same data" desc="Same InSDN CSV, two protocols" tell="The usual row-split protocol gets 0.9998, as high as the best published scores; the controller view gets 0.946.">
        <Bars height={260} data={[{ name: "Host-side CSV, random row split (ours)", v: hs.bacc_mean }, { name: "Controller view, unseen captures (ours)", v: cv.mlp_all.bacc.mean }]} series={[{ key: "v", name: "Balanced accuracy", color: COLORS.teal }]} cellColors={[COLORS.amber, COLORS.teal]} decimals={4} />
      </Section>
      <Section title="What this does and does not say">
        <p><b>It supports:</b> those scores are what the easy protocol produces on this CSV (our own host-side run gives {hs.bacc_mean.toFixed(4)}), and any claim that such a detector runs at the controller is undercut by our gap result (the controller never had those flow features).</p>
        <p><b>It does not show:</b> that any of these papers is wrong. Their split procedure, feature set and deployment claim must be read in the full text. We can only say the benchmark cannot support a controller-side claim.</p>
      </Section>
      <Insight analogy="Several students score near-perfect on a quiz drawn from the worksheet they practised on." gain="Treat InSDN CSV accuracies as flow-feature results, not as evidence of controller-side detection." />
    </>
  );
}
