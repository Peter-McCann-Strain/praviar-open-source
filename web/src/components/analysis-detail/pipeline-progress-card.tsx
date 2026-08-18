"use client";

import { Card, CardContent } from "@/components/ui/card";
import { LiveResultsFeed } from "@/components/pipeline/live-results-feed";
import { ReportSkeleton } from "@/components/report/report-skeleton";
import { formatDuration } from "@/lib/utils";
import type { PipelineStep } from "@/stores/pipeline-store";
import type { StepNumber } from "@/types/pipeline";
import {
  clampPipelineStep,
  STEP_LABELS,
} from "@/components/analysis-detail/helpers";
import {
  buildLiveResults,
  buildStepViewModel,
  type ProgressPayloads,
} from "@/components/analysis-detail/pipeline-progress-card-helpers";
import { PipelineProgressSummary } from "@/components/analysis-detail/pipeline-progress-summary";
import { PipelineProgressStepRow } from "@/components/analysis-detail/pipeline-progress-step-row";
import { ResponsiveDisclosure } from "@/components/shared/responsive-disclosure";
import { ChevronDown } from "lucide-react";

export interface PipelineProgressCardProps {
  currentStep: number;
  elapsedMs: number;
  hasLiveData: boolean;
  invalidityAssessmentsCount?: number | null;
  isComplete: boolean;
  isFailed: boolean;
  isRunning: boolean;
  pipelineIsComplete: boolean;
  progressPct?: number | null;
  progressPayloads: ProgressPayloads;
  steps: PipelineStep[];
}

export function PipelineProgressCard({
  currentStep,
  elapsedMs,
  hasLiveData,
  invalidityAssessmentsCount,
  isComplete,
  isFailed,
  isRunning,
  pipelineIsComplete,
  progressPct,
  progressPayloads,
  steps,
}: PipelineProgressCardProps) {
  const safeCurrentStep = clampPipelineStep(currentStep);
  return (
    <Card>
      <CardContent
        className="p-4 sm:p-6 lg:p-8"
        data-testid="pipeline-progress-card-content"
      >
        <PipelineProgressSummary
          className="mt-0"
          currentStep={currentStep}
          elapsedMs={elapsedMs}
          isComplete={isComplete}
          isFailed={isFailed}
          isRunning={isRunning}
          pipelineIsComplete={pipelineIsComplete}
          progressPct={progressPct}
        />

        <ResponsiveDisclosure
          className="group mt-4"
          data-testid="pipeline-execution-disclosure"
          summary={
            <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 px-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 sm:hidden [&::-webkit-details-marker]:hidden">
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-[var(--text-primary)]">
                  8-stage execution receipt
                </span>
                <span className="mt-0.5 block text-xs leading-5 text-[var(--text-secondary)]">
                  {isComplete || pipelineIsComplete
                    ? "All stages completed · inspect timing and outputs"
                    : isFailed
                      ? `Stopped at stage ${safeCurrentStep || 1} · inspect the failure trail`
                      : isRunning
                        ? `Stage ${safeCurrentStep || 1} active · inspect live evidence`
                        : "Queued · inspect the execution plan"}
                </span>
              </span>
              <ChevronDown
                className="h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180"
                aria-hidden="true"
              />
            </summary>
          }
        >
          <div className="mt-4 space-y-4 sm:mt-0">
            {STEP_LABELS.map((_, index) => {
              const stepNum = index + 1;
              const liveStep = hasLiveData ? steps[index] : null;
              const progress = progressPayloads[stepNum as StepNumber];
              const viewModel = buildStepViewModel({
                currentStep: safeCurrentStep,
                formatDuration,
                hasLiveData,
                invalidityAssessmentsCount,
                isComplete,
                isFailed,
                isRunning,
                liveStep,
                progress,
                stepNum,
              });

              return (
                <PipelineProgressStepRow key={stepNum} viewModel={viewModel} />
              );
            })}
          </div>
        </ResponsiveDisclosure>

        {isComplete && invalidityAssessmentsCount === 0 ? (
          <div
            className="mt-5 rounded-lg border border-warning/30 bg-warning/5 p-4 text-sm leading-6 text-[var(--text-secondary)]"
            role="note"
          >
            <p className="font-semibold text-[var(--text-primary)]">
              Invalidity workflow closed without assessment output
            </p>
            <p className="mt-1">
              Pipeline completion records that the stage returned; it does not
              assert invalidity coverage. This report contains no governed
              invalidity assessment, so validity remains unknown and requires
              counsel review.
            </p>
          </div>
        ) : null}

        {isRunning && currentStep >= 2 ? (
          <div className="mt-4">
            <LiveResultsFeed
              title="Live Results"
              results={buildLiveResults(progressPayloads)}
            />
          </div>
        ) : null}

        {safeCurrentStep >= 8 && isRunning ? (
          <div className="mt-6">
            <h3 className="mb-3 text-sm font-semibold text-[var(--text-tertiary)]">
              Report preview — generating...
            </h3>
            <ReportSkeleton />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
