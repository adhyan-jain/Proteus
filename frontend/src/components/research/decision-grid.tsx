import type { DecisionRow } from "@/lib/research";
import { REASON_LABEL } from "@/lib/research-format";

type Cat = "star" | "real" | "envelope" | "violated" | "utility" | "noregion";

function categorize(r: DecisionRow): Cat {
  if (r.promoted) return r.branch === "star" ? "star" : "real";
  if (r.reason === "no_affected_region") return "noregion";
  if (r.reason === "envelope_violated") return "violated";
  if (r.reason?.startsWith("envelope")) return "envelope";
  return "utility";
}

const CAT: Record<Cat, { cls: string; label: string }> = {
  star: { cls: "bg-synthetic text-surface-0", label: "promoted · synthetic candidate" },
  real: { cls: "bg-good text-surface-0", label: "promoted · real-only candidate" },
  envelope: { cls: "bg-warn-dim text-warn", label: "rejected · envelope not demonstrated" },
  violated: { cls: "bg-bad text-surface-0", label: "rejected · envelope violated" },
  utility: { cls: "bg-network-dim text-network", label: "rejected · no demonstrated gain" },
  noregion: { cls: "bg-surface-2 text-text-disabled", label: "no affected region (nothing to do)" },
};

// seeds x windows grid of per-window outcomes for one arm. Every cell is one controller decision
// read verbatim from the result files.
export function DecisionGrid({ rows }: { rows: Record<string, DecisionRow[]> }) {
  const seeds = Object.keys(rows).sort((a, b) => Number(a) - Number(b));
  if (seeds.length === 0) return null;
  const windows = rows[seeds[0]].map((r) => r.t);
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="mono border-separate border-spacing-[3px] text-[10.5px]">
          <thead>
            <tr>
              <th className="pr-2 text-left font-normal text-text-tertiary">seed \ t</th>
              {windows.map((t) => (
                <th key={t} className="w-10 text-center font-normal text-text-tertiary">
                  {t}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {seeds.map((s) => (
              <tr key={s}>
                <td className="pr-2 text-text-secondary">{s}</td>
                {rows[s].map((r) => {
                  const c = CAT[categorize(r)];
                  const tip = `seed ${s}, t=${r.t}\n${REASON_LABEL[r.reason ?? ""] ?? r.reason}` +
                    `${r.star_reason && r.star_reason !== "no_star" ? ` (candidate: ${r.star_reason})` : ""}` +
                    `\nk=${r.k ?? "–"} stop=${r.stop_reason ?? "–"}${r.rollback ? "\nROLLED BACK by canary" : ""}`;
                  return (
                    <td key={r.t} title={tip}
                      className={`h-6 w-10 rounded-sm text-center ${c.cls} ${r.rollback ? "ring-2 ring-bad" : ""}`}>
                      {r.k && r.k > 0 ? `k${r.k}` : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {Object.values(CAT).map((c) => (
          <span key={c.label} className="flex items-center gap-1.5 text-[11px] text-text-tertiary">
            <span className={`inline-block h-3 w-3 rounded-sm ${c.cls.split(" ")[0]}`} />
            {c.label}
          </span>
        ))}
        <span className="flex items-center gap-1.5 text-[11px] text-text-tertiary">
          <span className="inline-block h-3 w-3 rounded-sm ring-2 ring-bad" /> canary rollback · k# = accepted dose steps
        </span>
      </div>
    </div>
  );
}
