"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { NAV_ITEMS } from "./nav-items";

export function MobileNav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto border-b border-border-subtle bg-surface-1 px-3 py-2 md:hidden">
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "shrink-0 rounded px-2.5 py-1 text-[11.5px] whitespace-nowrap",
              active ? "bg-surface-3 text-text-primary" : "text-text-secondary"
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
