import { PageHead, Section } from "@/components/new-ui/study";

const QA: [string, string][] = [
  ["Does it detect attacks?", "Not proven. A trivial rule matches the score inside attack sessions."],
  ["Why not the 99% from CSV papers?", "They use features a controller never receives. That gap is the paper."],
  ["Logistic regression ties your network. Contribution?", "None from the model. The contribution is the measurement and the validity analysis."],
  ["Isn't this obvious for ONOS?", "The direction is; the size was never measured and the benchmark is still used as controller-based."],
  ["Why no oversampling of rare classes?", "6–12 attack windows would just be copied, and it risks leakage. Future work, in-fold only."],
  ["Is there a deployed SDN?", "No. Recorded captures plus a Mininet/Ryu testbed we start on demand. Detection is offline."],
];

export default function Faq() {
  return (
    <>
      <PageHead kicker="Q&A and scope" title="Questions you will get" intro="If you do not know, say: I measured X but not Y; Y is future work." />
      <Section title="Short answers">
        {QA.map(([q, a]) => (
          <div key={q}>
            <p className="font-semibold">{q}</p>
            <p className="text-muted-foreground">{a}</p>
          </div>
        ))}
      </Section>
      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Not new">
          <ul className="list-disc pl-5 text-muted-foreground">
            <li>Control-plane telemetry for SDN IDS (LAN-SDN-NIDS, SDNFLow)</li>
            <li>The detector itself</li>
            <li>Stock Ryu behaviour</li>
            <li>Session leakage as a pitfall</li>
          </ul>
        </Section>
        <Section title="Not done">
          <ul className="list-disc pl-5 text-muted-foreground">
            <li>Benign + attack traffic in one session</li>
            <li>OpenDaylight or another dataset</li>
            <li>A re-implemented published detector</li>
          </ul>
        </Section>
      </div>
      <Section title="Venue and the older system">
        <p className="text-muted-foreground">Workshop or conference as it stands; lower-quartile journal after revision. The earlier Proteus GAN and drift console (under /old) is a separate prototype with close prior work and no measured benefit, so it is not part of the claims.</p>
      </Section>
    </>
  );
}
