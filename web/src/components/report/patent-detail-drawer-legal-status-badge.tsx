"use client";

export function PatentDetailDrawerLegalStatusBadge({
  status,
}: {
  status: string;
}) {
  const colors: Record<string, string> = {
    active: "bg-success/15 text-success border-success/30",
    expired: "bg-error/15 text-error border-error/30",
    lapsed: "bg-warning/15 text-warning border-warning/30",
    revoked: "bg-error/15 text-error border-error/30",
    pending: "bg-info/15 text-info border-info/30",
    unknown:
      "bg-[var(--surface-muted)] text-[var(--text-tertiary)] border-[var(--border-default)]",
  };
  const classes = colors[status.toLowerCase()] ?? colors.unknown;

  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-bold uppercase border ${classes}`}
    >
      {status}
    </span>
  );
}
