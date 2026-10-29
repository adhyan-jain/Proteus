import fs from "node:fs";
import path from "node:path";
import Link from "next/link";
import { Badge } from "@/components/new-ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/new-ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/new-ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/new-ui/tabs";

const R = path.resolve(process.cwd(), "..", "research", "insdn_controller", "results");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const J = (f: string): any => JSON.parse(fs.readFileSync(path.join(R, f), "utf8").replace(/\bNaN\b/g, "null"));
const ci = (c?: { mean: number; ci95: number }, d = 1) => (c ? `${c.mean.toFixed(d)} ± ${c.ci95.toFixed(d)}` : "n/a");
const MODE: Record<string, string> = { mac: "MAC-pair forwarding", fivetuple: "Per-flow, 10 s idle", fivetuple_short: "Per-flow, 2 s idle" };

function Why({ children }: { children: React.ReactNode }) {
  return (
    <p className="border-l-2 border-border pl-3 text-sm text-muted-foreground">
      <span className="font-semibold text-foreground">What this shows: </span>
      {children}
    </p>
  );
}

function Stat({ title, value, note }: { title: string; value: string; note: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl font-semibold tabular-nums">{value}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">{note}</CardContent>
    </Card>
  );
}

function ModeTable({ summary }: { summary: Record<string, Record<string, { mean: number; ci95: number }>> }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Forwarding mode</TableHead>
          <TableHead>TCP PacketIns / run</TableHead>
          <TableHead>FlowMods / run</TableHead>
          <TableHead>Per-flow entries per 1 s poll</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {["mac", "fivetuple", "fivetuple_short"].map((m) => (
          <TableRow key={m}>
            <TableCell>{MODE[m]}</TableCell>
            <TableCell className="tabular-nums">{ci(summary[m].packet_in_tcp)}</TableCell>
            <TableCell className="tabular-nums">{ci(summary[m].flow_mods)}</TableCell>
            <TableCell className="tabular-nums">{ci(summary[m].fivetuple_entries_per_reply)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

const STEPS: [string, string, string][] = [
  ["1 Parse", "44 InSDN controller pcaps", "OpenFlow messages (PacketIn, FlowMod, stats)"],
  ["2 Label", "PacketIn packet + InSDN CSV flow IDs", "attack / benign tag per PacketIn"],
  ["3 Window + features", "message stream, 1 s or 5 s windows", "22 numbers per window"],
  ["4 History", "window rows", "88 inputs (current + 3 previous windows)"],
  ["5 Models", "88 inputs + window label", "attack / not attack per window (MLP, logistic, XGBoost, thresholds)"],
  ["6 Tests", "predictions", "10-seed mean ± 95% CI, trivial-rule check, session probes"],
  ["7 Live study", "Ryu app + Mininet, benign traffic", "control-channel pcaps, PacketIn / FlowMod counts per mode"],
];

export default function NewHome() {
  const fm = J("flowmod_matches.json");
  const one = J("live_modes_v4_one10.json").summary;
  const l3 = J("live_modes_v4_linear3.json").summary;
  const cv = J("v4_strict_W5_xgb.json").A_grouped_cv;
  const rc = J("review_checks.json").within_session_W5_strict.any_ip_packet_in;
  const st = J("stock_ryu_flowmods.json");
  const hs = J("hostside_xgb.json");
  const macPair = fm.total_by_match_structure["in_port|eth_dst|eth_src"];
  const MODELS: [string, string][] = [
    ["mlp_all", "MLP (controller features + history)"],
    ["linear_all_history", "Logistic regression"],
    ["xgb_all_history", "XGBoost (GPU)"],
    ["thr_packet_in_rate", "Single threshold: PacketIn rate"],
  ];

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <Badge variant="secondary">Measurement and validity study</Badge>
          <Link href="/old" className="text-sm text-muted-foreground underline">
            Old console (Proteus demo)
          </Link>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">What an SDN controller can actually observe</h1>
        <p className="text-sm text-muted-foreground">
          InSDN&apos;s own OpenFlow controller captures, a Mininet/Ryu testbed, and what it means for evaluating controller-side
          intrusion detection. Every number below is read from the result files of the study.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <Stat title="1 · Flows the controller saw" value={`0 of ${fm.flowmods.toLocaleString()}`} note={`FlowMods carry IP or port fields; ${macPair.toLocaleString()} match MAC pairs only.`} />
        <Stat title="2 · PacketIns per run" value={`${Math.round(one.fivetuple.packet_in_tcp.mean).toLocaleString()} vs ${one.mac.packet_in_tcp.mean.toFixed(1)}`} note="Per-flow vs MAC-pair forwarding on the same traffic (10 runs each)." />
        <Stat title="3 · Score vs trivial rule (5 s windows)" value={`${cv.mlp_all.bacc.mean.toFixed(3)} vs ${rc.bacc_pooled.toFixed(3)}`} note="Model balanced accuracy, vs a one-line rule inside attack sessions. The score is not proof of detection." />
      </section>

      <Tabs defaultValue="gap">
        <TabsList className="flex-wrap">
          <TabsTrigger value="gap">1 · Gap</TabsTrigger>
          <TabsTrigger value="fwd">2 · Forwarding</TabsTrigger>
          <TabsTrigger value="valid">3 · Validity</TabsTrigger>
          <TabsTrigger value="pipe">Pipeline</TabsTrigger>
          <TabsTrigger value="repro">Reproduce</TabsTrigger>
        </TabsList>

        <TabsContent value="gap" className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>What fields the controller&apos;s rules look at</CardTitle>
              <CardDescription>InSDN ONOS captures ({fm.flowmods.toLocaleString()} FlowMods) and Ryu&apos;s stock app ({st.flowmods} FlowMods)</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Why>The dataset labels connections by 5-tuple, but no rule the controller installed ever looked at IP addresses or ports, so those flows were never visible to it. Ryu&apos;s own example app behaves the same way.</Why>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead>Rule matches on</TableHead>
                    <TableHead>FlowMods</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(fm.total_by_match_structure).map(([k, v]) => (
                    <TableRow key={`o${k}`}>
                      <TableCell>InSDN (ONOS)</TableCell>
                      <TableCell className="font-mono text-xs">{k}</TableCell>
                      <TableCell className="tabular-nums">{String(v)}</TableCell>
                    </TableRow>
                  ))}
                  {Object.entries(st.total_by_match_structure).map(([k, v]) => (
                    <TableRow key={`s${k}`}>
                      <TableCell>Ryu stock app</TableCell>
                      <TableCell className="font-mono text-xs">{k}</TableCell>
                      <TableCell className="tabular-nums">{String(v)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="fwd" className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Same traffic, three forwarding settings</CardTitle>
              <CardDescription>Mininet + Ryu, benign traffic, 10 runs per mode, mean ± 95% CI</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Why>The forwarding app decides what the controller sees: per-flow rules make every connection visit the controller, MAC-pair rules almost none. A shorter idle timeout also hides entries from a 1 s poller.</Why>
              <h3 className="text-sm font-semibold">One switch</h3>
              <ModeTable summary={one} />
              <h3 className="text-sm font-semibold">Three-switch chain</h3>
              <ModeTable summary={l3} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="valid" className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Detection from the controller&apos;s view, and why the score is not proof</CardTitle>
              <CardDescription>Capture-grouped CV, 5 s windows, strict labels, 10 seeds</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Why>Models using only controller messages score high, but a one-line rule (&quot;at least one IP PacketIn&quot;) scores {rc.bacc_pooled.toFixed(3)} inside attack sessions, so InSDN&apos;s separate benign and attack sessions make the score unreliable as detection accuracy.</Why>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Model</TableHead>
                    <TableHead>Balanced accuracy</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {MODELS.map(([k, label]) => (
                    <TableRow key={k}>
                      <TableCell>{label}</TableCell>
                      <TableCell className="tabular-nums">{ci(cv[k].bacc, 3)}</TableCell>
                    </TableRow>
                  ))}
                  <TableRow>
                    <TableCell>Trivial rule: any IP PacketIn (inside attack sessions)</TableCell>
                    <TableCell className="tabular-nums">{rc.bacc_pooled.toFixed(3)}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Host-side flow-CSV baseline (contrast only)</TableCell>
                    <TableCell className="tabular-nums">{`${hs.bacc_mean.toFixed(4)} ± ${hs.bacc_ci95.toFixed(5)}`}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pipe" className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Study pipeline: what goes in, what comes out</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Why>The path from the raw controller recordings to the paper&apos;s tables. The CSV only supplies labels; it is never a model input.</Why>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Step</TableHead>
                    <TableHead>Input</TableHead>
                    <TableHead>Output</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {STEPS.map(([s, i, o]) => (
                    <TableRow key={s}>
                      <TableCell className="font-medium">{s}</TableCell>
                      <TableCell>{i}</TableCell>
                      <TableCell>{o}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="repro" className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Reproduce everything</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Why>One command rebuilds the features and every result from the hashed raw captures and compares them with the stored files.</Why>
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">{`research/insdn_controller/reproduce.sh
python research/insdn_controller/paper/verify_numbers.py`}</pre>
              <p className="text-sm text-muted-foreground">Result files live in research/insdn_controller/results/, capture hashes in capture_hashes.sha256.</p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </main>
  );
}
