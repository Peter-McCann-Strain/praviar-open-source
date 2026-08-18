"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Clock3,
  Database,
  FileCheck2,
  FileText,
  GitBranch,
  Layers3,
  LockKeyhole,
  PauseCircle,
  Radar,
  SearchCheck,
  ShieldCheck,
  UserCheck,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn, formatNumber } from "@/lib/utils";
import type { PipelineStep } from "@/stores/pipeline-store";
import type {
  Step2Payload,
  Step3Payload,
  Step4Payload,
  Step6Payload,
  Step7Payload,
  StepNumber,
} from "@/types/pipeline";
import {
  buildLiveResults,
  type ProgressPayloads,
} from "@/components/analysis-detail/pipeline-progress-card-helpers";
import {
  clampPipelineStep,
  formatElapsed,
  getPipelineStepLabel,
  getStepMicrocopy,
  TOTAL_PIPELINE_STEPS,
} from "@/components/analysis-detail/helpers";

interface RunningAnalysisWorkspaceProps {
  currentStep: number;
  elapsedMs: number;
  hasCheckpoint: boolean;
  hasLiveData: boolean;
  hasPipelineIssue?: boolean;
  progressPct?: number | null;
  progressPayloads: ProgressPayloads;
  steps: PipelineStep[];
}

type GateStatus = "completed" | "running" | "pending" | "failed";
type DossierChangeTone = "source" | "triage" | "claim" | "verification";

const REVIEW_GATES = [
  { label: "Source trace", step: 2, icon: SearchCheck },
  { label: "Claim packet", step: 4, icon: FileCheck2 },
  { label: "Invalidity sweep", step: 6, icon: ShieldCheck },
  { label: "Cross-check", step: 7, icon: UserCheck },
] as const;

function getLiveStep(steps: PipelineStep[], stepNumber: number) {
  return (
    steps.find((step) => step.number === stepNumber) ??
    steps[stepNumber - 1] ??
    null
  );
}

function getGateStatus({
  currentStep,
  hasLiveData,
  stepNumber,
  steps,
}: {
  currentStep: number;
  hasLiveData: boolean;
  stepNumber: number;
  steps: PipelineStep[];
}): GateStatus {
  const liveStep = getLiveStep(steps, stepNumber);
  if (hasLiveData && liveStep) {
    return liveStep.status;
  }
  if (stepNumber < currentStep) {
    return "completed";
  }
  if (stepNumber === currentStep) {
    return "running";
  }
  return "pending";
}

function statusTone(status: GateStatus) {
  switch (status) {
    case "completed":
      return "border-success/20 bg-success/10 text-success";
    case "running":
      return "border-brand-primary/25 bg-brand-primary/10 text-brand-primary";
    case "failed":
      return "border-error/20 bg-error/10 text-error";
    default:
      return "border-[var(--border-subtle)] bg-[var(--surface-hover)] text-[var(--text-tertiary)]";
  }
}

function getNextArtifact(currentStep: number): string {
  if (currentStep <= 1) return "Source search manifest";
  if (currentStep <= 2) return "Deduplicated patent family set";
  if (currentStep <= 3) return "Reviewer-ready claim packet";
  if (currentStep <= 4) return "Material claim mapping";
  if (currentStep <= 5) return "Equivalence assessment";
  if (currentStep <= 6) return "Invalidity defense notes";
  if (currentStep <= 7) return "Verified report draft";
  return "Interactive FTO report";
}

function metricValue(value: number | null) {
  return value == null ? "Pending" : formatNumber(value);
}

