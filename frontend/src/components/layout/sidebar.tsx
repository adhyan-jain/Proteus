"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { NAV_GROUPS } from "./nav-items";

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden h-full w-[204px] shrink-0 flex-col border-r border-border-subtle bg-surface-1 md:flex">
      <div className="flex h-12 items-center gap-2 border-b border-border-subtle px-4">
        <span className="h-2 w-2 rounded-full bg-network live-dot" />
        <span className="text-[13px] font-bold tracking-[0.14em] text-text-primary">PROTEUS</span>
      </div>
      <nav className="flex-1 overflow-y-auto py-2">
        {NAV_GROUPS.map((group) => (
          <div key={group.title} className="mb-2">
            <p className="px-4 pb-1 pt-2 text-[9.5px] font-semibold uppercase tracking-[0.14em] text-text-disabled">
              {group.title}
            </p>
            {group.items.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-2 border-l-2 px-4 py-1.5 text-[12.5px] transition-colors",
                    active
                      ? "border-network bg-surface-2 text-text-primary"
                      : "border-transparent text-text-secondary hover:border-border-strong hover:bg-surface-2/60 hover:text-text-primary"
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="border-t border-border-subtle px-4 py-3">
        <p className="mono text-[10px] leading-relaxed text-text-disabled">
          feedback-controlled synthetic
          <br />
          intervention · research
        </p>
      </div>
    </aside>
  );
}
