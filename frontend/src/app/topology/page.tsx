import { api } from "@/lib/api";
import type { Ci } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";

const MODE_LABELS: Record<string, string> = {
  mac: "MAC-pair forwarding",
  fivetuple: "5-tuple, 10 s idle",
  fivetuple_short: "5-tuple, 2 s idle",
};
const fmt = (c: Ci | undefined) => (c ? `${c.mean.toFixed(1)} ± ${c.ci95.toFixed(1)}` : "n/a");

export default async function TopologyPage() {
  const data = await api.controllerTelemetry().catch(() => null);
  const ok = data && data.available ? data : null;
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold text-text-primary">SDN Topology</h1>
        <Badge tone="idle" dot>
          recorded testbed · no live controller
        </Badge>
      </div>

      <Panel>
        <PanelHeader
          title="Mininet / Ryu testbed used in the forwarding study"
          subtitle="Topologies from research/insdn_controller/live/run_benign.py; Open vSwitch with OpenFlow 1.3, controller on port 6653"
        />
        <PanelBody>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <p className="mb-2 text-[12px] text-text-tertiary">One switch: h1-h5 clients, h6 HTTP server</p>
              <svg viewBox="0 0 340 200" className="w-full text-text-secondary">
                <rect x="130" y="6" width="80" height="24" rx="4" fill="none" stroke="currentColor" />
                <text x="170" y="22" textAnchor="middle" fontSize="11" fill="currentColor">Ryu controller</text>
                <line x1="170" y1="30" x2="170" y2="80" stroke="currentColor" strokeDasharray="3 3" />
                <rect x="140" y="80" width="60" height="24" rx="4" fill="none" stroke="currentColor" />
                <text x="170" y="96" textAnchor="middle" fontSize="11" fill="currentColor">s1</text>
                {[1, 2, 3, 4, 5, 6].map((i) => {
                  const x = 25 + (i - 1) * 56;
                  return (
                    <g key={i}>
                      <line x1="170" y1="104" x2={x + 14} y2="150" stroke="currentColor" />
                      <rect x={x} y="150" width="28" height="22" rx="4" fill="none" stroke="currentColor" />
                      <text x={x + 14} y="165" textAnchor="middle" fontSize="10" fill="currentColor">h{i}</text>
                    </g>
                  );
                })}
              </svg>
            </div>
            <div>
              <p className="mb-2 text-[12px] text-text-tertiary">Three-switch chain: two hosts per switch, server h6 on s3</p>
              <svg viewBox="0 0 340 200" className="w-full text-text-secondary">
                <rect x="130" y="6" width="80" height="24" rx="4" fill="none" stroke="currentColor" />
                <text x="170" y="22" textAnchor="middle" fontSize="11" fill="currentColor">Ryu controller</text>
                {[0, 1, 2].map((k) => {
                  const x = 40 + k * 110;
                  return (
                    <g key={k}>
                      <line x1="170" y1="30" x2={x + 30} y2="80" stroke="currentColor" strokeDasharray="3 3" />
                      <rect x={x} y="80" width="60" height="24" rx="4" fill="none" stroke="currentColor" />
                      <text x={x + 30} y="96" textAnchor="middle" fontSize="11" fill="currentColor">s{k + 1}</text>
                      {k < 2 && <line x1={x + 60} y1="92" x2={x + 110} y2="92" stroke="currentColor" />}
                      {[0, 1].map((j) => {
                        const hx = x + j * 36;
                        return (
                          <g key={j}>
                            <line x1={x + 30} y1="104" x2={hx + 14} y2="150" stroke="currentColor" />
                            <rect x={hx} y="150" width="28" height="22" rx="4" fill="none" stroke="currentColor" />
                            <text x={hx + 14} y="165" textAnchor="middle" fontSize="10" fill="currentColor">h{k * 2 + j + 1}</text>
                          </g>
                        );
                      })}
                    </g>
                  );
                })}
              </svg>
            </div>
          </div>
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel>
          <PanelHeader title="Controller" />
          <PanelBody className="text-[12px] text-text-tertiary">
            Ryu, OpenFlow 1.3, learning switch with a configurable entry granularity (MAC-pair, 5-tuple 10 s, 5-tuple 2 s).
            Not connected live; the numbers here are recorded runs.
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Recorded TCP PacketIns per run (1 switch)" />
          <PanelBody className="text-[12px] text-text-secondary">
            {ok ? (
              Object.entries(ok.live_modes).map(([m, v]) => (
                <div key={m} className="flex justify-between border-t border-border-subtle py-1 first:border-t-0">
                  <span>{MODE_LABELS[m] ?? m}</span>
                  <span className="mono text-text-primary">{fmt(v.packet_in_tcp)}</span>
                </div>
              ))
            ) : (
              "Result files not available."
            )}
          </PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Recorded TCP PacketIns per run (3 switches)" />
          <PanelBody className="text-[12px] text-text-secondary">
            {ok ? (
              Object.entries(ok.live_modes_linear3).map(([m, v]) => (
                <div key={m} className="flex justify-between border-t border-border-subtle py-1 first:border-t-0">
                  <span>{MODE_LABELS[m] ?? m}</span>
                  <span className="mono text-text-primary">{fmt(v.packet_in_tcp)}</span>
                </div>
              ))
            ) : (
              "Result files not available."
            )}
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}
