"use client";

import { ArrowDown } from "lucide-react";
import type { FunnelStageConfig } from "@/components/report/funnel-explorer-helpers";
import type { FunnelStage } from "@/components/report/funnel-explorer-helpers";
import { cn } from "@/lib/utils";

const STAGE_INTERACTION_CLASSES: Record<
  FunnelStage,
  { idle: string; selected: string }
> = {
  discovered: {
    idle: "praviar-glass-chip hover:border-info/20 hover:bg-info/10",
    selected: "border-info/20 bg-info/10 shadow-lg ring-1 ring-info/30",
  },
  hard_filter: {
    idle: "praviar-glass-chip hover:border-warning/20 hover:bg-warning/10",
    selected:
      "border-warning/20 bg-warning/10 shadow-lg ring-1 ring-warning/30",
  },
  ranked: {
    idle: "praviar-glass-chip hover:border-info/20 hover:bg-info/10",
    selected: "border-info/20 bg-info/10 shadow-lg ring-1 ring-info/30",
  },
  triaged: {
    idle: "praviar-glass-chip hover:border-brand-primary/20 hover:bg-brand-primary/10",
    selected:
      "border-brand-primary/20 bg-brand-primary/10 shadow-lg ring-1 ring-brand-primary/30",
  },
  analyzed: {
    idle: "praviar-glass-chip hover:border-success/20 hover:bg-success/10",
    selected:
      "border-success/20 bg-success/10 shadow-lg ring-1 ring-success/30",
  },
};

export function StageCard({
  stage,
  count,
  prevCount,
  isSelected,
  onClick,
}: {
  stage: FunnelStageConfig;
  count: number;
  prevCount: number | null;
  isSelected: boolean;
  onClick: () => void;
}) {
  const Icon = stage.icon;
  const passRate =
    prevCount && prevCount > 0 ? ((count / prevCount) * 100).toFixed(0) : null;
  const rejected = prevCount ? prevCount - count : null;
  const interactionClasses = STAGE_INTERACTION_CLASSES[stage.id];

  return (
    <div className="flex flex-col items-center gap-1">
      <button
        type="button"
        onClick={onClick}
        aria-pressed={isSelected}
        className={cn(
          "w-full cursor-pointer rounded-lg border p-4 transition-all",
          isSelected ? interactionClasses.selected : interactionClasses.idle,
        )}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-lg ${stage.bgColor}`}
            >
              <Icon className={`h-4 w-4 ${stage.color}`} aria-hidden="true" />
            </div>
            <div className="text-left">
              <p className="text-xs text-[var(--text-tertiary)]">
                {stage.label}
              </p>
              <p className="text-lg font-bold tabular-nums text-[var(--text-primary)]">
                {count.toLocaleString()}
              </p>
            </div>
          </div>
          {passRate ? (
            <div className="text-right">
              <p className="text-xs text-[var(--text-disabled)]">pass rate</p>
              <p className={`text-sm font-semibold ${stage.color}`}>
                {passRate}%
              </p>
            </div>
          ) : null}
        </div>
        {rejected !== null && rejected > 0 ? (
          <p className="mt-1 text-xs text-[var(--text-disabled)]">
            {rejected.toLocaleString()} removed
          </p>
        ) : null}
      </button>
    </div>
  );
}

export function FlowArrow() {
  return (
    <div className="flex justify-center py-1">
      <ArrowDown className="h-4 w-4 text-[var(--text-disabled)]" />
    </div>
  );
}
