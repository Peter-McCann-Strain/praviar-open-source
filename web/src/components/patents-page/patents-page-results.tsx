import Link from "next/link";
import { ArrowRight, FileText, SearchX } from "lucide-react";
import type { PatentItem } from "@/hooks/use-patents";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { RiskBadge } from "@/components/shared/risk-badge";
import { cn } from "@/lib/utils";
import {
  canAccessFullReport,
  getReportAccessHrefWithQuery,
} from "@/lib/report-permissions";
import type { RiskLevel } from "@praviar/shared-types";
import {
  type ExpiryTone,
  extractJurisdiction,
  getPatentExpirySignal,
  normalizeRiskLevel,
  type RiskFilter,
} from "./helpers";

interface PatentsPageResultsProps {
  patents: PatentItem[];
  total: number;
  page: number;
  perPage: number;
  totalPages: number;
  isLoading?: boolean;
  searchQuery: string;
  riskFilter: RiskFilter;
  onClearFilters: () => void;
  onPrevious: () => void;
  onNext: () => void;
  isUpdating?: boolean;
  currentUserRole?: string | null;
  riskRatingsRestricted?: boolean;
  canViewRisk?: boolean;
}

export function PatentsPageResults({
  patents,
  total,
  page,
  perPage,
  totalPages,
  isLoading = false,
  searchQuery,
  riskFilter,
  onClearFilters,
  onPrevious,
  onNext,
  isUpdating = false,
  currentUserRole,
  riskRatingsRestricted,
  canViewRisk = false,
}: PatentsPageResultsProps) {
  const hasActiveFilters = searchQuery.length > 0 || riskFilter !== "all";
  const hasVisibleRows = patents.length > 0;
  const rangeStart =
    total === 0 ? 0 : Math.min((page - 1) * perPage + 1, total);
  const rangeEnd =
    total === 0
      ? 0
      : Math.max(rangeStart, Math.min(total, rangeStart + patents.length - 1));
  const resultsLabel =
    (isLoading || isUpdating) && total > 0 && !hasVisibleRows
      ? "Updating matching patents"
      : total > 0
        ? `Showing ${rangeStart}-${rangeEnd} of ${total.toLocaleString()} patents`
        : isLoading
          ? "Loading matching patents"
          : "Showing 0 patents";
  const fullReportAllowed = canAccessFullReport(
    currentUserRole,
    riskRatingsRestricted,
  );
  const columnCount = canViewRisk ? 7 : 6;

  return (
    <>
      <p className="sr-only" role="status" aria-live="polite">
        {resultsLabel}
      </p>
      <Card aria-busy={isLoading || isUpdating ? true : undefined}>
        <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/50 px-4 py-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase text-[var(--text-tertiary)]">
                Evidence records
              </p>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                {resultsLabel}
                {isUpdating && hasVisibleRows ? " · updating result page" : ""}
              </p>
            </div>
          </div>
        </div>
        <CardContent
          aria-label="Patent evidence records horizontal scroll area"
          className="overflow-hidden p-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] min-[1440px]:overflow-x-auto min-[1440px]:p-0"
          role="region"
          tabIndex={0}
        >
          <table
            className={cn(
              "w-full min-w-0",
              canViewRisk
                ? "min-[1440px]:min-w-[920px]"
                : "min-[1440px]:min-w-[820px]",
            )}
          >
            <caption className="sr-only">
              {canViewRisk
                ? "Patent evidence records with risk, CPC, assignee, expiry, jurisdiction, and report links."
                : "Patent evidence records with CPC, assignee, expiry, jurisdiction, and governed report links."}
            </caption>
            <thead className="hidden min-[1440px]:sticky min-[1440px]:top-0 min-[1440px]:z-10 min-[1440px]:table-header-group">
              <tr className="praviar-glass-strip border-b border-[var(--border-default)]">
                <th
                  scope="col"
                  className="px-4 py-2.5 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Patent identity
                </th>
                <th
                  scope="col"
                  className="px-4 py-2.5 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Title & CPC
                </th>
                {canViewRisk ? (
                  <th
                    scope="col"
                    className="px-4 py-2.5 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                  >
                    Risk
                  </th>
                ) : null}
                <th
                  scope="col"
                  className="px-4 py-2.5 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Assignee
                </th>
                <th
                  scope="col"
                  className="px-4 py-2.5 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Expiry
                </th>
                <th
                  scope="col"
                  className="px-4 py-2.5 text-left text-xs font-semibold uppercase text-[var(--text-tertiary)]"
                >
                  Jurisdiction
                </th>
                <th scope="col" className="px-4 py-2.5">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="block space-y-3 min-[1440px]:table-row-group min-[1440px]:divide-y min-[1440px]:divide-[var(--border-subtle)] min-[1440px]:space-y-0">
              {isLoading && patents.length === 0 ? (
                <tr className="block min-[1440px]:table-row">
                  <td
                    colSpan={columnCount}
                    className="block px-4 py-14 text-center min-[1440px]:table-cell min-[1440px]:px-6 min-[1440px]:py-16"
                  >
                    <FileText className="mx-auto mb-3 h-10 w-10 text-[var(--text-disabled)]" />
                    <p className="text-[var(--text-secondary)]">
                      Loading matching patents
                    </p>
                    <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                      Keeping the patent controls available while the library
                      query updates.
                    </p>
                  </td>
                </tr>
              ) : patents.length > 0 ? (
                patents.map((patent) => {
                  const supportedRisk = canViewRisk
                    ? normalizeRiskLevel(patent.risk_level)
                    : null;
                  const expiry = getPatentExpirySignal(patent.expiry_date);

                  return (
                    <tr
                      key={patent.id}
                      className={cn(
                        "block rounded-lg border border-l-[3px] bg-[var(--surface-muted)]/60 p-3 shadow-[var(--shadow-xs)] transition-colors hover:bg-[var(--surface-subtle)] min-[1440px]:table-row min-[1440px]:border-x-0 min-[1440px]:border-b-0 min-[1440px]:border-r-0 min-[1440px]:bg-transparent min-[1440px]:p-0 min-[1440px]:shadow-none",
                        getRiskRowClass(supportedRisk),
                      )}
                    >
                      <td className="block pb-3 min-[1440px]:table-cell min-[1440px]:px-4 min-[1440px]:py-3">
                        <div className="min-w-0">
                          <div className="min-w-0">
                            <p className="break-all font-mono text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                              {patent.patent_number}
                            </p>
                            <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                              {patent.compound_name}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="block py-2 min-[1440px]:table-cell min-[1440px]:max-w-sm min-[1440px]:px-4 min-[1440px]:py-3">
                        <span className="mb-1 block text-xs font-medium uppercase text-[var(--text-tertiary)] min-[1440px]:hidden">
                          Title & CPC
                        </span>
                        <p className="line-clamp-2 break-words text-sm font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
                          {patent.title || "\u2014"}
                        </p>
                        <PatentCpcChips codes={patent.cpc_codes} />
                      </td>
                      {canViewRisk ? (
                        <td className="grid grid-cols-[6rem_1fr] items-center gap-3 py-2 min-[1440px]:table-cell min-[1440px]:px-4 min-[1440px]:py-3">
                          <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] min-[1440px]:hidden">
                            Risk
                          </span>
                          <span>
                            {supportedRisk ? (
                              <RiskBadge risk={supportedRisk} size="sm" />
                            ) : (
                              <span className="text-xs text-[var(--text-disabled)]">
                                &mdash;
                              </span>
                            )}
                          </span>
                        </td>
                      ) : null}
                      <td className="grid grid-cols-[6rem_1fr] items-start gap-3 py-2 min-[1440px]:table-cell min-[1440px]:px-4 min-[1440px]:py-3">
                        <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] min-[1440px]:hidden">
                          Assignee
                        </span>
                        <span className="min-w-0 break-words text-sm text-[var(--text-secondary)]">
                          {patent.assignee || "\u2014"}
                        </span>
                      </td>
                      <td className="grid grid-cols-[6rem_1fr] items-start gap-3 py-2 min-[1440px]:table-cell min-[1440px]:px-4 min-[1440px]:py-3">
                        <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] min-[1440px]:hidden">
                          Expiry
                        </span>
                        <PatentExpirySignal signal={expiry} />
                      </td>
                      <td className="grid grid-cols-[6rem_1fr] items-center gap-3 py-2 min-[1440px]:table-cell min-[1440px]:px-4 min-[1440px]:py-3">
                        <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] min-[1440px]:hidden">
                          Jurisdiction
                        </span>
                        <span className="font-mono text-sm font-semibold text-[var(--text-secondary)]">
                          {extractJurisdiction(patent.patent_number)}
                        </span>
                      </td>
                      <td className="block pt-3 min-[1440px]:table-cell min-[1440px]:px-4 min-[1440px]:py-3">
                        <Button
                          asChild
                          variant="ghost"
                          size="sm"
                          className="min-h-11 w-full justify-between gap-1 text-xs text-[var(--text-tertiary)] hover:text-brand-primary min-[1440px]:w-auto min-[1440px]:justify-center"
                        >
                          <Link
                            href={getPatentReportHref(
                              patent,
                              currentUserRole,
                              riskRatingsRestricted,
                            )}
                            aria-label={`Open patent evidence for ${patent.patent_number}`}
                          >
                            {fullReportAllowed ? "Open report" : "Open summary"}
                            <ArrowRight
                              className="h-3 w-3"
                              aria-hidden="true"
                            />
                          </Link>
                        </Button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr className="block min-[1440px]:table-row">
                  <td
                    colSpan={columnCount}
                    className="block px-4 py-14 text-center min-[1440px]:table-cell min-[1440px]:px-6 min-[1440px]:py-16"
                  >
                    <EmptyState
                      icon={hasActiveFilters ? SearchX : FileText}
                      title={
                        hasActiveFilters
                          ? "No patents match your filters"
                          : "No patents found"
                      }
                      description={
                        hasActiveFilters
                          ? canViewRisk
                            ? "Try adjusting your search or risk filter to restore the patent evidence index."
                            : "Try adjusting your search to restore the patent evidence index."
                          : "Verified patent evidence will appear here once reports publish it."
                      }
                      action={
                        hasActiveFilters
                          ? { label: "Clear filters", onClick: onClearFilters }
                          : undefined
                      }
                      contextItems={
                        hasActiveFilters
                          ? [
                              "Filters applied",
                              "Patent index available",
                              "Clear to recover",
                            ]
                          : [
                              "Awaiting report evidence",
                              "Patent rows stay scoped",
                              "Published reports populate this view",
                            ]
                      }
                      className="mx-auto max-w-2xl"
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-3 text-sm text-[var(--text-secondary)] sm:flex-row sm:items-center sm:justify-between">
        <span className="tabular-nums">{resultsLabel}</span>
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              disabled={page <= 1}
              onClick={onPrevious}
              className="min-h-11 text-xs"
            >
              Previous
            </Button>
            <span className="text-xs tabular-nums text-[var(--text-tertiary)]">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="ghost"
              size="sm"
              disabled={page >= totalPages}
              onClick={onNext}
              className="min-h-11 text-xs"
            >
              Next
            </Button>
          </div>
        )}
      </div>
    </>
  );
}

