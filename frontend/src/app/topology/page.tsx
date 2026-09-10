import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";

export default async function TopologyPage() {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold text-text-primary">SDN Topology</h1>
        <Badge tone="idle" dot>
          no live controller connected
        </Badge>
      </div>

      <Panel>
        <PanelHeader
          title="Ryu Controller / Mininet Topology"
          subtitle="Interactive topology graph — switches, hosts, links, live flow overlays, click-through inspection"
        />
        <PanelBody>
          <div className="flex min-h-[420px] flex-col items-center justify-center gap-4 rounded border border-dashed border-border-default bg-[radial-gradient(circle_at_center,_var(--surface-2)_0%,_var(--surface-0)_75%)] px-6 py-16 text-center">
            <TopologyGlyph />
            <div className="flex flex-col gap-1.5">
              <span className="mono text-[11px] font-semibold uppercase tracking-[0.14em] text-text-disabled">
                NO LIVE CONTROLLER CONNECTED
              </span>
              <p className="max-w-lg text-[12px] leading-relaxed text-text-tertiary">
                The Mininet/Ryu SDN deployment is a separate, in-progress workstream and isn&apos;t wired into
                this build yet. Once a controller is reachable, this screen renders switches, hosts, and links
                as an interactive graph (React Flow), with live traffic volume on edges and suspicious flows
                highlighted in red — click any node or edge to inspect flow tables, port stats, or per-flow
                classification.
              </p>
            </div>
          </div>
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel>
          <PanelHeader title="Controller" />
          <PanelBody className="text-[12px] text-text-tertiary">Ryu — not connected.</PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Switches" />
          <PanelBody className="text-[12px] text-text-tertiary">No OpenFlow switches reporting.</PanelBody>
        </Panel>
        <Panel>
          <PanelHeader title="Active Flows" />
          <PanelBody className="text-[12px] text-text-tertiary">No flow table data available.</PanelBody>
        </Panel>
      </div>
    </div>
  );
}

function TopologyGlyph() {
  return (
    <svg width="120" height="72" viewBox="0 0 120 72" className="text-text-disabled">
      <circle cx="60" cy="12" r="6" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="20" cy="56" r="6" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="60" cy="56" r="6" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="100" cy="56" r="6" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <line x1="60" y1="18" x2="20" y2="50" stroke="currentColor" strokeWidth="1" strokeDasharray="2 3" />
      <line x1="60" y1="18" x2="60" y2="50" stroke="currentColor" strokeWidth="1" strokeDasharray="2 3" />
      <line x1="60" y1="18" x2="100" y2="50" stroke="currentColor" strokeWidth="1" strokeDasharray="2 3" />
    </svg>
  );
}
