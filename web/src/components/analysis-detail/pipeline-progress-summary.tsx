"use client";

import { cn } from "@/lib/utils";
import {
  clampPipelineStep,
  formatElapsed,
  TOTAL_PIPELINE_STEPS,
} from "@/components/analysis-detail/helpers";

interface PipelineProgressSummaryProps {
  className?: string;
  currentStep: number;
  elapsedMs: number;
  isComplete: boolean;
  isFailed: boolean;
  isRunning: boolean;
  pipelineIsComplete: boolean;
  progressPct?: number | null;
}

export function PipelineProgressSummary({
  className,
  currentStep,
  elapsedMs,
  isComplete,
  isFailed,
  isRunning,
  pipelineIsComplete,
  progressPct,
}: PipelineProgressSummaryProps) {
  const safeCurrentStep = clampPipelineStep(currentStep);
  const hasBackendProgress =
    typeof progressPct === "number" && Number.isFinite(progressPct);
  const fallbackProgressPercent =
    isRunning && safeCurrentStep > 0
      ? Math.round(((safeCurrentStep - 1) / TOTAL_PIPELINE_STEPS) * 100)
      : Math.round((safeCurrentStep / TOTAL_PIPELINE_STEPS) * 100);
  const progressPercent =
    isComplete || pipelineIsComplete
      ? 100
      : hasBackendProgress
        ? Math.min(99, Math.max(0, Math.round(progressPct)))
        : fallbackProgressPercent;
  const progressWidth =
    isComplete || pipelineIsComplete ? 100 : progressPercent;
  const progressLabel =
    safeCurrentStep === 0
      ? "Pipeline queued"
      : `Pipeline ${progressPercent}% complete · step ${safeCurrentStep} of ${TOTAL_PIPELINE_STEPS}`;

  return (
    <div className={cn("mt-8", className)}>
      <div
        className="h-2 overflow-hidden rounded-full bg-[var(--surface-hover)]"
        role="progressbar"
        aria-valuenow={progressPercent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Pipeline progress"
      >
        <div
          className={cn(
            "h-full rounded-full transition-all duration-1000 ease-out",
            isFailed ? "bg-error" : "brand-gradient",
          )}
          style={{
            width: `${progressWidth}%`,
          }}
        />
      </div>
      <p
        className="mt-2 text-center text-xs tabular-nums text-[var(--text-tertiary)]"
        aria-live="polite"
      >
        {isComplete || pipelineIsComplete
          ? "Analysis complete"
          : isFailed
            ? safeCurrentStep > 0
              ? `Failed at step ${safeCurrentStep} of ${TOTAL_PIPELINE_STEPS}`
              : "Pipeline failed before the first stage"
            : progressLabel}
        {isRunning && elapsedMs > 0 ? (
          <span className="ml-2 text-[var(--text-disabled)]">
            ({formatElapsed(elapsedMs)} elapsed)
          </span>
        ) : null}
      </p>
    </div>
  );
}
