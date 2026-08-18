"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { LockKeyhole } from "lucide-react";
import { isAuthBoundaryError } from "@/lib/api-client";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useAnalyses } from "@/hooks/use-analysis";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import { AnalysesPageHeader } from "@/components/analyses-page/analyses-page-header";
import { AnalysesPageFilters } from "@/components/analyses-page/analyses-page-filters";
import { AnalysesPageResults } from "@/components/analyses-page/analyses-page-results";
import { AppErrorState } from "@/components/shared/app-error-state";
import { OperationalStatusFrame } from "@/components/shared/operational-status-frame";
import { normalizeAnalysisSearch } from "@/lib/analysis-search";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import {
  buildStatusCounts,
  type RiskFilter,
  type SortOption,
  type StatusFilter,
} from "@/components/analyses-page/helpers";
import AnalysesLoading from "./loading";

const PER_PAGE = 20;
const STATUS_FILTERS = new Set<StatusFilter>([
  "all",
  "running",
  "completed",
  "failed",
  "pending",
  "cancelled",
]);
const RISK_FILTERS = new Set<RiskFilter>([
  "all",
  "high",
  "medium",
  "low",
  "clear",
]);
const SORT_OPTIONS = new Set<SortOption>([
  "date-desc",
  "date-asc",
  "risk-desc",
  "risk-asc",
]);
const EMPTY_STATUS_COUNTS: Record<string, number> = {
  all: 0,
  pending: 0,
  running: 0,
  completed: 0,
  failed: 0,
  cancelled: 0,
};

function resolveStatusFilter(value: string | null): StatusFilter {
  return value && STATUS_FILTERS.has(value as StatusFilter)
    ? (value as StatusFilter)
    : "all";
}

function resolveRiskFilter(value: string | null): RiskFilter {
  return value && RISK_FILTERS.has(value as RiskFilter)
    ? (value as RiskFilter)
    : "all";
}

function resolveSortOption(value: string | null): SortOption {
  return value && SORT_OPTIONS.has(value as SortOption)
    ? (value as SortOption)
    : "date-desc";
}

export default function AnalysesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchParamsKey = searchParams.toString();

  return (
    <AnalysesPageContent
      initialRiskFilter={resolveRiskFilter(searchParams.get("risk"))}
      initialSearchQuery={normalizeAnalysisSearch(searchParams.get("q"))}
      initialSortBy={resolveSortOption(searchParams.get("sort"))}
      initialStatusFilter={resolveStatusFilter(searchParams.get("status"))}
      router={router}
      searchParamsSnapshot={searchParamsKey}
    />
  );
}

interface AnalysesPageContentProps {
  initialRiskFilter: RiskFilter;
  initialSearchQuery: string;
  initialSortBy: SortOption;
  initialStatusFilter: StatusFilter;
  router: ReturnType<typeof useRouter>;
  searchParamsSnapshot: string;
}