function buildDossierChanges({
  analysisPayload,
  invalidityPayload,
  searchPayload,
  triagePayload,
  verificationPayload,
}: {
  analysisPayload?: Step4Payload;
  invalidityPayload?: Step6Payload;
  searchPayload?: Step2Payload;
  triagePayload?: Step3Payload;
  verificationPayload?: Step7Payload;
}) {
  const changes: Array<{
    detail: string;
    id: string;
    label: string;
    tone: DossierChangeTone;
  }> = [];

  if (searchPayload?.patents_found != null) {
    changes.push({
      id: "search",
      label: `${formatNumber(searchPayload.patents_found)} patent records discovered`,
      detail:
        searchPayload.message ?? "Source search manifest is now available.",
      tone: "source",
    });
  }

  if (triagePayload?.relevant != null) {
    changes.push({
      id: "triage",
      label: `${formatNumber(triagePayload.relevant)} relevant families surfaced`,
      detail:
        triagePayload.total != null
          ? `${formatNumber(triagePayload.total)} records triaged for FTO relevance.`
          : "Relevance triage is updating.",
      tone: "triage",
    });
  }

  if (analysisPayload?.current_patent) {
    changes.push({
      id: "claim",
      label: `${analysisPayload.current_patent} claim packet active`,
      detail:
        analysisPayload.analyzed != null && analysisPayload.total != null
          ? `${formatNumber(analysisPayload.analyzed)} of ${formatNumber(
              analysisPayload.total,
            )} material patents mapped.`
          : "Material claim mapping is in progress.",
      tone: "claim",
    });
  }

  if (invalidityPayload?.assessed != null) {
    changes.push({
      id: "invalidity",
      label: `${formatNumber(invalidityPayload.assessed)} invalidity checks assessed`,
      detail: "Validity and defense notes are being attached to the dossier.",
      tone: "verification",
    });
  }

  if (verificationPayload?.checks_passed != null) {
    changes.push({
      id: "verification",
      label: `${formatNumber(verificationPayload.checks_passed)} verification checks passed`,
      detail: "Cross-checks are converging into the report draft.",
      tone: "verification",
    });
  }

  return changes.slice(-4);
}

function dossierChangeToneClass(tone: DossierChangeTone) {
  switch (tone) {
    case "source":
      return "border-info/20 bg-info/10 text-info";
    case "triage":
      return "border-brand-primary/20 bg-brand-primary/10 text-brand-primary";
    case "claim":
      return "border-warning/25 bg-warning/10 text-warning";
    default:
      return "border-success/20 bg-success/10 text-success";
  }
}

