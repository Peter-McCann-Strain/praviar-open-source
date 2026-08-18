"use client";

import { useId, useRef } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ANALYSIS_SEARCH_MAX_LENGTH } from "@/lib/analysis-search";
import { cn } from "@/lib/utils";
import type { RiskFilter, SortOption, StatusFilter } from "./helpers";

interface AnalysesPageFiltersProps {
  searchQuery: string;
  statusFilter: StatusFilter;
  riskFilter: RiskFilter;
  sortBy: SortOption;
  statusCounts: Record<string, number>;
  statusCountsExact: boolean;
  riskRatingsRestricted: boolean;
  onClearFilters: () => void;
  onSearchChange: (value: string) => void;
  onStatusFilterChange: (value: StatusFilter) => void;
  onRiskFilterChange: (value: RiskFilter) => void;
  onSortChange: (value: SortOption) => void;
}

const STATUS_LABELS: Record<StatusFilter, string> = {
  all: "All status",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  pending: "Pending",
  cancelled: "Cancelled",
};

const RISK_LABELS: Record<RiskFilter, string> = {
  all: "All Risk",
  high: "High Risk",
  medium: "Medium Risk",
  low: "Low Risk",
  clear: "Clear",
};

const SORT_LABELS: Record<SortOption, string> = {
  "date-desc": "Newest first",
  "date-asc": "Oldest first",
  "risk-desc": "Highest risk",
  "risk-asc": "Lowest risk",
};

