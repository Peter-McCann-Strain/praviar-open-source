"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Clock3,
  Database,
  FileWarning,
  FileText,
  Loader2,
  LockKeyhole,
  SearchX,
  Scale,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type ReportStatusVariant =
  | "auth"
  | "loading"
  | "validation"
  | "forbidden"
  | "temporary"
  | "missing";

interface ReportStatusStateProps {
  variant: ReportStatusVariant;
  analysisStatus?: string | null;
  analysisId?: string;
  analysisUpdatedAt?: string | null;
  currentStep?: number | null;
  detail?: string | null;
  onRetry?: () => void;
  totalPatentsFound?: number | null;
  className?: string;
}

type ReportStatusTone = "default" | "warning" | "error";

const REPORT_STATUS_COPY: Record<
  ReportStatusVariant,
  {
    icon: LucideIcon;
    tone: ReportStatusTone;
    eyebrow: string;
    title: string;
    description: string;
    contextItems: string[];
    recoveryTitle: string;
    recoveryBody: string;
  }
> = {
  auth: {
    icon: LockKeyhole,
    tone: "default",
    eyebrow: "Report access",
    title: "Checking report access",
    description:
      "Confirming your authenticated workspace session before any report evidence or review controls are shown.",
    contextItems: [
      "Session check in progress",
      "No report content exposed",
      "Actions open after access",
    ],
    recoveryTitle: "Preparing a private workspace",
    recoveryBody:
      "Praviar opens report evidence only after your private team session is confirmed.",
  },
  loading: {
    icon: Loader2,
    tone: "default",
    eyebrow: "Report workspace",
    title: "Loading report workspace",
    description:
      "Retrieving the verified FTO packet, evidence rail, and review controls for this analysis.",
    contextItems: [
      "Workspace locked while loading",
      "No report content shown yet",
      "Actions open after load",
    ],
    recoveryTitle: "Preparing a governed view",
    recoveryBody:
      "Export, share, review, and chat actions stay unavailable until the report package is ready.",
  },
  validation: {
    icon: FileWarning,
    tone: "error",
    eyebrow: "Report package check",
    title: "Report package could not be verified",
    description:
      "The report package did not pass Praviar's readiness checks, so the workspace stayed closed.",
    contextItems: [
      "Report rendering blocked",
      "Existing data unchanged",
      "Support review required",
    ],
    recoveryTitle: "No FTO conclusion is shown from this state",
    recoveryBody:
      "Retry after support confirms the report package, or share the support reference with the team handling this analysis.",
  },
  forbidden: {
    icon: LockKeyhole,
    tone: "warning",
    eyebrow: "Report access",
    title: "Report access unavailable",
    description:
      "Your current team session does not have permission to view this report. Ask an administrator to confirm access for this analysis.",
    contextItems: [
      "Authenticated workspace",
      "Team-scoped access",
      "No report content exposed",
    ],
    recoveryTitle: "Request access through your workspace owner",
    recoveryBody:
      "This view does not reveal report evidence, export controls, or review actions until access is confirmed.",
  },
  temporary: {
    icon: AlertTriangle,
    tone: "error",
    eyebrow: "Report load",
    title: "Report temporarily unavailable",
    description:
      "The report service did not return a usable workspace. Try a fresh load; analysis data and review records remain unchanged.",
    contextItems: [
      "No report edits made",
      "Workspace actions paused",
      "Retry recommended",
    ],
    recoveryTitle: "Refresh the report request",
    recoveryBody:
      "A retry asks for a fresh report response without changing the underlying analysis.",
  },
  missing: {
    icon: SearchX,
    tone: "warning",
    eyebrow: "Report lookup",
    title: "Report not available",
    description:
      "We could not find a report for this analysis yet. Return to the analysis once generation has completed or confirm the analysis ID.",
    contextItems: [
      "No report content loaded",
      "Workspace actions disabled",
      "Analysis ID checked",
    ],
    recoveryTitle: "Confirm report generation",
    recoveryBody:
      "The report workspace opens after a completed analysis has a verified report response.",
  },
};

