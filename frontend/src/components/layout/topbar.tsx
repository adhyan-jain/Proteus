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
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border-subtle bg-surface-1 px-4">
      <div className="flex items-center gap-3">
        <Badge tone={apiUp === null ? "idle" : apiUp ? "good" : "bad"} dot>
          {apiUp === null ? "connecting" : apiUp ? "api online" : "api offline"}
        </Badge>
        <Badge tone="idle" dot>
          no live controller
        </Badge>
        {experimentAvailable ? (
          <Badge tone="network">
            model: proteus-demo-classifier · {exp.class_names.length} classes
          </Badge>
        ) : (
          <Badge tone="idle">no experiment run</Badge>
        )}
      </div>
      <div className="flex items-center gap-4">
        {experimentAvailable && (
          <span className="mono text-[11px] text-text-tertiary">
            single-seed demo run · {exp.n_timesteps} timesteps
          </span>
        )}
        <span className="mono text-[11px] text-text-secondary">{now}</span>
      </div>
    </header>
  );
}