function PatentCpcChips({ codes }: { codes: string[] }) {
  const visibleCodes = codes.filter(Boolean).slice(0, 2);
  const hiddenCodes = codes.filter(Boolean).slice(visibleCodes.length);
  const extraCount = Math.max(0, hiddenCodes.length);

  if (visibleCodes.length === 0) {
    return (
      <p className="mt-1 text-xs text-[var(--text-tertiary)]">
        CPC not indexed
      </p>
    );
  }

  return (
    <div className="mt-2 flex min-w-0 max-w-full flex-wrap gap-1.5">
      {visibleCodes.map((code) => (
        <span
          key={code}
          title={code}
          className="max-w-full break-all rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-0.5 font-mono text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]"
        >
          {code}
        </span>
      ))}
      {extraCount > 0 ? (
        <span
          className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-0.5 text-xs text-[var(--text-tertiary)]"
          title={hiddenCodes.join(", ")}
          aria-label={`${extraCount} additional CPC ${
            extraCount === 1 ? "code" : "codes"
          }: ${hiddenCodes.join(", ")}`}
        >
          +{extraCount}
        </span>
      ) : null}
    </div>
  );
}

function getPatentReportHref(
  patent: PatentItem,
  currentUserRole?: string | null,
  riskRatingsRestricted?: boolean,
): string {
  return getReportAccessHrefWithQuery(
    patent.analysis_id,
    currentUserRole,
    riskRatingsRestricted,
    {
      tab: "patents",
      patent: patent.patent_number,
    },
  );
}

