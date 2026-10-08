"use client";

import { useEffect, useState } from "react";
import { research, type StagesDoc } from "@/lib/research";
import { Badge } from "@/components/ui/badge";

export function TopBar() {
  const [stages, setStages] = useState<StagesDoc | null>(null);
  const [apiUp, setApiUp] = useState<boolean | null>(null);
  const [now, setNow] = useState<string>("");

  useEffect(() => {
    research
      .stages()
      .then((d) => {
        setStages(d);
        setApiUp(true);
      })
      .catch(() => setApiUp(false));
    const tick = () => setNow(new Date().toISOString().replace("T", " ").slice(0, 19) + "Z");
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const s = stages?.stages as Record<string, { ran?: boolean }> | undefined;
  const branch = stages?.stages.gates.p1_branch ?? null;
  const verdict = branch ? branch.split(":")[0] : null;

  return (
    <header className="flex h-auto min-h-12 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border-subtle bg-surface-1 px-3 py-2 sm:px-4 sm:py-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={apiUp === null ? "idle" : apiUp ? "good" : "bad"} dot>
          {apiUp === null ? "connecting" : apiUp ? "api online" : "api offline"}
        </Badge>
        <Badge tone={s?.p0_summary?.ran ? "good" : "idle"} className="hidden sm:inline-flex">
          P0 {s?.p0_summary?.ran ? "frozen" : "not run"}
        </Badge>
        <Badge tone={!s?.p1_summary?.ran ? "idle" : verdict === "POSITIVE" ? "good" : verdict === "NEGATIVE" ? "warn" : "network"} className="hidden sm:inline-flex">
          P1 {s?.p1_summary?.ran ? (verdict ?? "run").toLowerCase() : "not run"}
        </Badge>
        <Badge tone="idle" dot className="hidden md:inline-flex">
          no live controller
        </Badge>
      </div>
      <span className="mono text-[11px] text-text-secondary">{now}</span>
    </header>
  );
}
