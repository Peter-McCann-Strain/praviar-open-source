"use client";

import { AlertTriangle } from "lucide-react";

interface UsageMeterProps {
  limitConfigured?: boolean;
  used: number;
  limit: number;
  pct: number;
}

export function UsageMeter({
  limitConfigured = true,
  used,
  limit,
  pct,
}: UsageMeterProps) {
  const hasLimit = limitConfigured && limit > 0;
  const isOverage = hasLimit && used > limit;
  const isNearLimit = hasLimit && pct >= 80 && !isOverage;
  const usedLabel = used.toLocaleString();
  const limitLabel = hasLimit ? limit.toLocaleString() : "No limit set";
  const boundedPct = hasLimit ? Math.min(Math.max(pct, 0), 100) : 0;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="type-body-md text-[var(--text-secondary)]">
          Analyses this period
        </span>
        <span className="type-body-md font-medium tabular-nums text-[var(--text-primary)]">
          {usedLabel} / {limitLabel}
        </span>
      </div>
      <div
        className="h-3 w-full overflow-hidden rounded-full bg-[var(--surface-muted)]"
        role="meter"
        aria-label="Analysis usage this billing period"
        aria-valuemin={0}
        aria-valuemax={hasLimit ? limit : undefined}
        aria-valuenow={
          hasLimit ? Math.min(used, Math.max(limit, 0)) : undefined
        }
        aria-valuetext={
          hasLimit
            ? `${usedLabel} of ${limitLabel} analyses used`
            : `${usedLabel} analyses used with no configured analysis limit`
        }
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out motion-reduce:transition-none ${
            isOverage
              ? "bg-error"
              : isNearLimit
                ? "bg-warning"
                : "bg-brand-primary"
          }`}
          style={{ width: `${boundedPct}%` }}
        />
      </div>
      {isOverage ? (
        <div className="flex items-center gap-1.5 text-xs text-error">
          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          <span>{used - limit} over limit</span>
        </div>
      ) : null}
      {isNearLimit ? (
        <div className="flex items-center gap-1.5 text-xs text-warning">
          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          <span>Approaching limit</span>
        </div>
      ) : null}
    </div>
  );
}
