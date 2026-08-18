"use client";

import {
  AlertTriangle,
  CheckCircle,
  FileWarning,
  RefreshCw,
  Scale,
  ShieldCheck,
  type LucideIcon,
  XCircle,
} from "lucide-react";
import type { FTOReport } from "@praviar/shared-types";
import { AIRecoveryBrief } from "@/components/shared/ai-recovery-brief";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function AnalysisFailuresCard({
  analysisFailures,
  auditFailureCount,
  coverageFailureCount,
  evidenceSufficientForClearance,
}: {
  analysisFailures: NonNullable<FTOReport["analysis_failures"]>;
  auditFailureCount?: number;
  coverageFailureCount?: number;
  evidenceSufficientForClearance?: boolean;
}) {
  const metadataCounts = [
    analysisFailures.length,
    auditFailureCount,
    coverageFailureCount,
  ].filter((count): count is number => typeof count === "number");
  const hasMetadataInconsistency = new Set(metadataCounts).size > 1;
  const reportedFailureCount = Math.max(
    ...metadataCounts,
    analysisFailures.length,
  );
  const hasRecoveryWarning =
    reportedFailureCount > 0 || hasMetadataInconsistency;
  const recoverableCount = analysisFailures.filter(
    (failure) => failure.recoverable,
  ).length;
  const needsReviewCount = Math.max(reportedFailureCount - recoverableCount, 0);

  return (
    <Card id="analysis-failures" className="overflow-hidden">
      <CardHeader>
        <div className="flex items-center gap-2">
          {hasRecoveryWarning ? (
            <XCircle className="h-5 w-5 text-error" />
          ) : (
            <CheckCircle className="h-5 w-5 text-success" />
          )}
          <CardTitle className="text-sm">Analysis Failures</CardTitle>
          {reportedFailureCount > 0 && (
            <Badge variant="destructive" className="text-xs ml-auto">
              {reportedFailureCount}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {!hasRecoveryWarning ? (
          <div className="rounded-lg bg-success/5 border border-success/10 p-4 text-center">
            <p className="text-sm text-success">
              All patents processed successfully
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <section
              aria-label="Analysis failure recovery impact"
              className="rounded-lg border border-warning/25 bg-warning/5 p-3 sm:p-4"
            >
              <div className="flex items-center gap-3 sm:hidden">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-warning/25 bg-warning/10 text-warning">
                  <AlertTriangle className="h-5 w-5" aria-hidden="true" />
                </span>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-warning">
                  Recovery impact
                </p>
              </div>
              <div className="mt-3 flex min-w-0 items-start gap-3 sm:mt-0">
                <span className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-warning/25 bg-warning/10 text-warning sm:flex">
                  <AlertTriangle className="h-5 w-5" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <p className="hidden text-xs font-semibold uppercase tracking-[0.14em] text-warning sm:block">
                    Recovery impact
                  </p>
                  <h3 className="text-base font-semibold leading-6 text-[var(--text-primary)] sm:mt-1 sm:text-lg sm:leading-7">
                    {hasMetadataInconsistency
                      ? "Report metadata needs verification"
                      : evidenceSufficientForClearance === false
                        ? "Report is screening-only until gaps are reviewed"
                        : "Report remains usable with caveats"}
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                    {hasMetadataInconsistency
                      ? "Failure counts do not match across report metadata. Verify the affected patent set before relying on coverage conclusions."
                      : "These patents were excluded from automated analysis outputs. Review them before relying on affected clearance or exclusion language."}
                  </p>
                </div>
              </div>

              <dl className="mt-4 grid gap-3 sm:grid-cols-3">
                <FailureMetric
                  icon={FileWarning}
                  label="Affected patents"
                  value={`${reportedFailureCount}`}
                  detail="Excluded from automated findings"
                  tone="error"
                />
                <FailureMetric
                  icon={RefreshCw}
                  label="Recoverable"
                  value={`${recoverableCount}`}
                  detail="Retry candidates"
                  tone="warning"
                />
                <FailureMetric
                  icon={Scale}
                  label="Needs review"
                  value={`${needsReviewCount}`}
                  detail="Manual triage required"
                  tone="error"
                />
              </dl>
            </section>

            {hasMetadataInconsistency ? (
              <section
                aria-label="Report metadata inconsistency"
                className="rounded-lg border border-error/25 bg-error/5 p-3"
              >
                <div className="flex min-w-0 gap-2">
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 shrink-0 text-error"
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      Report metadata inconsistency
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                      Failure counts differ between report rows, decision audit,
                      or coverage summary. Treat coverage as needing
                      verification until the report package is refreshed.
                    </p>
                  </div>
                </div>
              </section>
            ) : null}

            <AIRecoveryBrief
              items={[
                "Prioritize non-recoverable patents for reviewer triage before counsel handoff.",
                "Retry recoverable source or timeout failures without changing existing report findings.",
                "Keep affected patent IDs attached to export packets and follow-up analysis.",
              ]}
              note="No legal conclusion changed from this recovery guidance."
            />

            <section
              aria-label="Analysis failure safeguard"
              className="rounded-lg border border-brand-primary/15 bg-brand-primary/5 p-3"
            >
              <div className="flex min-w-0 gap-2">
                <ShieldCheck
                  className="mt-0.5 h-4 w-4 shrink-0 text-brand-primary"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    No legal conclusion changed
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                    Recovery status describes processing coverage only; it does
                    not edit findings, risk ratings, or reviewer decisions.
                  </p>
                </div>
              </div>
            </section>

            {analysisFailures.length === 0 ? (
              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] p-4 text-sm leading-6 text-[var(--text-secondary)]">
                Failure details are not present in this report payload. Use the
                decision audit and coverage summary counts as the current
                recovery source of truth.
              </div>
            ) : (
              <div
                className="overflow-x-auto rounded-lg border border-[var(--border-subtle)] focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
                role="region"
                tabIndex={0}
                aria-label="Analysis failures horizontal scroll area"
              >
                <table className="w-full min-w-[760px] text-sm">
                  <caption className="sr-only">
                    Affected patents with pipeline step, safe failure category,
                    and recovery status
                  </caption>
                  <thead>
                    <tr className="border-b border-[var(--border-default)] bg-[var(--surface-muted)]">
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]"
                      >
                        Patent ID
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]"
                      >
                        Pipeline step
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]"
                      >
                        Safe category
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]"
                      >
                        Recovery note
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]"
                      >
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-default)]">
                    {analysisFailures.map((failure) => {
                      const category = getFailureCategory(failure);

                      return (
                        <tr
                          key={`${failure.patent_id}-${failure.step}-${failure.error_type}`}
                          className={cn(
                            failure.recoverable ? "bg-warning/5" : "bg-error/5",
                          )}
                        >
                          <td className="px-4 py-3 font-mono text-xs text-[var(--text-primary)]">
                            {failure.patent_id}
                          </td>
                          <td className="px-4 py-3 text-[var(--text-secondary)]">
                            {formatPipelineStep(failure.step)}
                          </td>
                          <td className="px-4 py-3 text-[var(--text-secondary)]">
                            <Badge
                              variant={category.variant}
                              className="text-xs"
                            >
                              {category.label}
                            </Badge>
                          </td>
                          <td className="max-w-[24rem] px-4 py-3 text-xs leading-5 text-[var(--text-secondary)]">
                            {category.note}
                          </td>
                          <td className="px-4 py-3">
                            {failure.recoverable ? (
                              <Badge
                                variant="warning"
                                className="gap-1 text-xs"
                              >
                                <RefreshCw
                                  className="h-3.5 w-3.5"
                                  aria-hidden="true"
                                />
                                Recoverable
                              </Badge>
                            ) : (
                              <Badge
                                variant="destructive"
                                className="gap-1 text-xs"
                              >
                                <XCircle
                                  className="h-3.5 w-3.5"
                                  aria-hidden="true"
                                />
                                Needs review
                              </Badge>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

type FailureMetricTone = "error" | "warning";

function FailureMetric({
  detail,
  icon: Icon,
  label,
  tone,
  value,
}: {
  detail: string;
  icon: LucideIcon;
  label: string;
  tone: FailureMetricTone;
  value: string;
}) {
  const toneClass = tone === "error" ? "text-error" : "text-warning";

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/75 p-3">
      <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        <Icon className={`h-3.5 w-3.5 ${toneClass}`} aria-hidden="true" />
        {label}
      </dt>
      <dd className="mt-2 text-2xl font-semibold leading-none text-[var(--text-primary)]">
        {value}
      </dd>
      <dd className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
        {detail}
      </dd>
    </div>
  );
}

function formatPipelineStep(step: string): string {
  return step
    .replace(/^step(\d+)_/i, "Step $1: ")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function getFailureCategory(
  failure: NonNullable<FTOReport["analysis_failures"]>[number],
): {
  label: string;
  note: string;
  variant: "secondary" | "warning" | "destructive";
} {
  const errorText =
    `${failure.error_type} ${failure.error_message}`.toLowerCase();

  if (errorText.includes("timeout")) {
    return {
      label: "Source timeout",
      note: "External evidence retrieval did not finish; retry the source-backed step before relying on this patent's coverage.",
      variant: "warning",
    };
  }

  if (errorText.includes("schema") || errorText.includes("validation")) {
    return {
      label: "Validation issue",
      note: "Generated analysis failed report-shape checks and was excluded from findings for this patent.",
      variant: "destructive",
    };
  }

  if (
    errorText.includes("rate") ||
    errorText.includes("quota") ||
    errorText.includes("503") ||
    errorText.includes("unavailable")
  ) {
    return {
      label: "Source unavailable",
      note: "A source dependency was unavailable; preserve this patent for source refresh or reviewer triage.",
      variant: "warning",
    };
  }

  return {
    label: "Processing issue",
    note: "Processing did not complete for this patent; details are preserved for support review.",
    variant: failure.recoverable ? "warning" : "secondary",
  };
}
