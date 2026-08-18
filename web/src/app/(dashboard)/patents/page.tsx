"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { isAuthBoundaryError } from "@/lib/api-client";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import { usePatents } from "@/hooks/use-patents";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import {
  PatentsPageFilters,
  PatentsPageHeader,
  PatentsPageResults,
  PatentsPageSummary,
} from "@/components/patents-page";
import {
  filterAndSortPatents,
  type RiskFilter,
  type SortOption,
} from "@/components/patents-page/helpers";
import { LibraryStatusState } from "@/components/shared/library-status-state";

const MAX_PATENT_SEARCH_LENGTH = 200;

function reportPatentLibraryLoadFailure() {
  console.error("[PatentsPage] Failed to load patent library");
}

function reportPatentLibraryAccessRestriction() {
  console.error("[PatentsPage] Patent library access restricted");
}

export default function PatentsPage() {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const [page, setPage] = useState(1);
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortOption>("risk-desc");
  const [searchFocusSignal, setSearchFocusSignal] = useState(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const perPage = 20;
  const canViewRisk = principal.data?.risk_ratings_restricted === false;
  const effectiveRiskFilter: RiskFilter = canViewRisk ? riskFilter : "all";
  const effectiveSort: SortOption =
    canViewRisk || sortBy === "id-asc" || sortBy === "id-desc"
      ? sortBy
      : "id-asc";

  // Debounce the search so we don't fire a request on every keystroke.
  // Reset to page 1 when the search changes.
  const handleSearchChange = (value: string) => {
    const nextValue = value.slice(0, MAX_PATENT_SEARCH_LENGTH);
    setSearchQuery(nextValue);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(nextValue.trim());
      setPage(1);
    }, 300);
  };

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    [],
  );

  const {
    data: apiData,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = usePatents(
    token,
    page,
    perPage,
    effectiveRiskFilter !== "all" ? effectiveRiskFilter : undefined,
    debouncedSearch || undefined,
    effectiveSort,
  );

  const allPatents = useMemo(() => apiData?.items ?? [], [apiData]);
  const total = apiData?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const displayPage = Math.min(apiData?.page ?? page, totalPages);

  // The API sorts before pagination; this keeps visible rows deterministic for
  // demo data and placeholder responses while a new page is loading.
  const sortedPatents = useMemo(
    () => filterAndSortPatents(allPatents, "", effectiveSort),
    [allPatents, effectiveSort],
  );

  useEffect(() => {
    if (page <= totalPages) return undefined;
    const clampTimer = window.setTimeout(() => {
      setPage(totalPages);
    }, 0);
    return () => window.clearTimeout(clampTimer);
  }, [page, totalPages]);

  const clearFilters = () => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    setSearchQuery("");
    setDebouncedSearch("");
    setRiskFilter("all");
    setPage(1);
  };
  const clearFiltersAndFocus = () => {
    clearFilters();
    setSearchFocusSignal((signal) => signal + 1);
  };
  const accessRestricted = isError && isAuthBoundaryError(error);
  const staleRefreshError = Boolean(isError && apiData && !accessRestricted);
  const authMissing = !DEMO_MODE_ENABLED && !token;
  const shouldShowFullPageLoading =
    isLoading &&
    !apiData &&
    page === 1 &&
    searchQuery.trim().length === 0 &&
    debouncedSearch.length === 0 &&
    effectiveRiskFilter === "all";
  const initialLoadFailed = Boolean(
    !authMissing && !shouldShowFullPageLoading && isError && !apiData,
  );
  const cachedAccessRestricted = Boolean(
    !authMissing && accessRestricted && apiData,
  );

  useErrorDiagnostic(initialLoadFailed, error, reportPatentLibraryLoadFailure);
  useErrorDiagnostic(
    cachedAccessRestricted,
    error,
    reportPatentLibraryAccessRestriction,
  );

  if (authMissing) {
    return (
      <div className="space-y-5 animate-fade-up">
        <PatentsPageHeader />
        <LibraryStatusState surface="patents" variant="auth" />
      </div>
    );
  }

  if (shouldShowFullPageLoading) {
    return (
      <div className="space-y-5 animate-fade-up">
        <PatentsPageHeader />
        <LibraryStatusState surface="patents" variant="loading" />
      </div>
    );
  }

  if (isError && !apiData) {
    return (
      <div className="space-y-5 animate-fade-up">
        <PatentsPageHeader />
        <LibraryStatusState
          surface="patents"
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
        <PatentsPageHeader />
        <LibraryStatusState
          surface="patents"
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
      <PatentsPageHeader
        patents={sortedPatents}
        total={total}
        isUpdating={Boolean(isFetching && apiData)}
        canViewRisk={canViewRisk}
      />
      <PatentsPageSummary
        patents={sortedPatents}
        total={total}
        canViewRisk={canViewRisk}
      />
      <PatentsPageFilters
        searchQuery={searchQuery}
        riskFilter={effectiveRiskFilter}
        sortBy={effectiveSort}
        canViewRisk={canViewRisk}
        onSearchQueryChange={handleSearchChange}
        onRiskFilterChange={(nextRiskFilter) => {
          setRiskFilter(nextRiskFilter);
          setPage(1);
        }}
        onSortByChange={(nextSortBy) => {
          setSortBy(nextSortBy);
          setPage(1);
        }}
        onClearFilters={clearFiltersAndFocus}
        restoreSearchFocusSignal={searchFocusSignal}
      />
      {staleRefreshError ? (
        <div
          role="status"
          aria-live="polite"
          className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]"
        >
          Patent library refresh failed. Existing verified records remain shown,
          and no evidence data was changed.
        </div>
      ) : null}
      <PatentsPageResults
        patents={sortedPatents}
        total={total}
        page={displayPage}
        perPage={perPage}
        totalPages={totalPages}
        isLoading={isLoading && !apiData}
        isUpdating={Boolean(isFetching && apiData)}
        searchQuery={debouncedSearch}
        riskFilter={effectiveRiskFilter}
        onClearFilters={clearFiltersAndFocus}
        onPrevious={() =>
          setPage((currentPage) => Math.max(1, currentPage - 1))
        }
        onNext={() =>
          setPage((currentPage) => Math.min(totalPages, currentPage + 1))
        }
        currentUserRole={principal.data?.role}
        riskRatingsRestricted={principal.data?.risk_ratings_restricted}
        canViewRisk={canViewRisk}
      />
    </div>
  );
}
