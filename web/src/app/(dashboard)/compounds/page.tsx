"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { isAuthBoundaryError } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useCompounds } from "@/hooks/use-compounds";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import type { CompoundItem } from "@/hooks/use-compounds";
import { CompoundsPageHeader } from "@/components/compounds/compounds-page-header";
import { CompoundsPageSummary } from "@/components/compounds/compounds-page-summary";
import { CompoundsSearchBar } from "@/components/compounds/compounds-search-bar";
import { CompoundsTable } from "@/components/compounds/compounds-table";
import { CompoundDetailCard } from "@/components/compounds/compound-detail-card";
import { CompoundsPagination } from "@/components/compounds/compounds-pagination";
import {
  getCompoundDetailId,
  normalizeCompoundSearchInput,
} from "@/components/compounds/helpers";
import { LibraryStatusState } from "@/components/shared/library-status-state";

function reportCompoundLibraryLoadFailure() {
  console.error("[CompoundsPage] Failed to load compound library");
}

function reportCompoundLibraryAccessRestriction() {
  console.error("[CompoundsPage] Compound library access restricted");
}

export default function CompoundsPage() {
  const token = useAuthToken();
  const perPage = 20;
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    },
    [],
  );

  function handleSearchChange(value: string) {
    const normalizedValue = normalizeCompoundSearchInput(value);
    setSearchQuery(normalizedValue);
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      setDebouncedSearch(normalizedValue.trim());
      setPage(1);
    }, 300);
  }

  function clearSearch() {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    setSearchQuery("");
    setDebouncedSearch("");
    setSelectedId(null);
    setPage(1);
  }

  const {
    data: apiData,
    isLoading,
    isFetching,
    isPlaceholderData,
    isError,
    error,
    refetch,
  } = useCompounds(token, page, perPage, debouncedSearch || undefined);
  const compounds = useMemo(() => apiData?.items ?? [], [apiData]);
  const total = apiData?.total ?? 0;
  const responsePerPage = apiData?.per_page ?? perPage;
  const totalPages = Math.max(1, Math.ceil(total / responsePerPage));
  const responsePage = apiData?.page ?? page;
  const displayPage = Math.min(Math.max(1, responsePage), totalPages);
  const isQueryUpdating = Boolean(isFetching && apiData);
  const isTableLoading = isLoading && !apiData;
  const isOutOfRangeEmptyPage = Boolean(
    apiData && total > 0 && compounds.length === 0,
  );
  const accessRestricted = isError && isAuthBoundaryError(error);
  const staleRefreshError = Boolean(isError && apiData && !accessRestricted);
  const authMissing = !token;
  const shouldShowFullPageLoading =
    isLoading &&
    !apiData &&
    page === 1 &&
    searchQuery.trim().length === 0 &&
    debouncedSearch.length === 0;
  const initialLoadFailed = Boolean(
    !authMissing && !shouldShowFullPageLoading && isError && !apiData,
  );
  const cachedAccessRestricted = Boolean(
    !authMissing && accessRestricted && apiData,
  );

  useErrorDiagnostic(
    initialLoadFailed,
    error,
    reportCompoundLibraryLoadFailure,
  );
  useErrorDiagnostic(
    cachedAccessRestricted,
    error,
    reportCompoundLibraryAccessRestriction,
  );

  const selectedCompound = useMemo<CompoundItem | null>(
    () => compounds.find((compound) => compound.id === selectedId) ?? null,
    [compounds, selectedId],
  );

  useEffect(() => {
    if (!apiData) return undefined;
    if (page <= totalPages) return undefined;
    const clampTimer = window.setTimeout(() => {
      setPage(totalPages);
    }, 0);
    return () => window.clearTimeout(clampTimer);
  }, [apiData, page, totalPages]);

  useEffect(() => {
    if (!apiData) return undefined;
    if (!selectedId) return undefined;
    if (compounds.some((compound) => compound.id === selectedId)) {
      return undefined;
    }
    const clearSelectionTimer = window.setTimeout(() => {
      setSelectedId(null);
    }, 0);
    return () => window.clearTimeout(clearSelectionTimer);
  }, [apiData, compounds, selectedId]);

  if (authMissing) {
    return (
      <div className="space-y-5 animate-fade-up">
        <CompoundsPageHeader />
        <LibraryStatusState surface="compounds" variant="auth" />
      </div>
    );
  }

  if (shouldShowFullPageLoading) {
    return (
      <div className="space-y-5 animate-fade-up">
        <CompoundsPageHeader />
        <LibraryStatusState surface="compounds" variant="loading" />
      </div>
    );
  }

  if (isError && !apiData) {
    return (
      <div className="space-y-5 animate-fade-up">
        <CompoundsPageHeader />
        <LibraryStatusState
          surface="compounds"
          variant={accessRestricted ? "restricted" : "temporary"}
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (accessRestricted) {
    return (
      <div className="space-y-5 animate-fade-up">
        <CompoundsPageHeader />
        <LibraryStatusState
          surface="compounds"
          variant="restricted"
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-up">
      <CompoundsPageHeader
        compounds={compounds}
        isUpdating={isQueryUpdating}
        selectedCompoundName={selectedCompound?.name ?? null}
        total={total}
      />
      <CompoundsPageSummary compounds={compounds} total={total} />
      <CompoundsSearchBar
        value={searchQuery}
        onChange={handleSearchChange}
        onClearSearch={clearSearch}
        total={total}
        visibleCount={compounds.length}
      />
      {staleRefreshError ? (
        <div
          role="status"
          aria-live="polite"
          className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]"
        >
          Compound library refresh failed. Existing normalized records remain
          shown, and no compound data was changed.
        </div>
      ) : null}
      <div
        className={
          selectedCompound
            ? "grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,24rem)] xl:items-start"
            : "space-y-3"
        }
      >
        <div className="space-y-3">
          <CompoundsTable
            compounds={compounds}
            selectedId={selectedId}
            searchQuery={debouncedSearch}
            isLoading={isTableLoading}
            isUpdating={isQueryUpdating}
            isOutOfRangeEmptyPage={isOutOfRangeEmptyPage}
            getDetailId={getCompoundDetailId}
            onSearchExampleSelect={handleSearchChange}
            onToggleSelect={(compoundId) =>
              setSelectedId((currentId) =>
                currentId === compoundId ? null : compoundId,
              )
            }
          />
          <CompoundsPagination
            page={displayPage}
            perPage={responsePerPage}
            totalPages={totalPages}
            total={total}
            visibleCount={compounds.length}
            isUpdating={isQueryUpdating}
            isNavigationDisabled={
              Boolean(isPlaceholderData) ||
              isTableLoading ||
              isOutOfRangeEmptyPage
            }
            requestedPage={page}
            onPrevious={() =>
              setPage((currentPage) => Math.max(1, currentPage - 1))
            }
            onNext={() =>
              setPage((currentPage) => Math.min(totalPages, currentPage + 1))
            }
          />
        </div>
        {selectedCompound ? (
          <CompoundDetailCard
            id={getCompoundDetailId(selectedCompound.id)}
            compound={selectedCompound}
            className="xl:sticky xl:top-24"
            onClose={() => setSelectedId(null)}
          />
        ) : null}
      </div>
    </div>
  );
}
