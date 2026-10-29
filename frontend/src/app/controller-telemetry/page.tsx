import { api } from "@/lib/api";
import type { Ci } from "@/lib/api";
import { Panel, PanelHeader, PanelBody } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";

const MODEL_LABELS: Record<string, string> = {
  mlp_all: "MLP (all controller features + history)",
  linear_all_history: "Logistic regression",
  xgb_all_history: "XGBoost (GPU)",
  thr_packet_in_rate: "Single threshold: PacketIn rate",
};

const MODE_LABELS: Record<string, string> = {
  mac: "MAC-pair forwarding",
  fivetuple: "5-tuple, 10 s idle",
  fivetuple_short: "5-tuple, 2 s idle",
};

const fmt = (c: Ci | undefined, d = 3) => (c ? `${c.mean.toFixed(d)} ± ${c.ci95.toFixed(d)}` : "n/a");

export default async function ControllerTelemetryPage() {
  const data = await api.controllerTelemetry().catch(() => null);
  if (!data || !data.available) {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="text-[15px] font-semibold text-text-primary">Controller Telemetry</h1>
        <Panel>
          <PanelBody className="text-[12px] text-text-tertiary">
            {data && "reason" in data ? data.reason : "API unreachable (start api/server.py)."}
          </PanelBody>
        </Panel>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h1 className="text-[15px] font-semibold text-text-primary">Controller Telemetry (InSDN / ONOS)</h1>
        <Badge tone="network" dot>
          {data.window_s} s windows · {data.label_scheme} labels
        </Badge>
      </div>

      <Panel>
        <PanelHeader
          title="Detection from controller-observable features"
          subtitle="Capture-grouped CV, 10 seeds, mean ± 95% CI. Feasibility only: the trivial rule is the bar to beat."
        />
        <PanelBody>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-text-tertiary">
                <th className="py-1">Model</th>
                <th>Balanced acc.</th>
                <th>Recall</th>
                <th>FPR</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.grouped_cv).map(([k, v]) => (
                <tr key={k} className="border-t border-border-subtle text-text-primary">
                  <td className="py-1">{MODEL_LABELS[k] ?? k}</td>
                  <td className="mono">{fmt(v.bacc)}</td>
                  <td className="mono">{fmt(v.recall)}</td>
                  <td className="mono">{fmt(v.fpr)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[12px] text-text-secondary">
            Validity check (within attack sessions, strict labels, 5 s): the trivial rule &quot;at least one IP PacketIn
            in the window&quot; scores balanced accuracy {data.within_session_trivial_any_ip_packet_in.bacc_pooled.toFixed(3)} on{" "}
            {data.within_session_trivial_any_ip_packet_in.positives} attack / {data.within_session_trivial_any_ip_packet_in.negatives}{" "}
            attack-free windows, so the grouped-CV numbers above are not evidence of attack detection.
          </p>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader
          title="Forwarding mode vs what the controller sees (1 switch)"
          subtitle="Ryu + Mininet, benign traffic only, 10 runs per mode (mean ± 95% CI)"
        />
        <PanelBody>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-text-tertiary">
                <th className="py-1">Mode</th>
                <th>TCP PacketIns / run</th>
                <th>FlowMods / run</th>
                <th>5-tuple entries per 1 s poll reply</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.live_modes).map(([m, v]) => (
                <tr key={m} className="border-t border-border-subtle text-text-primary">
                  <td className="py-1">{MODE_LABELS[m] ?? m}</td>
                  <td className="mono">{fmt(v.packet_in_tcp, 1)}</td>
                  <td className="mono">{fmt(v.flow_mods, 1)}</td>
                  <td className="mono">{fmt(v.fivetuple_entries_per_reply, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader
          title="Same study on a 3-switch chain"
          subtitle="Ryu + Mininet, benign traffic only, 10 runs per mode (mean ± 95% CI)"
        />
        <PanelBody>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-left text-text-tertiary">
                <th className="py-1">Mode</th>
                <th>TCP PacketIns / run</th>
                <th>FlowMods / run</th>
                <th>5-tuple entries per 1 s poll reply</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.live_modes_linear3).map(([m, v]) => (
                <tr key={m} className="border-t border-border-subtle text-text-primary">
                  <td className="py-1">{MODE_LABELS[m] ?? m}</td>
                  <td className="mono">{fmt(v.packet_in_tcp, 1)}</td>
                  <td className="mono">{fmt(v.flow_mods, 1)}</td>
                  <td className="mono">{fmt(v.fivetuple_entries_per_reply, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PanelBody>
      </Panel>

      {data.stock_ryu && (
        <Panel>
          <PanelHeader
            title="Second controller application: Ryu stock simple_switch_13"
            subtitle={`Unmodified application, ${data.stock_ryu.runs} runs, benign traffic. FlowMod match structures.`}
          />
          <PanelBody>
            <table className="w-full text-[12px]">
              <tbody>
                {Object.entries(data.stock_ryu.by_match).map(([k, v]) => (
                  <tr key={k} className="border-t border-border-subtle text-text-primary">
                    <td className="py-1 mono">{k}</td>
                    <td className="mono">{v} FlowMods</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-[12px] text-text-secondary">
              {data.stock_ryu.flowmods} FlowMods in total;{" "}
              {data.stock_ryu.ip_or_transport_fields ? "some" : "none"} carry IP or transport match fields. PacketIns per run:{" "}
              {data.stock_ryu.packet_in_per_run.join(", ")}.
            </p>
          </PanelBody>
        </Panel>
      )}

      {data.host_side && (
        <Panel>
          <PanelHeader
            title="Host-side flow-CSV baseline (contrast only)"
            subtitle={`${data.host_side.rows.toLocaleString()} flows, ${data.host_side.features} features, ${data.host_side.seeds} seeds`}
          />
          <PanelBody className="text-[12px] text-text-secondary">
            Balanced accuracy <span className="mono text-text-primary">{data.host_side.bacc_mean.toFixed(4)} ± {data.host_side.bacc_ci95.toFixed(5)}</span>.{" "}
            {data.host_side.protocol}. Rows of one session fall on both sides of the split and a controller never receives these
            features, so this is not comparable with the controller-view numbers above.
          </PanelBody>
        </Panel>
      )}

      <p className="mono text-[11px] text-text-disabled">
        Source: research/insdn_controller/results/{data.source_files.join(", ")}
      </p>
    </div>
  );
}
