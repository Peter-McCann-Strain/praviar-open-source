"use client";

import { useEffect, useLayoutEffect, useState } from "react";
import { Breadcrumb } from "@/components/shared/breadcrumb";
import {
  AnalysisCompleteCard,
  CancelledAnalysisCard,
  FailedAnalysisCard,
  PipelineErrorCard,
  ReviewPauseCard,
} from "@/components/analysis-detail/analysis-status-cards";
import { AnalysisHeader } from "@/components/analysis-detail/analysis-header";
import {
  AnalysisAuthState,
  AnalysisErrorState,
  AnalysisLoadingState,
  AnalysisNotFoundState,
} from "@/components/analysis-detail/analysis-states";
import { CheckpointOverlay } from "@/components/analysis-detail/checkpoint-overlay";
import { AnalysisLaunchContextCard } from "@/components/analysis-detail/analysis-launch-context-card";
import { CompoundSummaryCard } from "@/components/analysis-detail/compound-summary-card";
import { DevelopmentFixturePreviewCard } from "@/components/analysis-detail/development-fixture-preview-card";
import { PipelineProgressCard } from "@/components/analysis-detail/pipeline-progress-card";
import { RunningAnalysisWorkspace } from "@/components/analysis-detail/running-analysis-workspace";
import { useAnalysis } from "@/hooks/use-analysis";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePipelineStream } from "@/hooks/use-pipeline-stream";
import { APIError } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { logError } from "@/lib/error-logger";
import {
  useActiveCheckpoint,
  useCurrentStep,
  useIsComplete,
  useOverallRisk,
  usePipelineError,
  usePipelineSteps,
  usePipelineStore,
  useProgressPayloads,
} from "@/stores/pipeline-store";

const DEMO_RUNNING_ELAPSED_MS = 6 * 60 * 1000;

export function getRunningElapsedMs({
  createdAt,
  isDemoMode,
  isRunning,
  nowMs,
}: {
  createdAt?: string | null;
  isDemoMode: boolean;
  isRunning: boolean;
  nowMs: number;
}) {
  if (!isRunning || !createdAt) {
    return 0;
  }

  if (isDemoMode) {
    return DEMO_RUNNING_ELAPSED_MS;
  }

  const createdMs = new Date(createdAt).getTime();
  if (!Number.isFinite(createdMs)) {
    return 0;
  }

  return Math.max(0, nowMs - createdMs);
}

