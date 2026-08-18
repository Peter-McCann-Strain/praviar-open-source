"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import {
  ArrowRight,
  FileText,
  LockKeyhole,
  SearchX,
  Share2,
  UserCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { RiskBadge } from "@/components/shared/risk-badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { getReportAccessHref } from "@/lib/report-permissions";
import { cn } from "@/lib/utils";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import type { AnalysisListItem } from "@/types/api";
import {
  formatAnalysisDate,
  getAnalysisDuration,
  getAnalysisSmiles,
  type RiskFilter,
  type SortOption,
  type StatusFilter,
} from "./helpers";

interface AnalysesPageResultsProps {
  analyses: AnalysisListItem[];
  allAnalysesCount: number;
  searchQuery: string;
  statusFilter: StatusFilter;
  riskFilter: RiskFilter;
  sortBy: SortOption;
  page: number;
  totalPages: number;
  perPage: number;
  isLoading?: boolean;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onClearFilters: () => void;
}

type SignalTone = "neutral" | "info" | "success" | "warning" | "danger";

const SIGNAL_TONE_CLASSES: Record<SignalTone, string> = {
  neutral:
    "border-[var(--border-subtle)] bg-[var(--surface-subtle)] text-[var(--text-secondary)]",
  info: "border-info/25 bg-info/10 text-[var(--color-info-badge-fg)]",
  success:
    "border-success/25 bg-success/10 text-[var(--color-success-badge-fg)]",
  warning:
    "border-warning/30 bg-warning/10 text-[var(--color-warning-badge-fg)]",
  danger: "border-error/25 bg-error/10 text-[var(--color-error-badge-fg)]",
};

const RISK_RAIL_CLASSES: Record<string, string> = {
  high: "border-l-error xl:border-l-error",
  medium: "border-l-warning xl:border-l-warning",
  low: "border-l-success xl:border-l-success",
  clear: "border-l-info xl:border-l-info",
};

function getReviewSignal(analysis: AnalysisListItem): {
  label: string;
  tone: SignalTone;
} {
  if (analysis.development_fixture) {
    return { label: "Development fixture", tone: "warning" };
  }

  const reviewStatus = analysis.review_status?.status;

  if (analysis.review_status?.is_persisted && reviewStatus) {
    if (reviewStatus === "approved") {
      return { label: "Approved", tone: "success" };
    }
    if (reviewStatus === "changes_requested") {
      return { label: "Changes requested", tone: "warning" };
    }
    if (reviewStatus === "under_review") {
      return { label: "Under review", tone: "info" };
    }
    if (reviewStatus === "pending") {
      return { label: "Review pending", tone: "warning" };
    }
  }

  if (analysis.flagged_for_review) {
    return { label: "Review flagged", tone: "warning" };
  }
  if (analysis.status === "completed") {
    return { label: "Reviewer ready", tone: "info" };
  }
  if (analysis.status === "failed") {
    return { label: "Run failed", tone: "danger" };
  }
  if (analysis.status === "cancelled") {
    return { label: "Cancelled", tone: "neutral" };
  }
  return { label: "Evidence building", tone: "neutral" };
}

function getShareSignal(analysis: AnalysisListItem): {
  label: string;
  tone: SignalTone;
} {
  if (!analysis.share_active) {
    return { label: "Private", tone: "neutral" };
  }

  const views = analysis.share_view_count ?? 0;
  const viewLabel = views === 1 ? "1 view" : `${views} views`;

  return {
    label: views > 0 ? `Shared · ${viewLabel}` : "Shared link active",
    tone: "info",
  };
}

function getEvidenceSummary(analysis: AnalysisListItem) {
  if (analysis.development_fixture) {
    return "Static development fixture; no worker execution or elapsed runtime is implied.";
  }

  const summary = analysis.executive_summary?.trim();
  if (summary) {
    return summary;
  }

  if (analysis.status === "running" || analysis.status === "pending") {
    return "Evidence packet is still being assembled from patent source, triage, and claim-review steps.";
  }
  if (analysis.status === "failed") {
    return "Run failed before a complete evidence packet could be assembled.";
  }
  if (analysis.status === "cancelled") {
    return "Run cancelled before the evidence packet was finalized.";
  }
  return "Evidence packet ready for claim review, source inspection, and report handoff.";
}

