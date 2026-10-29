import { DT, Mono, PageHead, Section, Why } from "@/components/new-ui/study";

export default function Reproduce() {
  return (
    <>
      <PageHead kicker="Reproducibility" title="Every number can be rebuilt and checked" intro="One script regenerates the features and every result file from the hashed raw captures and compares them with the stored files; a second script checks the numbers quoted in the paper." />
      <Section title="Commands">
        <pre className="overflow-x-auto rounded-md bg-muted p-4 text-xs">{`research/insdn_controller/reproduce.sh                       # GPU, about 40 minutes
python research/insdn_controller/paper/verify_numbers.py     # paper numbers vs results/*.json

# re-recording the live captures needs root (see the README next to reproduce.sh)
sudo python3 live/run_benign.py --out live/out_stock --modes stock --repeats 5 --duration 60`}</pre>
        <Why>Features come out bit-identical from the raw captures; result files agree within a tolerance of 1e-6 (GPU float order). Packet timing differs when live captures are re-recorded, so those hashes pin the numbers in the paper.</Why>
      </Section>
      <Section title="Where things are">
        <DT head={["What", "Where"]} rows={[
          ["Paper (PDF and LaTeX)", <Mono key="a">research/insdn_controller/paper/main.pdf</Mono>],
          ["Every number's source", <Mono key="b">research/insdn_controller/results/*.json</Mono>],
          ["Capture hashes (SHA-256)", <Mono key="c">research/insdn_controller/capture_hashes.sha256</Mono>],
          ["Dataset sources and hashes", <Mono key="d">data/MANIFEST.md</Mono>],
          ["Raw captures (not in git)", <Mono key="e">data/raw/insdn_pcaps/, research/insdn_controller/live/</Mono>],
          ["Presentation guide and deck", <Mono key="f">research/insdn_controller/PRESENTATION_GUIDE.md, PRESENTATION.pptx</Mono>],
        ]} />
      </Section>
    </>
  );
}
