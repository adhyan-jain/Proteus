import type { ClassReport } from "@/lib/api";
import { fmtInt, fmtNum } from "@/lib/utils";

export function ReportTable({ report, classNames }: { report: ClassReport; classNames: string[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] border-collapse text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle text-left text-text-tertiary">
            <th className="py-1.5 pr-3 font-medium">class</th>
            <th className="py-1.5 pr-3 font-medium">precision</th>
            <th className="py-1.5 pr-3 font-medium">recall</th>
            <th className="py-1.5 pr-3 font-medium">f1-score</th>
            <th className="py-1.5 font-medium">support</th>
          </tr>
        </thead>
        <tbody>
          {classNames.map((name) => {
            const row = report[name];
            if (!row) return null;
            return (
              <tr key={name} className="mono border-b border-border-subtle/60">
                <td className="py-1.5 pr-3 text-text-primary">{name}</td>
                <td className="py-1.5 pr-3 text-text-secondary">{fmtNum(row.precision)}</td>
                <td className="py-1.5 pr-3 text-text-secondary">{fmtNum(row.recall)}</td>
                <td className="py-1.5 pr-3 font-semibold text-text-primary">{fmtNum(row["f1-score"])}</td>
                <td className="py-1.5 text-text-tertiary">{fmtInt(row.support)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
