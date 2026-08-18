"use client";

import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { STEP_ICONS, STEP_LABELS } from "@/components/analysis-detail/helpers";
import type { ProgressStepViewModel } from "@/components/analysis-detail/pipeline-progress-card-helpers";

export function PipelineProgressStepRow({
  viewModel,
}: {
  viewModel: ProgressStepViewModel;
}) {
  const Icon = STEP_ICONS[viewModel.stepNum - 1];
  const label = STEP_LABELS[viewModel.stepNum - 1];

  return (
    <div
      className="grid min-w-0 grid-cols-[2.5rem_minmax(0,1fr)] gap-3 sm:flex sm:items-center sm:gap-4"
      data-testid={`pipeline-progress-step-${viewModel.stepNum}`}
    >
      <div
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-full transition-all duration-500",
          viewModel.isDone &&
            !viewModel.hasCoverageGap &&
            "bg-success/20 text-[var(--color-success-badge-fg)]",
          viewModel.hasCoverageGap && "bg-warning/15 text-warning",
          viewModel.isActive && "bg-brand-primary/20 text-brand-primary",
          viewModel.isPending &&
            "bg-[var(--surface-hover)] text-[var(--text-disabled)]",
          viewModel.isFailed && "bg-error/20 text-error",
        )}
      >
        {viewModel.isActive ? (
          <Loader2
            className="h-5 w-5 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
        ) : (
          <Icon className="h-5 w-5" aria-hidden="true" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p
            className={cn(
              "text-sm font-medium",
              viewModel.isDone &&
                !viewModel.hasCoverageGap &&
                "text-[var(--text-primary)]",
              viewModel.hasCoverageGap && "text-warning",
              viewModel.isActive && "text-brand-primary",
              viewModel.isPending && "text-[var(--text-disabled)]",
              viewModel.isFailed && "text-error",
            )}
          >
            Step {viewModel.stepNum}: {label}
            <span className="sr-only">
              {" "}
              -{" "}
              {viewModel.hasCoverageGap
                ? "workflow closed without assessment output"
                : viewModel.isFailed
                  ? "failed"
                  : viewModel.isDone
                    ? "completed"
                    : viewModel.isActive
                      ? "running"
                      : "pending"}
            </span>
          </p>
          {viewModel.badgeCount ? (
            <span className="inline-flex items-center rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-[var(--color-success-badge-fg)] ring-1 ring-inset ring-success/20">
              {viewModel.badgeCount}
            </span>
          ) : null}
        </div>

        {viewModel.message && (viewModel.isActive || viewModel.isDone) ? (
          <p className="mt-0.5 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
            {viewModel.message}
          </p>
        ) : null}

        {viewModel.step4Progress ? (
          <div className="mt-1.5 flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--border-default)]">
              <div
                className="h-full rounded-full bg-brand-primary transition-all duration-500 ease-out"
                style={{
                  width: `${Math.min(
                    100,
                    (viewModel.step4Progress.analyzed /
                      viewModel.step4Progress.total) *
                      100,
                  )}%`,
                }}
              />
            </div>
            <span className="flex-shrink-0 text-xs tabular-nums text-[var(--text-tertiary)]">
              {viewModel.step4Progress.analyzed}/{viewModel.step4Progress.total}
            </span>
          </div>
        ) : null}
      </div>

      <div className="col-start-2 text-xs tabular-nums text-[var(--text-tertiary)] sm:col-start-auto sm:flex-shrink-0">
        {viewModel.durationLabel}
      </div>
    </div>
  );
}
