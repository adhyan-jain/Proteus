import fs from "node:fs";
import path from "node:path";
import Link from "next/link";
import type { ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/new-ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/new-ui/table";

const R = path.resolve(process.cwd(), "..", "research", "insdn_controller", "results");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const J = (f: string): any => JSON.parse(fs.readFileSync(path.join(R, f), "utf8").replace(/\bNaN\b/g, "null"));
export type Ci = { mean: number; ci95: number };
export const ci = (c?: Ci | null, d = 1) => (c && c.mean !== null ? `${c.mean.toFixed(d)} ± ${c.ci95.toFixed(d)}` : "n/a");
export const MODE: Record<string, string> = { mac: "MAC-pair forwarding", fivetuple: "Per-flow, 10 s idle", fivetuple_short: "Per-flow, 2 s idle" };

export function PageHead({ kicker, title, intro }: { kicker: string; title: string; intro: string }) {
  return (
    <header className="flex flex-col gap-2">
      <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">{kicker}</span>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">{intro}</p>
    </header>
  );
}

export function Why({ children }: { children: ReactNode }) {
  return (
    <p className="border-l-2 border-border pl-3 text-sm leading-relaxed text-muted-foreground">
      <span className="font-semibold text-foreground">What this shows: </span>
      {children}
    </p>
  );
}

export function Say({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md bg-muted p-3 text-sm leading-relaxed">
      <span className="font-semibold">What to tell the professor: </span>
      {children}
    </p>
  );
}

export function Stat({ title, value, note }: { title: string; value: string; note: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl font-semibold tabular-nums">{value}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">{note}</CardContent>
    </Card>
  );
}

export function Section({ title, desc, children }: { title: string; desc?: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {desc && <CardDescription>{desc}</CardDescription>}
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm leading-relaxed">{children}</CardContent>
    </Card>
  );
}

export function DT({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>{head.map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r, i) => (
          <TableRow key={i}>{r.map((c, j) => <TableCell key={j} className={j > 0 ? "tabular-nums align-top" : "align-top"}>{c}</TableCell>)}</TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">{children}</code>;
}

export function Next({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="text-sm underline text-muted-foreground">
      {label} →
    </Link>
  );
}
