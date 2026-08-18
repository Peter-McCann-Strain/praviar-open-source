"use client";

import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  Database,
  Clock3,
  FileSearch,
  PauseCircle,
  RotateCcw,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { LoadingMark } from "@/components/brand/loading-mark";
import { AIRecoveryBrief } from "@/components/shared/ai-recovery-brief";
import { Badge } from "@/components/ui/badge";
import {
  AlertTriangle,
  clampPipelineStep,
  getPipelineStepLabel,
} from "@/components/analysis-detail/helpers";
import {
  canAccessFullReport,
  getReportAccessHref,
} from "@/lib/report-permissions";
import type { CheckpointState } from "@/stores/pipeline-store";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";

interface RunningAnalysisIndicatorProps {
  currentStep: number;
  hasLiveData: boolean;
  stepDescription?: string;
}

export function RunningAnalysisIndicator({
  currentStep,
  hasLiveData,
  stepDescription,
}: RunningAnalysisIndicatorProps) {
  const label = getPipelineStepLabel(currentStep);

  return (
    <div
      className="flex flex-col items-center py-8"
      role="status"
      aria-live="polite"
    >
      <LoadingMark
        text={
          hasLiveData && stepDescription
            ? `${stepDescription}...`
            : `${label}...`
        }
        size="lg"
      />
    </div>
  );
}

interface PipelineErrorCardProps {
  error: string;
}

export const PIPELINE_ERROR_SAFE_MESSAGE =
  "Pipeline progress could not be refreshed. Existing analysis evidence remains unchanged; retry or review the saved status before relying on this run.";

