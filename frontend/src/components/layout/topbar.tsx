"use client";

import { useEffect, useState } from "react";
import { api, type ExperimentLatest } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

export function TopBar() {
  const [exp, setExp] = useState<ExperimentLatest | null>(null);
  const [apiUp, setApiUp] = useState<boolean | null>(null);
  const [now, setNow] = useState<string>("");

  useEffect(() => {
    api
      .experimentsLatest()
      .then((d) => {
        setExp(d);
        setApiUp(true);
      })
      .catch(() => setApiUp(false));
    const tick = () => setNow(new Date().toISOString().replace("T", " ").slice(0, 19) + "Z");
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const experimentAvailable = exp && exp.available;

  return (
    <header className="flex h-auto min-h-12 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-border-subtle bg-surface-1 px-3 py-2 sm:px-4 sm:py-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={apiUp === null ? "idle" : apiUp ? "good" : "bad"} dot>
          {apiUp === null ? "connecting" : apiUp ? "api online" : "api offline"}
        </Badge>
        <Badge tone="idle" dot>
          no live controller
        </Badge>
        {experimentAvailable ? (
          <Badge tone="network" className="hidden sm:inline-flex">
            model: proteus-demo-classifier · {exp.class_names.length} classes
          </Badge>
        ) : (
          <Badge tone="idle" className="hidden sm:inline-flex">
            no experiment run
          </Badge>
        )}
      </div>
      <div className="flex items-center gap-4">
        {experimentAvailable && (
          <span className="mono hidden text-[11px] text-text-tertiary lg:inline">
            single-seed demo run · {exp.n_timesteps} timesteps
          </span>
        )}
        <span className="mono text-[11px] text-text-secondary">{now}</span>
      </div>
    </header>
  );
}