function PatentExpirySignal({
  signal,
}: {
  signal: { dateLabel: string; statusLabel: string; tone: ExpiryTone };
}) {
  return (
    <span className="block">
      <span className="block text-sm font-medium text-[var(--text-secondary)]">
        {signal.dateLabel}
      </span>
      <span
        className={cn(
          "mt-1 inline-flex rounded-full border px-2 py-0.5 text-xs font-medium",
          signal.tone === "expired" &&
            "border-error/25 bg-error/10 text-[var(--color-error-badge-fg)]",
          signal.tone === "soon" &&
            "border-warning/25 bg-warning/10 text-[var(--color-warning-badge-fg)]",
          signal.tone === "active" &&
            "border-success/25 bg-success/10 text-[var(--color-success-badge-fg)]",
          signal.tone === "unknown" &&
            "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-tertiary)]",
        )}
      >
        {signal.statusLabel}
      </span>
    </span>
  );
}

function getRiskRowClass(risk: RiskLevel | null): string {
  if (risk === "high") {
    return "border-l-error min-[1440px]:border-l-error/70";
  }
  if (risk === "medium") {
    return "border-l-warning min-[1440px]:border-l-warning/70";
  }
  if (risk === "low") {
    return "border-l-success min-[1440px]:border-l-success/70";
  }
  if (risk === "clear") {
    return "border-l-info min-[1440px]:border-l-info/70";
  }
  return "border-l-[var(--border-default)]";
}
