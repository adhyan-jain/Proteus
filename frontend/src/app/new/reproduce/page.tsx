import { Chip, PageHead, Section } from "@/components/new-ui/study";

export default function Reproduce() {
  return (
    <>
      <PageHead kicker="Reproducibility" title="Every number can be rebuilt" intro="Features come out bit-identical; result files agree within 1e-6." />
      <Section title="Commands">
        <pre className="overflow-x-auto rounded-md bg-muted p-4 text-xs">{`research/insdn_controller/reproduce.sh                      # GPU, ~40 min
python research/insdn_controller/paper/verify_numbers.py    # paper vs results/*.json`}</pre>
        <div className="flex flex-wrap gap-2"><Chip>results/*.json</Chip><Chip>capture_hashes.sha256</Chip><Chip>data/MANIFEST.md</Chip><Chip>paper/main.pdf</Chip></div>
      </Section>
    </>
  );
}
