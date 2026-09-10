import { cn } from "@/lib/utils";

export function EmptyState({
  title,
  reason,
  className,
}: {
  title?: string;
  reason: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-[160px] flex-col items-center justify-center gap-2 rounded border border-dashed border-border-default bg-surface-0/40 px-6 py-10 text-center",
        className
      )}
    >
      <span className="mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-text-disabled">
        {title ?? "NOT AVAILABLE"}
      </span>
      <p className="max-w-md text-[12px] leading-relaxed text-text-tertiary">{reason}</p>
    </div>
  );
}
