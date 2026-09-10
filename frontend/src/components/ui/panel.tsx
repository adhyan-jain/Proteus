import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export function Panel({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-md border border-border-subtle bg-surface-1 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.02)]",
        className
      )}
    >
      {children}
    </div>
  );
}

export function PanelHeader({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border-subtle px-4 py-3">
      <div>
        <h3 className="text-[13px] font-semibold tracking-wide text-text-primary">{title}</h3>
        {subtitle && <p className="mt-0.5 text-[11px] text-text-tertiary">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function PanelBody({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("p-4", className)}>{children}</div>;
}
