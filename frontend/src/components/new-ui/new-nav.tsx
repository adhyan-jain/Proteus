"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  ["/new", "Overview"],
  ["/new/novelty", "Novelty points"],
  ["/new/gap", "1 · Gap"],
  ["/new/forwarding", "2 · Forwarding"],
  ["/new/validity", "3 · Validity"],
  ["/new/literature", "Published results"],
  ["/new/pipeline", "Pipeline"],
  ["/new/faq", "Q&A and scope"],
  ["/new/reproduce", "Reproduce"],
];

export function NewNav() {
  const p = usePathname();
  return (
    <nav className="sticky top-0 z-10 flex flex-wrap items-center gap-1 border-b border-border bg-background/95 px-4 py-2 backdrop-blur">
      {ITEMS.map(([h, l]) => (
        <Link key={h} href={h} className={`rounded-md px-3 py-1.5 text-sm ${p === h ? "bg-secondary font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
          {l}
        </Link>
      ))}
      <Link href="/old" className="ml-auto text-sm text-muted-foreground underline">Old console</Link>
    </nav>
  );
}
