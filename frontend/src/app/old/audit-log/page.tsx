import { api } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { EventStream } from "@/components/overview/event-stream";
import { EmptyState } from "@/components/ui/empty-state";

export default async function AuditLogPage() {
  const [drift, gate, adapt] = await Promise.all([api.driftEvents(), api.gateLog(), api.adaptationEvents()]);

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-[15px] font-semibold text-text-primary">Audit Log</h1>
      <Panel>
        <PanelHeader
          title="Full Event History"
          why="The complete, newest-first record of what the loop did, so any change in model behaviour can be traced back to an event."
        />
        <PanelBody>
          {drift.available || gate.available || adapt.available ? (
            <EventStream drift={drift} gate={gate} adapt={adapt} />
          ) : (
            <EmptyState reason="No experiment run available to audit." />
          )}
        </PanelBody>
      </Panel>
    </div>
  );
}
