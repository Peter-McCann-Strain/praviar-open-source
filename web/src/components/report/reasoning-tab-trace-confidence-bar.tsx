"use client";

import { cn } from "@/lib/utils";

function getConfidenceTone(pct: number) {
  if (pct >= 80) return "bg-[var(--color-success)]";
  if (pct >= 50) return "bg-[var(--color-warning)]";
  return "bg-[var(--color-error)]";
}

export function ReasoningTraceConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);

  return (
    <div
      className="flex items-center gap-2"
      title={`Confidence: ${pct}%`}
      role="meter"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Agent confidence"
    >
      <div className="w-20 h-1.5 rounded-full bg-[var(--surface-hover)] overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            getConfidenceTone(pct),
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-[var(--text-secondary)]">
        {pct}%
      </span>
    </div>
  );
}
