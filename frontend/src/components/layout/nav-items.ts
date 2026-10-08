export type NavItem = { href: string; label: string };
export type NavGroup = { title: string; items: readonly NavItem[] };

// Research evidence (frozen P0 + preregistered P1 campaign) is the primary story; the earlier
// demo-scale console pages are kept, relabelled as the legacy demo.
export const NAV_GROUPS: readonly NavGroup[] = [
  {
    title: "Research",
    items: [
      { href: "/", label: "Overview" },
      { href: "/research/p0", label: "P0 · Feasibility" },
      { href: "/research/p1", label: "P1 · Hypotheses" },
      { href: "/research/controller", label: "Controller" },
      { href: "/research/safety", label: "Safety & Canary" },
      { href: "/research/ablations", label: "Ablations & Controls" },
      { href: "/research/limits", label: "Claims & Limits" },
    ],
  },
  {
    title: "Legacy demo (not P1 evidence)",
    items: [
      { href: "/demo", label: "Demo Overview" },
      { href: "/live-detection", label: "Live Detection" },
      { href: "/experiments", label: "Experiments" },
      { href: "/drift", label: "Drift Monitor" },
      { href: "/synthetic-lab", label: "Synthetic Lab" },
      { href: "/fidelity-gate", label: "Fidelity Gate" },
      { href: "/adaptation", label: "Adaptation" },
      { href: "/topology", label: "Topology" },
      { href: "/audit-log", label: "Audit Log" },
      { href: "/models", label: "Models" },
    ],
  },
] as const;

export const NAV_ITEMS: readonly NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
