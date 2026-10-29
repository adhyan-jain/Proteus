import { Chip, Flow, PageHead, Section } from "@/components/new-ui/study";

export default function Pipeline() {
  return (
    <>
      <PageHead kicker="Architecture" title="What goes in, what comes out" intro="Two pipelines meet in the paper. Both end as result JSON files; the paper's tables are generated from them." />
      <Section title="A · InSDN controller captures" desc="Recorded, offline">
        <Flow steps={[
          { title: "44 captures", sub: "in: ONOS pcaps (TCP 6653)" },
          { title: "Parser", sub: "out: PacketIn, FlowMod, stats" },
          { title: "Labels", sub: "in: CSV flow IDs · out: tag per PacketIn" },
          { title: "Windows", sub: "out: 22 features / 1–5 s" },
          { title: "History", sub: "out: 88 inputs" },
          { title: "Models", sub: "out: attack / not, per window" },
          { title: "Tests", sub: "out: BAcc ± CI, trivial rule" },
        ]} />
        <div className="flex flex-wrap gap-2"><Chip>ofgap/ofparse.py</Chip><Chip>ofgap/ctrlfeat.py</Chip><Chip>ofgap/exp_ctrl2.py</Chip><Chip>ofgap/review_checks.py</Chip></div>
        <p className="text-sm text-muted-foreground">The CSV only supplies labels. Its flow features are never a model input. All training runs on the GPU.</p>
      </Section>
      <Section title="B · Live forwarding study" desc="Mininet + Ryu, benign traffic, no InSDN data">
        <Flow steps={[
          { title: "Ryu app", sub: "3 modes", tone: "amber" },
          { title: "Mininet", sub: "1 or 3 switches", tone: "amber" },
          { title: "Control-channel pcap", sub: "out: capture per run", tone: "amber" },
          { title: "Analysis", sub: "out: PacketIns, FlowMods, entries per poll", tone: "amber" },
        ]} />
        <div className="flex flex-wrap gap-2"><Chip>live/ryu_fwd.py</Chip><Chip>live/run_benign.py</Chip><Chip>live/live_table.py</Chip></div>
      </Section>
      <Section title="C · Granularity check" desc="Same 44 captures">
        <Flow steps={[{ title: "Every FlowMod", sub: "in: captures" }, { title: "Match fields", sub: "out: which headers a rule looks at" }]} />
        <div className="flex flex-wrap gap-2"><Chip>ofgap/flowmod_check.py</Chip><Chip>ofgap/gap_measure.py</Chip></div>
      </Section>
    </>
  );
}