export function AnalysesPageFilters({
  searchQuery,
  statusFilter,
  riskFilter,
  sortBy,
  statusCounts,
  statusCountsExact,
  riskRatingsRestricted,
  onClearFilters,
  onSearchChange,
  onStatusFilterChange,
  onRiskFilterChange,
  onSortChange,
}: AnalysesPageFiltersProps) {
  const searchId = useId();
  const statusId = useId();
  const riskId = useId();
  const sortId = useId();
  const noteId = useId();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const visibleSortBy =
    riskRatingsRestricted && (sortBy === "risk-desc" || sortBy === "risk-asc")
      ? "date-desc"
      : sortBy;
  const hasActiveFilters =
    searchQuery.trim().length > 0 ||
    statusFilter !== "all" ||
    (!riskRatingsRestricted && riskFilter !== "all") ||
    visibleSortBy !== "date-desc";
  const formatStatusOption = (label: string, key: string) =>
    statusCountsExact || key === "all"
      ? `${label} (${statusCounts[key] || 0})`
      : label;
  const activeChips = [
    searchQuery.trim() ? { label: `Search: ${searchQuery.trim()}` } : null,
    statusFilter !== "all"
      ? { label: `Status: ${STATUS_LABELS[statusFilter]}` }
      : null,
    !riskRatingsRestricted && riskFilter !== "all"
      ? { label: `Risk: ${RISK_LABELS[riskFilter]}` }
      : null,
    visibleSortBy !== "date-desc"
      ? { label: `Sort: ${SORT_LABELS[visibleSortBy]}` }
      : null,
  ].filter((chip): chip is { label: string } => Boolean(chip));

  return (
    <section
      aria-label="Analysis library controls"
      className="praviar-surface-premium space-y-3 rounded-lg p-3 sm:p-4"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Search and filter packets
          </h2>
          <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
            Filter scope is URL-backed for shared review context.
          </p>
        </div>
        {hasActiveFilters ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Clear all filters"
            onClick={() => {
              onClearFilters();
              searchInputRef.current?.focus();
            }}
            className="min-h-11 w-full gap-2 text-[var(--text-secondary)] sm:w-auto"
          >
            <X className="h-4 w-4" />
            Clear all
          </Button>
        ) : null}
      </div>
      <div
        className={cn(
          "grid gap-2.5 sm:grid-cols-2",
          riskRatingsRestricted
            ? "xl:grid-cols-[minmax(18rem,1.5fr)_repeat(2,minmax(10rem,0.65fr))]"
            : "xl:grid-cols-[minmax(18rem,1.5fr)_repeat(3,minmax(10rem,0.65fr))]",
        )}
      >
        <div className="relative sm:col-span-2 lg:col-span-1 lg:min-w-80 lg:max-w-md lg:flex-1">
          <label htmlFor={searchId} className="sr-only">
            Search analyses
          </label>
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]" />
          <Input
            id={searchId}
            ref={searchInputRef}
            placeholder="Search by compound name or submitted input..."
            className="min-h-11 pl-10"
            maxLength={ANALYSIS_SEARCH_MAX_LENGTH}
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
          />
        </div>
        <div className="min-w-0 space-y-1">
          <label
            htmlFor={statusId}
            className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
          >
            Analysis status
          </label>
          <div className="relative">
            <select
              id={statusId}
              value={statusFilter}
              aria-describedby={noteId}
              onChange={(event) =>
                onStatusFilterChange(event.target.value as StatusFilter)
              }
              className="h-11 w-full appearance-none rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] pl-3 pr-9 text-sm text-[var(--text-secondary)] transition-colors focus:border-brand-primary/40 focus:outline-none focus:ring-2 focus:ring-brand-primary/50"
            >
              <option value="all">
                {formatStatusOption(STATUS_LABELS.all, "all")}
              </option>
              <option value="running">
                {formatStatusOption(STATUS_LABELS.running, "running")}
              </option>
              <option value="completed">
                {formatStatusOption(STATUS_LABELS.completed, "completed")}
              </option>
              <option value="failed">
                {formatStatusOption(STATUS_LABELS.failed, "failed")}
              </option>
              <option value="pending">
                {formatStatusOption(STATUS_LABELS.pending, "pending")}
              </option>
              <option value="cancelled">
                {formatStatusOption(STATUS_LABELS.cancelled, "cancelled")}
              </option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]" />
          </div>
        </div>
        {!riskRatingsRestricted ? (
          <div className="min-w-0 space-y-1">
            <label
              htmlFor={riskId}
              className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
            >
              Risk level
            </label>
            <div className="relative">
              <select
                id={riskId}
                value={riskFilter}
                onChange={(event) =>
                  onRiskFilterChange(event.target.value as RiskFilter)
                }
                className="h-11 w-full appearance-none rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] pl-3 pr-9 text-sm text-[var(--text-secondary)] transition-colors focus:border-brand-primary/40 focus:outline-none focus:ring-2 focus:ring-brand-primary/50"
              >
                <option value="all">{RISK_LABELS.all}</option>
                <option value="high">{RISK_LABELS.high}</option>
                <option value="medium">{RISK_LABELS.medium}</option>
                <option value="low">{RISK_LABELS.low}</option>
                <option value="clear">{RISK_LABELS.clear}</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]" />
            </div>
          </div>
        ) : null}
        <div className="min-w-0 space-y-1">
          <label
            htmlFor={sortId}
            className="block text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
          >
            Sort analyses
          </label>
          <div className="relative">
            <select
              id={sortId}
              value={visibleSortBy}
              onChange={(event) =>
                onSortChange(event.target.value as SortOption)
              }
              className="h-11 w-full appearance-none rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] pl-3 pr-9 text-sm text-[var(--text-secondary)] transition-colors focus:border-brand-primary/40 focus:outline-none focus:ring-2 focus:ring-brand-primary/50"
            >
              <option value="date-desc">{SORT_LABELS["date-desc"]}</option>
              <option value="date-asc">{SORT_LABELS["date-asc"]}</option>
              {!riskRatingsRestricted ? (
                <>
                  <option value="risk-desc">{SORT_LABELS["risk-desc"]}</option>
                  <option value="risk-asc">{SORT_LABELS["risk-asc"]}</option>
                </>
              ) : null}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]" />
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p
          id={noteId}
          className="px-0.5 text-xs leading-5 text-[var(--text-tertiary)]"
        >
          {riskRatingsRestricted
            ? "Risk filtering and sorting are counsel-restricted. Search, status, and date controls still apply across every analysis."
            : statusCountsExact
              ? "Status counts are calculated across the current search and risk scope, not just this page."
              : "Status counts are unavailable for the full dataset; filters still apply across every analysis."}
        </p>
      </div>
      {activeChips.length > 0 ? (
        <div
          className="flex min-w-0 max-w-full flex-wrap gap-2"
          aria-label="Active filters"
          role="list"
        >
          {activeChips.map((chip) => (
            <span
              key={chip.label}
              className="inline-flex max-w-full min-w-0 rounded-full border border-brand-primary/20 bg-brand-primary/10 px-2.5 py-1 text-xs font-medium text-brand-primary"
              role="listitem"
              title={chip.label}
              aria-label={chip.label}
            >
              <span className="min-w-0 truncate">{chip.label}</span>
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