export function AnalysisDetailContent({ id }: { id: string }) {
  const token = useAuthToken();
  const {
    data: apiAnalysis,
    isLoading,
    isError,
    error: queryError,
    refetch,
  } = useAnalysis(id, token);
  const activeCheckpoint = useActiveCheckpoint();
  const clearCheckpoint = usePipelineStore((state) => state.clearCheckpoint);
  const liveSteps = usePipelineSteps();
  const streamedCurrentStep = useCurrentStep();
  const pipelineIsComplete = useIsComplete();
  const pipelineError = usePipelineError();
  const liveOverallRisk = useOverallRisk();
  const progressPayloads = useProgressPayloads();

  const analysis = apiAnalysis ?? null;
  const isDevelopmentFixture = analysis?.development_fixture === true;
  const isRunning = analysis?.status === "running" && !isDevelopmentFixture;
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!isRunning || !analysis?.created_at) {
      return;
    }

    const interval = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [analysis?.created_at, isRunning]);

  // Layout effect runs before paint, so stale SSE state is cleared before users
  // see a newly opened analysis detail view.
  useLayoutEffect(() => {
    usePipelineStore.getState().reset();
  }, [id]);

  usePipelineStream(isRunning && !DEMO_MODE_ENABLED ? id : null, token);

  if (isError) {
    logError(new Error("Analysis data could not be loaded"), {
      source: "AnalysisDetailPage",
      extra: {
        action: "load_analysis",
        analysisId: id,
        status: queryError instanceof APIError ? queryError.status : undefined,
      },
    });
    if (queryError instanceof APIError && queryError.status === 401) {
      return <AnalysisAuthState />;
    }

    if (
      queryError instanceof APIError &&
      (queryError.status === 403 || queryError.status === 404)
    ) {
      return <AnalysisNotFoundState />;
    }

    return (
      <AnalysisErrorState
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (isLoading) {
    return <AnalysisLoadingState />;
  }

  if (!analysis && !DEMO_MODE_ENABLED && !token) {
    return <AnalysisAuthState />;
  }

  if (!analysis) {
    return <AnalysisNotFoundState />;
  }

  const isComplete = analysis.status === "completed";
  const isFailed = analysis.status === "failed";
  const isCancelled = analysis.status === "cancelled";
  // Switch to live (SSE) step data only once the replay has caught up to the
  // DB-stored current_step. This prevents the UI from briefly regressing to
  // step 1 while the historical replay replays past states on reconnect.
  const hasLiveData =
    isRunning &&
    streamedCurrentStep > 0 &&
    streamedCurrentStep >= analysis.current_step;
  const currentStep = hasLiveData ? streamedCurrentStep : analysis.current_step;
  const overallRisk = pipelineIsComplete
    ? liveOverallRisk
    : analysis.overall_risk;
  const elapsedMs = getRunningElapsedMs({
    createdAt: analysis.created_at,
    isDemoMode: DEMO_MODE_ENABLED,
    isRunning,
    nowMs,
  });

  return (
    <div className="mx-auto max-w-6xl space-y-8 animate-fade-up">
      <Breadcrumb
        ariaLabel="Analysis detail breadcrumb"
        items={[
          { label: "Analyses", href: "/analyses" },
          { label: analysis.compound_name },
        ]}
      />

      <AnalysisHeader analysis={analysis} overallRisk={overallRisk} />

      <AnalysisLaunchContextCard analysis={analysis} />

      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
        <div className="min-w-0 space-y-6">
          <CompoundSummaryCard
            analysis={analysis}
            isComplete={isComplete}
            isDevelopmentFixture={isDevelopmentFixture}
            isFailed={isFailed}
            isRunning={isRunning}
            elapsedMs={elapsedMs}
          />

          {isDevelopmentFixture ? (
            <DevelopmentFixturePreviewCard
              currentStep={analysis.current_step}
            />
          ) : (
            <PipelineProgressCard
              currentStep={currentStep}
              elapsedMs={elapsedMs}
              hasLiveData={hasLiveData}
              invalidityAssessmentsCount={analysis.invalidity_assessments_count}
              isComplete={isComplete}
              isFailed={isFailed}
              isRunning={isRunning}
              pipelineIsComplete={pipelineIsComplete}
              progressPct={analysis.progress_pct}
              progressPayloads={progressPayloads}
              steps={liveSteps}
            />
          )}
        </div>

        <div
          className={
            isComplete || pipelineIsComplete
              ? "order-first min-w-0 space-y-4 lg:order-none lg:sticky lg:top-24"
              : "min-w-0 space-y-4 lg:sticky lg:top-24"
          }
        >
          {isRunning ? (
            <RunningAnalysisWorkspace
              currentStep={currentStep}
              elapsedMs={elapsedMs}
              hasCheckpoint={Boolean(activeCheckpoint)}
              hasLiveData={hasLiveData}
              hasPipelineIssue={Boolean(pipelineError)}
              progressPct={analysis.progress_pct}
              progressPayloads={progressPayloads}
              steps={liveSteps}
            />
          ) : null}

          {activeCheckpoint ? (
            <ReviewPauseCard checkpoint={activeCheckpoint} />
          ) : null}

          {pipelineError && !activeCheckpoint ? (
            <PipelineErrorCard error={pipelineError} />
          ) : null}

          {isFailed && !pipelineError ? (
            <FailedAnalysisCard
              currentStep={currentStep}
              totalPatentsFound={analysis.total_patents_found}
              updatedAt={analysis.updated_at}
            />
          ) : null}

          {isCancelled ? <CancelledAnalysisCard /> : null}

          {isComplete || pipelineIsComplete ? (
            <AnalysisCompleteCard
              id={id}
              reviewStatus={analysis.review_status}
              currentUserRole={analysis.current_user_role}
              riskRatingsRestricted={analysis.risk_ratings_restricted}
            />
          ) : null}
        </div>
      </div>

      <CheckpointOverlay
        analysisId={id}
        activeCheckpoint={activeCheckpoint}
        onClose={clearCheckpoint}
      />
    </div>
  );
}
