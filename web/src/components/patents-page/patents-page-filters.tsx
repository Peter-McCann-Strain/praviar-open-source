import { ChevronDown, Search, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ID_SORT_OPTIONS,
  RISK_FILTER_OPTIONS,
  SORT_OPTIONS,
  type RiskFilter,
  type SortOption,
} from "./helpers";
import { cn } from "@/lib/utils";

interface PatentsPageFiltersProps {
  searchQuery: string;
  riskFilter: RiskFilter;
  sortBy: SortOption;
  onSearchQueryChange: (nextQuery: string) => void;
  onRiskFilterChange: (nextRiskFilter: RiskFilter) => void;
  onSortByChange: (nextSortBy: SortOption) => void;
  onClearFilters: () => void;
  restoreSearchFocusSignal?: number;
  canViewRisk?: boolean;
}

export function PatentsPageFilters({
  searchQuery,
  riskFilter,
  sortBy,
  onSearchQueryChange,
  onRiskFilterChange,
  onSortByChange,
  onClearFilters,
  restoreSearchFocusSignal = 0,
  canViewRisk = false,
}: PatentsPageFiltersProps) {
  const searchId = useId();
  const riskFilterId = useId();
  const sortId = useId();
  const sortHelpId = useId();
  const searchInputRef = useRef<HTMLInputElement>(null);
  const hasMountedRef = useRef(false);
  const trimmedSearchQuery = searchQuery.trim();
  const activeRiskLabel = RISK_FILTER_OPTIONS.find(
    (option) => option.value === riskFilter,
  )?.label;
  const activeChips = [
    trimmedSearchQuery ? { label: `Search: ${trimmedSearchQuery}` } : null,
    canViewRisk && riskFilter !== "all" && activeRiskLabel
      ? { label: `Risk: ${activeRiskLabel}` }
      : null,
  ].filter((chip): chip is { label: string } => Boolean(chip));
  const hasActiveFilters = activeChips.length > 0;
  const sortOptions = canViewRisk ? SORT_OPTIONS : ID_SORT_OPTIONS;

  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      return;
    }

    if (restoreSearchFocusSignal > 0) {
      searchInputRef.current?.focus();
    }
  }, [restoreSearchFocusSignal]);

  return (
    <section
      aria-label="Patent library controls"
      className="praviar-surface-premium rounded-lg border border-[var(--card-border)] p-3 sm:p-4"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
        <div className="min-w-0 flex-1">
          <label
            htmlFor={searchId}
            className="mb-1.5 block text-xs font-semibold uppercase text-[var(--text-tertiary)]"
          >
            Search patents
          </label>
          <div className="relative">
            <Search
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]"
              aria-hidden="true"
            />
            <Input
              id={searchId}
              ref={searchInputRef}
              placeholder="Search by patent ID, title, assignee, or compound..."
              className="h-11 pl-10"
              maxLength={200}
              value={searchQuery}
              onChange={(event) => onSearchQueryChange(event.target.value)}
            />
          </div>
        </div>

        <div
          className={cn(
            "grid gap-3",
            canViewRisk ? "sm:grid-cols-2 lg:w-[28rem]" : "lg:w-56",
          )}
        >
          {canViewRisk ? (
            <div className="min-w-0">
              <label
                htmlFor={riskFilterId}
                className="mb-1.5 block text-xs font-semibold uppercase text-[var(--text-tertiary)]"
              >
                Risk filter
              </label>
              <div className="relative">
                <select
                  id={riskFilterId}
                  value={riskFilter}
                  onChange={(event) =>
                    onRiskFilterChange(event.target.value as RiskFilter)
                  }
                  className="h-11 w-full cursor-pointer appearance-none rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] pl-3 pr-9 text-sm text-[var(--text-secondary)] transition-colors focus:border-brand-primary/40 focus:outline-none focus:ring-2 focus:ring-brand-primary/50"
                >
                  {RISK_FILTER_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]"
                  aria-hidden="true"
                />
              </div>
            </div>
          ) : null}

          <div className="min-w-0">
            <label
              htmlFor={sortId}
              className="mb-1.5 block text-xs font-semibold uppercase text-[var(--text-tertiary)]"
            >
              Sort library
            </label>
            <div className="relative">
              <select
                id={sortId}
                value={sortBy}
                onChange={(event) =>
                  onSortByChange(event.target.value as SortOption)
                }
                aria-describedby={sortHelpId}
                className="h-11 w-full cursor-pointer appearance-none rounded-md border border-[var(--border-emphasis)] bg-[var(--surface-muted)] pl-3 pr-9 text-sm text-[var(--text-secondary)] transition-colors focus:border-brand-primary/40 focus:outline-none focus:ring-2 focus:ring-brand-primary/50"
              >
                {sortOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-disabled)]"
                aria-hidden="true"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-3 sm:flex-row sm:items-center sm:justify-between">
        <p
          id={sortHelpId}
          className="text-xs leading-5 text-[var(--text-tertiary)]"
        >
          {canViewRisk
            ? "Search, risk, and sort controls query the verified library before pagination."
            : "Search and patent-ID sort controls query the verified library before pagination. Counsel-governed risk remains restricted."}
        </p>
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
          {activeChips.length > 0 ? (
            <div
              className="flex min-w-0 max-w-full flex-wrap items-center gap-2"
              aria-label="Active patent filters"
              role="list"
            >
              {activeChips.map((chip) => (
                <span
                  key={chip.label}
                  className="inline-flex max-w-full min-w-0 rounded-full border border-[var(--border-default)] bg-[var(--surface-muted)] px-3 py-1 text-xs text-[var(--text-secondary)]"
                  role="listitem"
                  title={chip.label}
                  aria-label={chip.label}
                >
                  <span className="min-w-0 truncate">{chip.label}</span>
                </span>
              ))}
            </div>
          ) : null}
          {hasActiveFilters ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 gap-1.5 text-xs"
              onClick={() => {
                onClearFilters();
                searchInputRef.current?.focus();
              }}
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
              Clear patent filters
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