function EvidenceSignal({
  label,
  tone,
  icon,
}: {
  label: string;
  tone: SignalTone;
  icon?: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-1 text-xs font-medium leading-none",
        SIGNAL_TONE_CLASSES[tone],
      )}
      title={label}
    >
      {icon}
      <span className="truncate">{label}</span>
    </span>
  );
}

export function AnalysesPageResults({
  analyses,
  allAnalysesCount,
  searchQuery,
  statusFilter,
  riskFilter,
  sortBy,
  page,
  totalPages,
  perPage,
  isLoading = false,
  onPreviousPage,
  onNextPage,
  onClearFilters,
}: AnalysesPageResultsProps) {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const canCreateAnalysis = principal.data?.can_create_analysis === true;
  const hasFilters =
    searchQuery.trim().length > 0 ||
    statusFilter !== "all" ||
    riskFilter !== "all";
  const hasVisibleRows = analyses.length > 0;
  const rangeStart =
    allAnalysesCount === 0
      ? 0
      : Math.min((page - 1) * perPage + 1, allAnalysesCount);
  const rangeEnd =
    allAnalysesCount === 0
      ? 0
      : Math.max(
          rangeStart,
          Math.min((page - 1) * perPage + analyses.length, allAnalysesCount),
        );
  const resultSummary =
    isLoading && allAnalysesCount > 0 && !hasVisibleRows
      ? "Updating matching analyses..."
      : allAnalysesCount === 0
        ? "Showing 0 analyses"
        : `Showing ${rangeStart}-${rangeEnd} of ${allAnalysesCount} analyses`;
  const resultStatus = isLoading ? "Loading matching analyses" : resultSummary;
  const riskSort =
    sortBy === "risk-desc"
      ? "descending"
      : sortBy === "risk-asc"
        ? "ascending"
        : "none";
  const dateSort =
    sortBy === "date-desc"
      ? "descending"
      : sortBy === "date-asc"
        ? "ascending"
        : "none";

  return (
    <section
      aria-labelledby="analysis-library-results-heading"
      aria-busy={isLoading}
    >
      <div role="status" aria-live="polite" className="sr-only">
        {resultStatus}
      </div>
      <Card>
        <CardContent className="overflow-hidden p-0">
          <div className="flex flex-col gap-2 border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/42 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div className="min-w-0">
              <h2
                id="analysis-library-results-heading"
                className="text-sm font-semibold text-[var(--text-primary)]"
              >
                Evidence packets
              </h2>
              <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
                {isLoading ? "Updating matching packets..." : resultSummary}
              </p>
            </div>
            <p className="max-w-xl text-xs leading-5 text-[var(--text-tertiary)]">
              Review context, sharing state, and evidence status stay attached
              to each packet.
            </p>
          </div>
          <div className="overflow-hidden p-3 xl:overflow-x-auto xl:p-0">
            <table className="w-full min-w-0 border-separate border-spacing-0 xl:min-w-[960px] xl:table-fixed">
              <caption className="sr-only">
                Analysis Library evidence packets with status, risk, review,
                patent, sharing, duration, date, and row actions.
              </caption>
              <colgroup className="hidden xl:table-column-group">
                <col className="w-[31%]" />
                <col className="w-[9%]" />
                <col className="w-[8%]" />
                <col className="w-[16%]" />
                <col className="w-[9%]" />
                <col className="w-[8%]" />
                <col className="w-[10%]" />
                <col className="w-[9%]" />
              </colgroup>
              <thead className="hidden xl:table-header-group">
                <tr className="border-b border-[var(--border-default)]">
                  <th
                    scope="col"
                    className="bg-[var(--bg-surface)]/95 px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Compound
                  </th>
                  <th
                    scope="col"
                    className="bg-[var(--bg-surface)]/95 px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Status
                  </th>
                  <th
                    scope="col"
                    aria-sort={riskSort as "ascending" | "descending" | "none"}
                    className="bg-[var(--bg-surface)]/95 px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Risk
                  </th>
                  <th
                    scope="col"
                    className="bg-[var(--bg-surface)]/95 px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Review
                  </th>
                  <th
                    scope="col"
                    className="bg-[var(--bg-surface)]/95 px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Patents
                  </th>
                  <th
                    scope="col"
                    className="bg-[var(--bg-surface)]/95 px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Duration
                  </th>
                  <th
                    scope="col"
                    aria-sort={dateSort as "ascending" | "descending" | "none"}
                    className="bg-[var(--bg-surface)]/95 px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]"
                  >
                    Date
                  </th>
                  <th
                    scope="col"
                    className="bg-[var(--bg-surface)]/95 px-3 py-3"
                  >
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody className="block space-y-3 xl:table-row-group xl:divide-y xl:divide-[var(--border-subtle)] xl:space-y-0">
                {isLoading ? (
                  Array.from({ length: 5 }).map((_, index) => (
                    <tr
                      key={index}
                      aria-hidden="true"
                      className="block rounded-lg border border-[var(--border-default)] bg-[var(--surface-muted)]/60 p-3 xl:table-row xl:border-x-0 xl:border-y-0 xl:bg-transparent xl:p-0"
                    >
                      <td
                        colSpan={8}
                        className="block xl:table-cell xl:px-6 xl:py-4"
                      >
                        <div className="skeleton-shimmer h-12 rounded-md bg-[var(--skeleton-base)]" />
                      </td>
                    </tr>
                  ))
                ) : analyses.length > 0 ? (
                  analyses.map((analysis) => {
                    const reviewSignal = getReviewSignal(analysis);
                    const shareSignal = getShareSignal(analysis);
                    const reviewerName =
                      analysis.review_status?.reviewer_name?.trim();
                    const riskRailClass = analysis.overall_risk
                      ? RISK_RAIL_CLASSES[analysis.overall_risk]
                      : "border-l-[var(--border-subtle)] xl:border-l-[var(--border-subtle)]";
                    const rowActionLabel =
                      analysis.status === "completed"
                        ? "Open packet"
                        : "View run";
                    const rowActionHref =
                      analysis.status === "completed"
                        ? getReportAccessHref(
                            analysis.id,
                            analysis.current_user_role,
                            analysis.risk_ratings_restricted,
                          )
                        : `/analyses/${analysis.id}`;

                    return (
                      <tr
                        key={analysis.id}
                        className={cn(
                          "block rounded-lg border border-l-4 border-[var(--border-default)] bg-[var(--surface-muted)]/60 p-3 shadow-[var(--shadow-xs)] transition-colors hover:bg-[var(--surface-subtle)] focus-within:bg-[var(--surface-subtle)] xl:table-row xl:border-y-0 xl:border-r-0 xl:bg-transparent xl:p-0 xl:shadow-none xl:odd:bg-[var(--surface-card)] xl:even:bg-[var(--surface-muted)]/28 xl:hover:bg-brand-primary/[0.055] xl:focus-within:bg-brand-primary/[0.055]",
                          riskRailClass,
                        )}
                      >
                        <td className="block pb-3 xl:table-cell xl:px-5 xl:py-4 xl:align-top">
                          <Link
                            href={`/analyses/${analysis.id}`}
                            className="group block min-h-11 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
                          >
                            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)] xl:hidden">
                              Evidence packet
                            </p>
                            <p
                              className="break-words text-sm font-medium text-[var(--text-primary)] transition-colors group-hover:text-brand-primary xl:truncate"
                              title={analysis.compound_name}
                            >
                              {analysis.compound_name}
                            </p>
                            <p className="mt-0.5 break-all font-mono text-xs text-[var(--text-tertiary)] xl:truncate xl:break-normal">
                              {getAnalysisSmiles(analysis.compound_smiles)}
                            </p>
                          </Link>
                          <p className="mt-2 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                            {getEvidenceSummary(analysis)}
                          </p>
                          <div className="mt-3 flex flex-wrap gap-2 xl:hidden">
                            <EvidenceSignal
                              label={reviewSignal.label}
                              tone={reviewSignal.tone}
                              icon={<UserCheck className="h-3 w-3" />}
                            />
                            <EvidenceSignal
                              label={shareSignal.label}
                              tone={shareSignal.tone}
                              icon={
                                analysis.share_active ? (
                                  <Share2 className="h-3 w-3" />
                                ) : (
                                  <LockKeyhole className="h-3 w-3" />
                                )
                              }
                            />
                            {reviewerName ? (
                              <span className="max-w-full text-xs leading-5 text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                                Reviewer: {reviewerName}
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td className="grid grid-cols-[5.5rem_1fr] items-center gap-3 py-2 xl:table-cell xl:px-4 xl:py-4 xl:align-top">
                          <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] xl:hidden">
                            Status
                          </span>
                          <span className="min-w-0 xl:flex xl:flex-col xl:items-start xl:gap-1.5">
                            {analysis.development_fixture ? (
                              <span className="inline-flex items-center rounded-full border border-warning/30 bg-warning/10 px-2.5 py-0.5 text-xs font-medium text-[var(--color-warning-badge-fg)] shadow-[var(--shadow-xs)]">
                                Seeded preview
                              </span>
                            ) : (
                              <StatusBadge status={analysis.status} />
                            )}
                            {analysis.status === "running" && (
                              <span className="ml-2 text-xs tabular-nums text-[var(--text-tertiary)] xl:ml-0">
                                {analysis.development_fixture
                                  ? "Static · "
                                  : ""}
                                Step {analysis.current_step}/8
                              </span>
                            )}
                          </span>
                        </td>
                        <td className="grid grid-cols-[5.5rem_1fr] items-center gap-3 py-2 xl:table-cell xl:px-4 xl:py-4 xl:align-top">
                          <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] xl:hidden">
                            Risk
                          </span>
                          <span>
                            {analysis.overall_risk ? (
                              <RiskBadge
                                risk={analysis.overall_risk}
                                size="sm"
                              />
                            ) : (
                              <span className="text-xs text-[var(--text-secondary)]">
                                {analysis.risk_ratings_restricted
                                  ? "Counsel restricted"
                                  : "Risk unavailable"}
                              </span>
                            )}
                          </span>
                        </td>
                        <td className="hidden xl:table-cell xl:px-4 xl:py-4 xl:align-top">
                          <div className="flex min-w-0 flex-col items-start gap-1.5">
                            <EvidenceSignal
                              label={reviewSignal.label}
                              tone={reviewSignal.tone}
                              icon={<UserCheck className="h-3 w-3" />}
                            />
                            <EvidenceSignal
                              label={shareSignal.label}
                              tone={shareSignal.tone}
                              icon={
                                analysis.share_active ? (
                                  <Share2 className="h-3 w-3" />
                                ) : (
                                  <LockKeyhole className="h-3 w-3" />
                                )
                              }
                            />
                            {reviewerName ? (
                              <p
                                className="truncate text-xs text-[var(--text-tertiary)]"
                                title={`Reviewer: ${reviewerName}`}
                              >
                                Reviewer: {reviewerName}
                              </p>
                            ) : null}
                          </div>
                        </td>
                        <td className="grid grid-cols-[5.5rem_1fr] items-center gap-3 py-2 xl:table-cell xl:px-4 xl:py-4 xl:align-top">
                          <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] xl:hidden">
                            Patents
                          </span>
                          <div className="text-sm tabular-nums text-[var(--text-primary)]">
                            {analysis.total_patents_found}
                            {!analysis.risk_ratings_restricted &&
                              (analysis.blocking_patents_count ?? 0) > 0 && (
                                <span className="ml-1.5 text-xs text-error">
                                  ({analysis.blocking_patents_count} blocking)
                                </span>
                              )}
                          </div>
                        </td>
                        <td className="grid grid-cols-[5.5rem_1fr] items-center gap-3 py-2 xl:table-cell xl:px-4 xl:py-4 xl:align-top">
                          <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] xl:hidden">
                            Duration
                          </span>
                          <span className="text-sm tabular-nums text-[var(--text-secondary)]">
                            {getAnalysisDuration(
                              analysis.pipeline_duration_seconds,
                            )}
                          </span>
                        </td>
                        <td className="grid grid-cols-[5.5rem_1fr] items-center gap-3 py-2 xl:table-cell xl:px-4 xl:py-4 xl:align-top">
                          <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] xl:hidden">
                            Date
                          </span>
                          <div className="min-w-0">
                            <span className="block whitespace-nowrap text-sm text-[var(--text-secondary)]">
                              {formatAnalysisDate(analysis.created_at)}
                            </span>
                            <span className="mt-0.5 block whitespace-nowrap text-xs text-[var(--text-tertiary)] xl:mt-1">
                              Updated {formatAnalysisDate(analysis.updated_at)}
                            </span>
                          </div>
                        </td>
                        <td className="block pt-3 xl:table-cell xl:px-3 xl:py-4 xl:align-top">
                          <Button
                            asChild
                            variant="ghost"
                            size="sm"
                            className="min-h-11 w-full justify-between gap-1 text-xs text-[var(--text-tertiary)] hover:text-brand-primary xl:w-auto xl:justify-center"
                          >
                            <Link
                              href={rowActionHref}
                              aria-label={`${rowActionLabel} for ${analysis.compound_name}`}
                            >
                              <FileText className="h-3.5 w-3.5 xl:hidden" />
                              <span className="xl:hidden">
                                {rowActionLabel}
                              </span>
                              <span className="hidden xl:inline">
                                {analysis.status === "completed"
                                  ? "Open"
                                  : "View"}
                              </span>
                              <ArrowRight className="h-3 w-3" />
                            </Link>
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr className="block xl:table-row">
                    <td
                      colSpan={8}
                      className="block px-4 py-14 text-center xl:table-cell xl:px-6 xl:py-16"
                    >
                      <EmptyState
                        icon={hasFilters ? SearchX : FileText}
                        title={
                          hasFilters
                            ? "No analyses match your filters"
                            : "No analyses yet"
                        }
                        description={
                          hasFilters
                            ? "Adjust your search, risk, or status filters to restore the analysis index."
                            : "Submit a compound to get a structured patent landscape report with risk assessment."
                        }
                        action={
                          hasFilters
                            ? {
                                label: "Clear filters",
                                onClick: onClearFilters,
                              }
                            : canCreateAnalysis
                              ? {
                                  label: "Start your first analysis",
                                  href: "/analyses/new",
                                }
                              : undefined
                        }
                        contextItems={
                          hasFilters
                            ? [
                                "Filters applied",
                                "Library remains available",
                                "Clear to recover",
                              ]
                            : [
                                "No private records yet",
                                "Evidence packet workflow",
                                "Counsel review workflow",
                              ]
                        }
                        className="mx-auto max-w-2xl"
                      />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-3 text-sm text-[var(--text-secondary)] sm:flex-row sm:items-center sm:justify-between">
        <span className="tabular-nums">{resultSummary}</span>
        {totalPages > 1 ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--text-tertiary)] tabular-nums">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              aria-label="Previous page"
              disabled={page <= 1}
              onClick={onPreviousPage}
              className="min-h-11"
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              aria-label="Next page"
              disabled={page >= totalPages}
              onClick={onNextPage}
              className="min-h-11"
            >
              Next
            </Button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
