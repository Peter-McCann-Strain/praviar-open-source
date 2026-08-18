import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  className?: string;
}

const STATUS_STYLES: Record<string, string> = {
  pending:
    "bg-[var(--surface-active)] text-[var(--text-secondary)] border-[var(--border-default)]",
  running:
    "bg-info/15 text-[var(--text-primary)] border-info/25 animate-pulse motion-reduce:animate-none",
  completed:
    "bg-success/15 text-[var(--color-success-badge-fg)] border-success/25",
  failed: "bg-error/15 text-[var(--color-error-badge-fg)] border-error/25",
  cancelled:
    "bg-[var(--surface-active)] text-[var(--text-tertiary)] border-[var(--border-default)]",
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        STATUS_STYLES[status] || STATUS_STYLES.pending,
        "shadow-[var(--shadow-xs)]",
        className,
      )}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}