export function RunningAnalysisWorkspace({
  currentStep,
  elapsedMs,
  hasCheckpoint,
  hasLiveData,
  hasPipelineIssue = false,
  progressPct,
  progressPayloads,
  steps,
}: RunningAnalysisWorkspaceProps) {
  const safeCurrentStep = clampPipelineStep(currentStep);
  const currentPayload =
    safeCurrentStep > 0
      ? progressPayloads[safeCurrentStep as StepNumber]
      : undefined;
  const liveStepDescription = getLiveStep(steps, safeCurrentStep)?.description;
  const currentMicrocopy =
    (safeCurrentStep > 0
      ? getStepMicrocopy(safeCurrentStep, currentPayload)
      : null) ??
    currentPayload?.message ??
    liveStepDescription ??
    "Preparing the first auditable pipeline stage.";

  const searchPayload = progressPayloads[2] as Step2Payload | undefined;
  const triagePayload = progressPayloads[3] as Step3Payload | undefined;
  const analysisPayload = progressPayloads[4] as Step4Payload | undefined;
  const invalidityPayload = progressPayloads[6] as Step6Payload | undefined;
  const verificationPayload = progressPayloads[7] as Step7Payload | undefined;
  const liveResults = buildLiveResults(progressPayloads);
  const dossierChanges = buildDossierChanges({
    analysisPayload,
    invalidityPayload,
    searchPayload,
    triagePayload,
    verificationPayload,
  });
  const hasBackendProgress =
    typeof progressPct === "number" && Number.isFinite(progressPct);
  const stagePercent = hasBackendProgress
    ? Math.min(99, Math.max(0, Math.round(progressPct)))
    : Math.round(
        ((safeCurrentStep > 0 ? safeCurrentStep - 1 : 0) /
          TOTAL_PIPELINE_STEPS) *
          100,
      );
  const streamLabel = hasPipelineIssue
    ? "Stream needs attention"
    : hasLiveData
      ? "Live stream connected"
      : "Reconciling from saved run state";
  const nextArtifact = getNextArtifact(safeCurrentStep);
  const runStatusLabel = hasCheckpoint
    ? "Review paused"
    : hasPipelineIssue
      ? "Needs attention"
      : "On track";

  return (
    <Card
      className="praviar-live-dossier-field overflow-hidden"
      data-testid="live-evidence-dossier"
    >
      <CardContent className="space-y-5 p-0">
        <div className="relative isolate overflow-hidden border-b border-[var(--border-subtle)] p-5">
          <div
            className="praviar-evidence-field-pattern pointer-events-none absolute inset-0 -z-10 opacity-40"
            aria-hidden="true"
          />
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                Live evidence dossier
              </p>
              <h2 className="mt-1 type-heading-sm text-[var(--text-primary)]">
                Audit trail in progress
              </h2>
              <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                Evidence, gates, and provisional artifacts update as the agentic
                FTO run advances.
              </p>
              <p className="mt-2 text-xs font-medium leading-5 text-brand-primary">
                Synthetic research preview; not a legal clearance opinion.
              </p>
            </div>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
                hasCheckpoint
                  ? "border-warning/25 bg-warning/10 text-[var(--color-warning-badge-fg)]"
                  : hasPipelineIssue
                    ? "border-error/20 bg-error/10 text-error"
                    : "border-success/20 bg-success/10 text-[var(--color-success-badge-fg)]",
              )}
            >
              {hasCheckpoint ? (
                <PauseCircle className="h-3.5 w-3.5" aria-hidden="true" />
              ) : hasPipelineIssue ? (
                <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <Activity className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {runStatusLabel}
            </span>
          </div>
          <div className="mt-5" role="status" aria-live="polite">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="font-medium text-[var(--text-primary)]">
                {getPipelineStepLabel(safeCurrentStep)}
              </span>
              <span className="tabular-nums text-[var(--text-tertiary)]">
                {safeCurrentStep}/{TOTAL_PIPELINE_STEPS}
              </span>
            </div>
            <div
              className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--surface-hover)]"
              role="progressbar"
              aria-label="Live dossier progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={stagePercent}
            >
              <div
                className="h-full rounded-full bg-brand-primary transition-[width] duration-700 motion-reduce:transition-none"
                style={{ width: `${stagePercent}%` }}
              />
            </div>
            <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
              {currentMicrocopy}
            </p>
          </div>
        </div>

        <div className="grid gap-3 px-5">
          <section
            aria-label="Latest evidence movement"
            className="rounded-lg border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_78%,transparent)] p-4 shadow-[var(--shadow-xs)]"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                  Latest evidence movement
                </p>
                <h3 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                  What changed since launch
                </h3>
              </div>
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-brand-primary/18 bg-brand-primary/10 px-2 py-1 text-xs font-semibold text-brand-primary">
                <Radar className="h-3 w-3" aria-hidden="true" />
                Live dossier
              </span>
            </div>
            <div className="mt-3 grid gap-2">
              {dossierChanges.length > 0 ? (
                dossierChanges.map((change) => (
                  <div
                    key={change.id}
                    className="grid grid-cols-[2rem_minmax(0,1fr)] gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 px-3 py-2"
                  >
                    <span
                      className={cn(
                        "mt-0.5 flex h-7 w-7 items-center justify-center rounded-md border",
                        dossierChangeToneClass(change.tone),
                      )}
                      aria-hidden="true"
                    >
                      <GitBranch className="h-3.5 w-3.5" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-xs font-semibold text-[var(--text-primary)]">
                        {change.label}
                      </span>
                      <span className="mt-0.5 block text-xs leading-4 text-[var(--text-secondary)]">
                        {change.detail}
                      </span>
                    </span>
                  </div>
                ))
              ) : (
                <p className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                  The first source event has not arrived yet. The dossier will
                  fill as search, triage, claim mapping, and verification
                  milestones stream in.
                </p>
              )}
            </div>
          </section>

          <section
            aria-label="Artifact path"
            className="rounded-lg border border-brand-primary/15 bg-brand-primary/8 p-4 shadow-[var(--shadow-xs)]"
          >
            <div className="flex items-start gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
                <Layers3 className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                  Now assembling
                </p>
                <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                  {nextArtifact}
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  The next artifact becomes reviewable only after evidence gates
                  complete and provisional caveats remain visible.
                </p>
              </div>
            </div>
          </section>
        </div>

        <div className="grid gap-3 px-5 sm:grid-cols-2">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-base)] p-4">
            <div className="flex items-center gap-2 text-xs font-medium uppercase text-[var(--text-tertiary)]">
              <Clock3 className="h-4 w-4" aria-hidden="true" />
              Elapsed
            </div>
            <p className="mt-2 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
              {elapsedMs > 0 ? formatElapsed(elapsedMs) : "0:00"}
            </p>
          </div>
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-base)] p-4">
            <div className="flex items-center gap-2 text-xs font-medium uppercase text-[var(--text-tertiary)]">
              <Database className="h-4 w-4" aria-hidden="true" />
              Stream
            </div>
            <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">
              {streamLabel}
            </p>
          </div>
        </div>

        <div className="space-y-3 px-5">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              Evidence captured
            </h3>
            <span className="text-xs text-[var(--text-tertiary)]">
              Provisional
            </span>
          </div>
          <div className="grid gap-2">
            <EvidenceMetric
              label="Patent records"
              value={metricValue(searchPayload?.patents_found ?? null)}
              detail="retrieved from enabled sources"
            />
            <EvidenceMetric
              label="Relevant families"
              value={metricValue(triagePayload?.relevant ?? null)}
              detail={
                triagePayload?.total != null
                  ? `of ${formatNumber(triagePayload.total)} triaged`
                  : "awaiting triage"
              }
            />
            <EvidenceMetric
              label="Patent analyses"
              value={
                analysisPayload?.analyzed != null
                  ? `${formatNumber(analysisPayload.analyzed)}${
                      analysisPayload.total != null
                        ? `/${formatNumber(analysisPayload.total)}`
                        : ""
                    }`
                  : "Pending"
              }
              detail={
                analysisPayload?.current_patent ?? "material claim mapping"
              }
            />
          </div>
        </div>

        <div className="space-y-3 px-5">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Verification gates
          </h3>
          <div className="grid gap-2">
            {REVIEW_GATES.map((gate) => {
              const Icon = gate.icon;
              const status = getGateStatus({
                currentStep: safeCurrentStep,
                hasLiveData,
                stepNumber: gate.step,
                steps,
              });
              return (
                <div
                  key={gate.label}
                  className="flex items-center justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-base)] px-3 py-2"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <Icon className="h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
                    <span className="truncate text-sm text-[var(--text-secondary)]">
                      {gate.label}
                    </span>
                  </div>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium capitalize",
                      statusTone(status),
                    )}
                  >
                    {status === "completed" ? (
                      <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                    ) : (
                      <CircleDashed className="h-3 w-3" aria-hidden="true" />
                    )}
                    {status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="space-y-3 px-5">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Next expected artifact
          </h3>
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-base)] p-4">
            <div className="flex items-start gap-3">
              <FileText className="mt-0.5 h-4 w-4 flex-shrink-0 text-brand-primary" />
              <div className="min-w-0">
                <p className="font-medium text-[var(--text-primary)]">
                  {nextArtifact}
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
                  Report actions unlock after completion and reviewer-visible
                  checks.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="px-5 pb-5">
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-base)] p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <LockKeyhole className="h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
                <span className="truncate text-sm font-medium text-[var(--text-primary)]">
                  Legal output remains draft
                </span>
              </div>
              <span className="text-xs tabular-nums text-[var(--text-tertiary)]">
                {liveResults.length} live milestone
                {liveResults.length === 1 ? "" : "s"}
              </span>
            </div>
            <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
              Evidence and citations stay provisional until the run completes
              and review requirements are resolved.
            </p>
            {invalidityPayload?.assessed != null ||
            verificationPayload?.checks_passed != null ? (
              <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                {invalidityPayload?.assessed != null
                  ? `${formatNumber(invalidityPayload.assessed)} invalidity checks assessed. `
                  : ""}
                {verificationPayload?.checks_passed != null
                  ? `${formatNumber(verificationPayload.checks_passed)} verification checks passed.`
                  : ""}
              </p>
            ) : null}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function EvidenceMetric({
  detail,
  label,
  value,
}: {
  detail: string;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-base)] px-3 py-2">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-[var(--text-primary)]">
          {label}
        </p>
        <p className="truncate text-xs text-[var(--text-tertiary)]">{detail}</p>
      </div>
      <span className="flex-shrink-0 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </span>
    </div>
  );
}