export function PipelineErrorCard({ error }: PipelineErrorCardProps) {
  const hasDiagnosticDetail = error.trim().length > 0;

  return (
    <Card
      className="border-error/30"
      role="alert"
      data-has-diagnostic-detail={hasDiagnosticDetail ? "true" : "false"}
    >
      <CardContent className="flex items-center gap-4 p-6">
        <AlertTriangle className="h-8 w-8 flex-shrink-0 text-error" />
        <div className="flex-1">
          <p className="font-medium text-error">Pipeline Error</p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {PIPELINE_ERROR_SAFE_MESSAGE}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

interface FailedAnalysisCardProps {
  currentStep: number;
  totalPatentsFound?: number | null;
  updatedAt?: string | null;
}

export function FailedAnalysisCard({
  currentStep,
  totalPatentsFound,
  updatedAt,
}: FailedAnalysisCardProps) {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const canCreateAnalysis = principal.data?.can_create_analysis === true;
  const safeStep = clampPipelineStep(currentStep);
  const label = getPipelineStepLabel(safeStep);

  return (
    <Card className="overflow-hidden border-error/30">
      <CardContent className="space-y-4 p-0">
        <div
          role="alert"
          aria-atomic="true"
          className="border-b border-error/15 bg-error/10 p-5"
        >
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-error/25 bg-error/10 text-error">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="font-semibold text-error">Analysis failed</p>
              <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                The pipeline stopped
                {safeStep > 0 ? ` at step ${safeStep} (${label})` : ""}. Review
                the saved status before rerunning the workflow.
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-4 p-5 pt-0">
          <section
            aria-label="Failed analysis preserved evidence"
            className="rounded-lg border border-brand-primary/15 bg-brand-primary/5 p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
                  Evidence preserved
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
                  {updatedAt
                    ? `Latest saved snapshot: ${formatAnalysisSnapshotTime(updatedAt)}`
                    : "Latest saved pipeline state remains available."}
                </p>
              </div>
              <Badge variant="warning" className="shrink-0">
                Needs review
              </Badge>
            </div>
            <dl className="mt-3 grid gap-2">
              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-3">
                <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  <Clock3
                    className="h-3.5 w-3.5 text-brand-primary"
                    aria-hidden="true"
                  />
                  Last pipeline step
                </dt>
                <dd className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                  {safeStep > 0 ? `Step ${safeStep} of 8` : "Step unavailable"}
                </dd>
              </div>
              {typeof totalPatentsFound === "number" ? (
                <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-3">
                  <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                    <Database
                      className="h-3.5 w-3.5 text-brand-primary"
                      aria-hidden="true"
                    />
                    Search context
                  </dt>
                  <dd className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                    {totalPatentsFound.toLocaleString()} patents found
                  </dd>
                </div>
              ) : null}
            </dl>
          </section>

          <AIRecoveryBrief
            items={[
              "Preserve the last successful evidence and triage context before rerunning.",
              "Use the failed step to decide whether to retry, adjust scope, or ask support.",
              "Start a new analysis only after confirming this run should be superseded.",
            ]}
            note="No legal conclusion changed from this failed analysis state."
          />

          <section
            aria-label="Failed analysis safeguards"
            className="rounded-lg border border-warning/25 bg-warning/10 p-3"
          >
            <div className="flex min-w-0 gap-2">
              <ShieldCheck
                className="mt-0.5 h-4 w-4 shrink-0 text-warning"
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  No legal conclusion changed
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  Recovery guidance does not alter findings, risk ratings, or
                  reviewer decisions.
                </p>
              </div>
            </div>
          </section>

          <div className="grid gap-2">
            <Button
              asChild
              variant="outline"
              className="min-h-11 justify-between gap-2"
            >
              <Link href="/analyses">
                <span className="inline-flex items-center gap-2">
                  <FileSearch className="h-4 w-4" aria-hidden="true" />
                  Return to analysis library
                </span>
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
            {canCreateAnalysis ? (
              <Button asChild className="min-h-11 justify-between gap-2">
                <Link href="/analyses/new">
                  <span className="inline-flex items-center gap-2">
                    <RotateCcw className="h-4 w-4" aria-hidden="true" />
                    Start replacement analysis
                  </span>
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              </Button>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function formatAnalysisSnapshotTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "timestamp unavailable";
  }

  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

interface ReviewPauseCardProps {
  checkpoint: CheckpointState;
}

const CHECKPOINT_LABELS: Record<CheckpointState["checkpoint_type"], string> = {
  identity_review: "Resolved identity review",
  search_review: "Search review",
  triage_review: "Triage review",
  analysis_review: "Analysis review",
  report_review: "Report review",
};

export function ReviewPauseCard({ checkpoint }: ReviewPauseCardProps) {
  return (
    <Card
      className="border-warning/35 bg-warning/5"
      role="status"
      aria-live="polite"
    >
      <CardContent className="space-y-4 p-6">
        <div className="flex items-start gap-4">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-warning/15 text-warning">
            <PauseCircle className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-medium text-[var(--text-primary)]">
              Human review checkpoint
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {CHECKPOINT_LABELS[checkpoint.checkpoint_type]} is waiting for a
              reviewer decision before the pipeline continues.
            </p>
          </div>
        </div>
        <div className="grid gap-3 text-xs text-[var(--text-secondary)] sm:grid-cols-2">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-base)] p-3">
            <div className="flex items-center gap-2 font-medium text-[var(--text-primary)]">
              <UserCheck className="h-4 w-4 text-warning" aria-hidden="true" />
              Reviewer action
            </div>
            <p className="mt-1">
              Approve or reject the checkpoint in the review dialog.
            </p>
          </div>
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-base)] p-3">
            <div className="flex items-center gap-2 font-medium text-[var(--text-primary)]">
              <Clock3 className="h-4 w-4 text-warning" aria-hidden="true" />
              Timeout window
            </div>
            <p className="mt-1 tabular-nums">
              {checkpoint.timeout_minutes} minutes
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function CancelledAnalysisCard() {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const canCreateAnalysis = principal.data?.can_create_analysis === true;

  return (
    <Card className="border-[var(--border-default)]">
      <CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--surface-hover)] text-[var(--text-secondary)]">
            <RotateCcw className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <p className="font-medium text-[var(--text-primary)]">
              Analysis cancelled
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              This run stopped before completion. Start a new analysis when you
              are ready.
            </p>
          </div>
        </div>
        {canCreateAnalysis ? (
          <Button asChild variant="outline" size="sm" className="gap-2">
            <Link href="/analyses/new">
              New analysis
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

interface AnalysisReviewStatus {
  status:
    | "pending"
    | "under_review"
    | "approved"
    | "rejected"
    | "changes_requested"
    | string;
  is_persisted: boolean;
  reviewer_name?: string | null;
  reviewer_email?: string | null;
  reviewed_at?: string | null;
  updated_at?: string | null;
}

interface AnalysisCompleteCardProps {
  id: string;
  reviewStatus?: AnalysisReviewStatus | null;
  currentUserRole?: string | null;
  riskRatingsRestricted?: boolean;
}

const REVIEW_STATUS_LABELS: Record<string, string> = {
  approved: "Approved",
  rejected: "Rejected",
  under_review: "Under review",
  changes_requested: "Changes requested",
};

export function AnalysisCompleteCard({
  id,
  reviewStatus,
  currentUserRole,
  riskRatingsRestricted,
}: AnalysisCompleteCardProps) {
  const showReview =
    reviewStatus &&
    reviewStatus.is_persisted &&
    reviewStatus.status !== "pending";
  const reviewLabel = showReview
    ? (REVIEW_STATUS_LABELS[reviewStatus.status] ?? reviewStatus.status)
    : null;
  const fullReportAllowed = canAccessFullReport(
    currentUserRole,
    riskRatingsRestricted,
  );
  const reportHref = getReportAccessHref(
    id,
    currentUserRole,
    riskRatingsRestricted,
  );

  return (
    <Card className="border-success/30">
      <CardContent className="flex min-w-0 flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6 lg:flex-col lg:items-stretch">
        <div className="flex min-w-0 items-start gap-4 sm:items-center lg:items-start">
          <CheckCircle className="h-8 w-8 shrink-0 text-success" />
          <div className="min-w-0">
            <p className="font-medium text-[var(--text-primary)]">
              Analysis Complete
            </p>
            <p className="text-sm text-[var(--text-secondary)]">
              {fullReportAllowed
                ? "View the full interactive report"
                : "View the authorized executive summary"}
            </p>
            {showReview && reviewLabel ? (
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                <span className="font-medium text-[var(--text-secondary)]">
                  {reviewLabel}
                </span>
                {reviewStatus?.reviewer_name ? (
                  <>
                    {" "}
                    · <span>{reviewStatus.reviewer_name}</span>
                  </>
                ) : null}
              </p>
            ) : null}
          </div>
        </div>
        <div className="flex min-w-0 sm:shrink-0 lg:w-full">
          <Button
            asChild
            className="min-h-11 w-full justify-between gap-2 sm:w-auto sm:justify-center lg:w-full lg:justify-between"
          >
            <Link href={reportHref}>
              <span className="sm:hidden">
                {fullReportAllowed ? "Open report" : "Open summary"}
              </span>
              <span className="hidden sm:inline">
                {fullReportAllowed
                  ? "Open Report Workspace"
                  : "Open Authorized Summary"}
              </span>
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
