import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

interface CompoundsPaginationProps {
  page: number;
  perPage: number;
  totalPages: number;
  total: number;
  visibleCount: number;
  isUpdating?: boolean;
  isNavigationDisabled?: boolean;
  requestedPage?: number;
  onPrevious: () => void;
  onNext: () => void;
}

export function CompoundsPagination({
  page,
  perPage,
  totalPages,
  total,
  visibleCount,
  isUpdating = false,
  isNavigationDisabled = false,
  requestedPage,
  onPrevious,
  onNext,
}: CompoundsPaginationProps) {
  const hasVisibleRows = total > 0 && visibleCount > 0;
  const rangeStart = hasVisibleRows ? (page - 1) * perPage + 1 : 0;
  const rangeEnd = hasVisibleRows
    ? Math.min(total, rangeStart + visibleCount - 1)
    : 0;
  const resultsLabel = hasVisibleRows
    ? `Showing ${rangeStart}-${rangeEnd} of ${total.toLocaleString()} compounds`
    : total > 0
      ? `Showing 0 of ${total.toLocaleString()} compounds`
      : "Showing 0 compounds";
  const updateLabel =
    isUpdating && requestedPage && requestedPage !== page
      ? `Updating page ${requestedPage}`
      : isUpdating
        ? "Refreshing compounds"
        : null;

  return (
    <div className="flex flex-col gap-3 text-sm text-[var(--text-secondary)] sm:flex-row sm:items-center sm:justify-between">
      <p className="sr-only" role="status" aria-live="polite">
        {updateLabel ? `${resultsLabel}. ${updateLabel}.` : resultsLabel}
      </p>
      <span className="flex flex-wrap items-center gap-2">
        <span className="tabular-nums text-sm text-[var(--text-secondary)]">
          {resultsLabel}
        </span>
        {updateLabel ? (
          <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-0.5 text-xs font-medium uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            {updateLabel}
          </span>
        ) : null}
      </span>
      {totalPages > 1 && (
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1 || isNavigationDisabled}
            aria-label="Previous compounds page"
            title="Previous compounds page"
            onClick={onPrevious}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="tabular-nums text-sm text-[var(--text-secondary)]">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages || isNavigationDisabled}
            aria-label="Next compounds page"
            title="Next compounds page"
            onClick={onNext}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