export function ReportStatusState({
  variant,
  analysisStatus,
  analysisId,
  analysisUpdatedAt,
  currentStep,
  detail,
  onRetry,
  totalPatentsFound,
  className,
}: ReportStatusStateProps) {
  const meta =
    variant === "missing"
      ? getMissingReportCopy(analysisStatus)
      : REPORT_STATUS_COPY[variant];
  const titleId = `report-status-${variant}-title`;
  const isLoading = variant === "loading";
  const isPending = variant === "auth" || isLoading;
  const diagnosticReference = formatDiagnosticReference(detail);
  const showRecoveryPackage = !isPending && variant !== "forbidden";

  return (
    <OperationalStatusFrame
      actionLabel="Retry report load"
      aiBrief={getReportRecoveryBrief({
        canRetry: Boolean(onRetry),
        variant,
        analysisStatus,
      })}
      className={["mx-auto w-full max-w-[90rem]", className]
        .filter(Boolean)
        .join(" ")}
      contextItems={meta.contextItems}
      dataTestId={`report-status-${variant}`}
      description={meta.description}
      eyebrow={meta.eyebrow}
      headingLevel={1}
      icon={meta.icon}
      isLoading={isLoading}
      isPending={isPending}
      onRetry={onRetry}
      recoveryBody={meta.recoveryBody}
      recoveryExtra={
        showRecoveryPackage ? (
          <>
            <ReportRecoverySafeguard />
            <ReportRecoverySnapshot
              analysisStatus={analysisStatus}
              analysisUpdatedAt={analysisUpdatedAt}
              currentStep={currentStep}
              totalPatentsFound={totalPatentsFound}
            />
            {diagnosticReference ? (
              <details className="mt-4 min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-3">
                <summary className="cursor-pointer text-sm font-medium text-[var(--text-primary)]">
                  View support reference
                </summary>
                <div className="praviar-code-surface mt-3 rounded-lg p-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                    Support reference
                  </p>
                  <p className="mt-2 break-words text-xs leading-5 text-[var(--text-secondary)]">
                    {diagnosticReference}
                  </p>
                </div>
              </details>
            ) : null}
          </>
        ) : null
      }
      recoveryTitle={meta.recoveryTitle}
      secondaryAction={
        analysisId && !isPending ? (
          <Button
            asChild
            variant="secondary"
            className="min-h-11 w-full gap-2 sm:w-auto"
          >
            <Link href={`/analyses/${analysisId}`}>
              <FileText className="h-4 w-4" aria-hidden="true" />
              Open analysis status
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </Button>
        ) : null
      }
      title={meta.title}
      titleId={titleId}
      tone={meta.tone}
    />
  );
}

function getReportRecoveryBrief({
  canRetry,
  variant,
  analysisStatus,
}: {
  canRetry: boolean;
  variant: ReportStatusVariant;
  analysisStatus?: string | null;
}) {
  if (variant === "auth" || variant === "loading") {
    return undefined;
  }

  if (variant === "forbidden") {
    return {
      items: [
        "Keep report content, exports, share controls, and review actions hidden until access is confirmed.",
        "Ask a workspace administrator to verify your team permission for this analysis.",
        "Use only the access state shown here; no private report details are disclosed.",
      ],
      note: "This access state does not confirm whether report artifacts or reviewer records exist.",
    };
  }

  if (variant === "missing" && analysisStatus === "running") {
    return {
      items: [
        "Track pipeline progress from the analysis status view before opening the report workspace.",
        "Keep export, share, review, and chat controls paused until a verified report package exists.",
        "Use the last saved analysis status as the source of truth while report generation continues.",
      ],
      note: "No legal conclusion changed by waiting for report readiness.",
    };
  }

  if (
    variant === "missing" &&
    (analysisStatus === "failed" || analysisStatus === "cancelled")
  ) {
    return {
      items: [
        "Open the analysis status to inspect the last completed pipeline step.",
        "Preserve available search and triage context before starting any rerun.",
        "Start a new analysis only after confirming the failure or cancellation cause.",
      ],
      note: "Recovery guidance does not create or alter an FTO conclusion.",
    };
  }

  if (variant === "validation") {
    return {
      items: [
        "Keep partial or schema-invalid report content hidden from the workspace.",
        "Use the support reference to trace readiness issues without exposing secrets.",
        canRetry
          ? "Retry only after the report package can be verified against the expected contract."
          : "Reload only after the report package can be verified against the expected contract.",
      ],
      note: "No legal conclusion is shown from a package that failed readiness checks.",
    };
  }

  return {
    items: [
      "Keep preserved report inputs, evidence references, and reviewer records unchanged.",
      canRetry
        ? "Retry requests a fresh report response without mutating the underlying analysis."
        : "A fresh report response can be requested when a retry control is available.",
      "Open analysis status if generation, failure, or readiness still needs review.",
    ],
    note: "No legal conclusion changed from this recovery state.",
  };
}

