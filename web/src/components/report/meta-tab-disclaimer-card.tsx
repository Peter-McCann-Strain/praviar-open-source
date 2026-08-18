"use client";

export function DisclaimerCard({ disclaimer }: { disclaimer: string }) {
  if (!disclaimer) {
    return null;
  }

  return (
    <div
      className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-hover)] p-4"
      data-print-redundant-disclaimer
    >
      <p className="text-xs leading-relaxed text-[var(--text-tertiary)]">
        {disclaimer}
      </p>
    </div>
  );
}