function AnalysesPageContent({
  initialRiskFilter,
  initialSearchQuery,
  initialSortBy,
  initialStatusFilter,
  router,
  searchParamsSnapshot,
}: AnalysesPageContentProps) {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const [searchQuery, setSearchQuery] = useState(initialSearchQuery);
  const [appliedSearchQuery, setAppliedSearchQuery] =
    useState(initialSearchQuery);
  const [statusFilter, setStatusFilter] =
    useState<StatusFilter>(initialStatusFilter);
  const [riskFilter, setRiskFilter] = useState<RiskFilter>(initialRiskFilter);
  const [sortBy, setSortBy] = useState<SortOption>(initialSortBy);
  const [page, setPage] = useState(1);
  const searchParamsSnapshotRef = useRef(searchParamsSnapshot);
  const riskCapability = principal.data?.risk_ratings_restricted;
  const riskRatingsRestricted = riskCapability !== false;
  const effectiveRiskFilter = riskRatingsRestricted ? "all" : riskFilter;
  const effectiveSortBy =
    riskRatingsRestricted && (sortBy === "risk-desc" || sortBy === "risk-asc")
      ? "date-desc"
      : sortBy;

  // All filters, search, and sort are pushed to the server so they apply
  // across the full dataset — not just the current 20-row page.
  const {
    data: apiData,
    isLoading,
    isPlaceholderData,
    isError,
    error,
    refetch,
  } = useAnalyses(
    token,
    page,
    PER_PAGE,
    statusFilter,
    effectiveRiskFilter,
    appliedSearchQuery,
    effectiveSortBy,
    riskRatingsRestricted,
  );
  const allAnalyses = apiData?.items ?? [];
  const total = apiData?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE));
  const displayPage = Math.min(page, totalPages);
  const isPageOutOfRange = Boolean(apiData && page > totalPages);
  const hasExactStatusCounts = Boolean(apiData?.status_counts);
  const statusCounts = hasExactStatusCounts
    ? (apiData?.status_counts ?? EMPTY_STATUS_COUNTS)
    : total <= allAnalyses.length
      ? buildStatusCounts(allAnalyses)
      : { ...EMPTY_STATUS_COUNTS, all: total };
  const isAuthMissing = !DEMO_MODE_ENABLED && !token;
  const accessRestricted = isError && isAuthBoundaryError(error);
  const shouldShowFullPageLoading = isLoading && !apiData;
  const isUpdatingResults = Boolean(isPlaceholderData) || isPageOutOfRange;

  const replaceFiltersUrl = useCallback(
    ({
      search,
      status,
      risk,
      sort,
    }: {
      search: string;
      status: StatusFilter;
      risk: RiskFilter;
      sort: SortOption;
    }) => {
      const params = new URLSearchParams(searchParamsSnapshot);
      const trimmedSearch = normalizeAnalysisSearch(search);

      if (trimmedSearch) {
        params.set("q", trimmedSearch);
      } else {
        params.delete("q");
      }

      if (status !== "all") {
        params.set("status", status);
      } else {
        params.delete("status");
      }

      if (risk !== "all") {
        params.set("risk", risk);
      } else {
        params.delete("risk");
      }

      if (sort !== "date-desc") {
        params.set("sort", sort);
      } else {
        params.delete("sort");
      }

      params.delete("page");
      const query = params.toString();
      router.replace(query ? `?${query}` : "/analyses", { scroll: false });
    },
    [router, searchParamsSnapshot],
  );

  useEffect(() => {
    if (
      riskCapability !== true ||
      (riskFilter === "all" && sortBy !== "risk-desc" && sortBy !== "risk-asc")
    ) {
      return undefined;
    }

    const safeSortBy =
      sortBy === "risk-desc" || sortBy === "risk-asc" ? "date-desc" : sortBy;
    const timeout = window.setTimeout(() => {
      setRiskFilter("all");
      setSortBy(safeSortBy);
      setPage(1);
      replaceFiltersUrl({
        search: searchQuery,
        status: statusFilter,
        risk: "all",
        sort: safeSortBy,
      });
    }, 0);

    return () => window.clearTimeout(timeout);
  }, [
    replaceFiltersUrl,
    riskCapability,
    riskFilter,
    searchQuery,
    sortBy,
    statusFilter,
  ]);

  useEffect(() => {
    if (searchParamsSnapshotRef.current === searchParamsSnapshot) {
      return undefined;
    }

    searchParamsSnapshotRef.current = searchParamsSnapshot;
    const timeout = window.setTimeout(() => {
      setSearchQuery(initialSearchQuery);
      setAppliedSearchQuery(initialSearchQuery);
      setStatusFilter(initialStatusFilter);
      setRiskFilter(initialRiskFilter);
      setSortBy(initialSortBy);
      setPage(1);
    }, 0);

    return () => window.clearTimeout(timeout);
  }, [
    initialRiskFilter,
    initialSearchQuery,
    initialSortBy,
    initialStatusFilter,
    searchParamsSnapshot,
  ]);

  useEffect(() => {
    if (apiData && page > totalPages) {
      const timeout = window.setTimeout(() => {
        setPage(totalPages);
      }, 0);

      return () => window.clearTimeout(timeout);
    }

    return undefined;
  }, [apiData, page, totalPages]);

  useEffect(() => {
    const normalizedSearchQuery = normalizeAnalysisSearch(searchQuery);

    if (normalizedSearchQuery === appliedSearchQuery) {
      return undefined;
    }

    const timeout = window.setTimeout(() => {
      setAppliedSearchQuery(normalizedSearchQuery);
      setPage(1);
      replaceFiltersUrl({
        search: normalizedSearchQuery,
        status: statusFilter,
        risk: riskFilter,
        sort: sortBy,
      });
    }, 250);

    return () => window.clearTimeout(timeout);
  }, [
    appliedSearchQuery,
    replaceFiltersUrl,
    riskFilter,
    searchQuery,
    sortBy,
    statusFilter,
  ]);

  if (isAuthMissing) {
    return (
      <div className="space-y-5 animate-fade-up">
        <AnalysesPageHeader
          totalCount={0}
          visibleCount={0}
          visibleAnalyses={[]}
        />
        <OperationalStatusFrame
          contextItems={[
            "Session check in progress",
            "Analysis index remains private",
            "Filters restore after access is confirmed",
          ]}
          dataTestId="analyses-access-auth"
          description="Confirming your team-scoped session before Praviar requests the private analysis index or applies saved library filters."
          eyebrow="Library access"
          icon={LockKeyhole}
          isPending
          recoveryBody="The library waits for a verified workspace token, then requests only organization-scoped analysis records for the active filters."
          recoveryTitle="Preparing the governed analysis library"
          title="Checking analyses access"
          titleId="analyses-access-auth-title"
          tone="default"
        />
      </div>
    );
  }

  if (accessRestricted) {
    return (
      <div className="space-y-5 animate-fade-up">
        <AnalysesPageHeader
          totalCount={0}
          visibleCount={0}
          visibleAnalyses={[]}
        />
        <OperationalStatusFrame
          contextItems={[
            "Cached packets hidden",
            "No analysis records exposed",
            "Retry after access changes",
          ]}
          dataTestId="analyses-access-restricted"
          description="Your current session is not authorized to view this organization-scoped analysis library. Cached records stay hidden until access is confirmed again."
          eyebrow="Library access"
          icon={LockKeyhole}
          isPending={false}
          onRetry={() => {
            void refetch();
          }}
          recoveryBody="A retry requests a fresh authorization check before any analysis packets or saved filter results are shown."
          recoveryTitle="Confirm analysis library access"
          title="Analysis library access restricted"
          titleId="analyses-access-restricted-title"
          tone="error"
        />
      </div>
    );
  }

  if (shouldShowFullPageLoading) {
    return <AnalysesLoading />;
  }

  if (isError) {
    return (
      <div className="space-y-5 animate-fade-up">
        <AnalysesPageHeader
          totalCount={total}
          visibleCount={allAnalyses.length}
          visibleAnalyses={allAnalyses}
        />
        <AppErrorState
          title="Analysis library temporarily unavailable"
          description="We could not load the library index right now. Existing reports are preserved; retry when the workspace connection is available."
          detail="Analysis list request failed."
          aiBrief={{
            items: [
              "Keep saved filters and report links unchanged while the library reloads.",
              "Retry only requests the latest organization-scoped analysis index.",
              "Use already exported reports as temporary counsel references.",
            ],
            note: "No analysis launch, report export, or reviewer decision is submitted from this recovery state.",
          }}
          onAction={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-up">
      <AnalysesPageHeader
        totalCount={total}
        visibleCount={allAnalyses.length}
        visibleAnalyses={allAnalyses}
      />
      <AnalysesPageFilters
        searchQuery={searchQuery}
        statusFilter={statusFilter}
        riskFilter={riskFilter}
        sortBy={sortBy}
        statusCounts={statusCounts}
        statusCountsExact={hasExactStatusCounts || total <= allAnalyses.length}
        riskRatingsRestricted={riskRatingsRestricted}
        onClearFilters={() => {
          setSearchQuery("");
          setAppliedSearchQuery("");
          setStatusFilter("all");
          setRiskFilter("all");
          setSortBy("date-desc");
          setPage(1);
          replaceFiltersUrl({
            search: "",
            status: "all",
            risk: "all",
            sort: "date-desc",
          });
        }}
        onSearchChange={(value) => {
          setSearchQuery(normalizeAnalysisSearch(value));
        }}
        onStatusFilterChange={(value) => {
          const normalizedSearchQuery = normalizeAnalysisSearch(searchQuery);
          setStatusFilter(value);
          setAppliedSearchQuery(normalizedSearchQuery);
          setPage(1);
          replaceFiltersUrl({
            search: normalizedSearchQuery,
            status: value,
            risk: riskFilter,
            sort: sortBy,
          });
        }}
        onRiskFilterChange={(value) => {
          const normalizedSearchQuery = normalizeAnalysisSearch(searchQuery);
          setRiskFilter(value);
          setAppliedSearchQuery(normalizedSearchQuery);
          setPage(1);
          replaceFiltersUrl({
            search: normalizedSearchQuery,
            status: statusFilter,
            risk: value,
            sort: sortBy,
          });
        }}
        onSortChange={(value) => {
          const normalizedSearchQuery = normalizeAnalysisSearch(searchQuery);
          setSortBy(value);
          setAppliedSearchQuery(normalizedSearchQuery);
          setPage(1);
          replaceFiltersUrl({
            search: normalizedSearchQuery,
            status: statusFilter,
            risk: riskFilter,
            sort: value,
          });
        }}
      />
      <AnalysesPageResults
        analyses={allAnalyses}
        allAnalysesCount={total}
        searchQuery={searchQuery}
        statusFilter={statusFilter}
        riskFilter={effectiveRiskFilter}
        sortBy={effectiveSortBy}
        page={displayPage}
        totalPages={totalPages}
        perPage={PER_PAGE}
        isLoading={isUpdatingResults}
        onPreviousPage={() =>
          setPage((current) =>
            current > totalPages ? totalPages : Math.max(1, current - 1),
          )
        }
        onNextPage={() =>
          setPage((current) => Math.min(totalPages, current + 1))
        }
        onClearFilters={() => {
          setSearchQuery("");
          setAppliedSearchQuery("");
          setStatusFilter("all");
          setRiskFilter("all");
          setSortBy("date-desc");
          setPage(1);
          replaceFiltersUrl({
            search: "",
            status: "all",
            risk: "all",
            sort: "date-desc",
          });
        }}
      />
    </div>
  );
}