function ReportRecoverySafeguard() {
  return (
    <section
      aria-label="Report recovery safeguard"
      className="mt-4 rounded-lg border border-warning/25 bg-warning/10 p-3"
    >
      <div className="flex min-w-0 items-start gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-warning/25 bg-warning/10 text-warning">
          <Scale className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            No legal conclusion changed
          </p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            Automated recovery does not modify findings, risk ratings, reviewer
            decisions, or legal-boundary language.
          </p>
        </div>
      </div>
    </section>
  );
}

function ReportRecoverySnapshot({
  analysisStatus,
  analysisUpdatedAt,
  currentStep,
  totalPatentsFound,
}: {
  analysisStatus?: string | null;
  analysisUpdatedAt?: string | null;
  currentStep?: number | null;
  totalPatentsFound?: number | null;
}) {
  const facts = [
    analysisStatus
      ? {
          icon: ShieldCheck,
          label: "Analysis status",
          value: formatStatusLabel(analysisStatus),
        }
      : null,
    typeof currentStep === "number"
      ? {
          icon: Clock3,
          label: "Last pipeline step",
          value: `Step ${Math.max(0, currentStep)} of 8`,
        }
      : null,
    typeof totalPatentsFound === "number"
      ? {
          icon: Database,
          label: "Evidence count",
          value: `${totalPatentsFound.toLocaleString()} patents found`,
        }
      : null,
  ].filter((fact): fact is { icon: LucideIcon; label: string; value: string } =>
    Boolean(fact),
  );

  if (facts.length === 0 && !analysisUpdatedAt) {
    return null;
  }

  return (
    <section
      aria-label="Preserved analysis snapshot"
      className="mt-4 rounded-lg border border-brand-primary/15 bg-brand-primary/5 p-3"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
            Evidence preserved
          </p>
          {analysisUpdatedAt ? (
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              Latest saved snapshot: {formatDateTime(analysisUpdatedAt)}
            </p>
          ) : null}
        </div>
        <Badge variant="success" className="w-fit">
          Auto-saved
        </Badge>
      </div>

      {facts.length > 0 ? (
        <dl className="mt-3 grid gap-2 sm:grid-cols-3">
          {facts.map((fact) => {
            const Icon = fact.icon;

            return (
              <div
                key={fact.label}
                className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-3"
              >
                <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                  <Icon
                    className="h-3.5 w-3.5 text-brand-primary"
                    aria-hidden="true"
                  />
                  {fact.label}
                </dt>
                <dd className="mt-1 break-words text-sm font-semibold text-[var(--text-primary)]">
                  {fact.value}
                </dd>
              </div>
            );
          })}
        </dl>
      ) : null}
    </section>
  );
}

function formatStatusLabel(status: string): string {
  return status
    .split(/[_-]+/u)
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Saved timestamp unavailable";
  }

  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function formatDiagnosticReference(detail?: string | null): string | null {
  if (!detail) {
    return null;
  }

  const normalized = detail.replace(/\s+/gu, " ").trim();
  if (!normalized) {
    return null;
  }

  return `Report validation reference ${hashDiagnosticReference(normalized)}`;
}

function hashDiagnosticReference(value: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36).toUpperCase().padStart(7, "0");
}

function getMissingReportCopy(
  analysisStatus?: string | null,
): (typeof REPORT_STATUS_COPY)["missing"] {
  if (analysisStatus === "pending" || analysisStatus === "running") {
    return {
      ...REPORT_STATUS_COPY.missing,
      eyebrow: "Report preparation",
      title: "Report is still being prepared",
      description:
        "This analysis has not produced a verified report yet. Return once report preparation completes.",
      contextItems: [
        "Report preparation in progress",
        "No report content loaded",
        "Workspace actions disabled",
      ],
      recoveryTitle: "Track generation from the analysis view",
      recoveryBody:
        "The report workspace opens after the analysis produces a verified report package.",
    };
  }

  if (analysisStatus === "failed" || analysisStatus === "cancelled") {
    return {
      ...REPORT_STATUS_COPY.missing,
      eyebrow: "Report preparation",
      title: "Report was not produced",
      description:
        "This analysis did not produce a verified report package. Review the analysis status before rerunning the workflow.",
      contextItems: [
        "No verified report",
        "No report content loaded",
        "Workspace actions disabled",
      ],
      recoveryTitle: "Review the analysis outcome",
      recoveryBody:
        "The report workspace remains closed until a completed analysis has a verified report package.",
    };
  }

  return REPORT_STATUS_COPY.missing;
}
