"use client";

import { cn } from "@/lib/utils";

interface ConfidenceBarProps {
  /** Uncalibrated model-support score between 0 and 1. */
  value: number;
  size?: "sm" | "md";
}

export function ConfidenceBar({ value, size = "md" }: ConfidenceBarProps) {
  const pct = Math.round(value * 100);

  const barColor =
    value >= 0.8 ? "bg-success" : value >= 0.5 ? "bg-warning" : "bg-error";

  const heightClass = size === "sm" ? "h-1.5" : "h-2";

  return (
    <div
      className="flex items-center gap-2"
      aria-label={`Model-support score ${pct} out of 100; not a probability`}
    >
      <div
        className={cn(
          "flex-1 rounded-full bg-[var(--surface-active)] overflow-hidden",
          heightClass,
        )}
      >
        <div
          className={cn("h-full rounded-full transition-all", barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-[var(--text-secondary)] tabular-nums w-8 text-right">
        {pct}/100
      </span>
    </div>
  );
}
