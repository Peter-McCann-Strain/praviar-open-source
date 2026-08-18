import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AnalysesPage from "@/app/(dashboard)/analyses/page";
import { APIError } from "@/lib/api-client";
import { ANALYSIS_SEARCH_MAX_LENGTH } from "@/lib/analysis-search";

const mockUseAuthToken = vi.fn();
const mockUseAnalyses = vi.fn();
const mockUsePrincipalCapabilities = vi.hoisted(() => vi.fn());
const navigationMocks = vi.hoisted(() => ({
  replace: vi.fn(),
  searchParams: "",
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/hooks/use-analysis", () => ({
  useAnalyses: (...args: unknown[]) => mockUseAnalyses(...args),
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => mockUsePrincipalCapabilities(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigationMocks.replace }),
  useSearchParams: () => new URLSearchParams(navigationMocks.searchParams),
}));

const analyses = [
  {
    id: "ana-1",
    compound_input: "Aspirin",
    compound_name: "Aspirin",
    compound_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
    status: "completed",
    progress_pct: 100,
    overall_risk: "high",
    total_patents_found: 15,
    blocking_patents_count: 2,
    executive_summary:
      "Two blocking patent families require counsel review before launch.",
    estimated_cost_usd: 4.2,
    pipeline_duration_seconds: 320,
    flagged_for_review: true,
    current_user_role: "attorney",
    review_status: {
      status: "under_review",
      is_persisted: true,
      reviewer_name: "Dr. Rao",
    },
    share_active: true,
    share_view_count: 3,
    share_last_viewed_at: "2026-03-22T12:00:00Z",
    created_at: "2026-03-20T12:00:00Z",
    updated_at: "2026-03-22T12:00:00Z",
    current_step: 8,
  },
  {
    id: "ana-2",
    compound_input: "Ibuprofen",
    compound_name: "Ibuprofen",
    compound_smiles: "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
    status: "running",
    progress_pct: 38,
    overall_risk: "medium",
    total_patents_found: 8,
    blocking_patents_count: 0,
    executive_summary: "",
    estimated_cost_usd: 2.1,
    pipeline_duration_seconds: null,
    flagged_for_review: false,
    current_user_role: "attorney",
    review_status: null,
    share_active: false,
    share_view_count: 0,
    share_last_viewed_at: null,
    created_at: "2026-03-21T12:00:00Z",
    updated_at: "2026-03-21T12:05:00Z",
    current_step: 3,
  },
];

const statusCounts = {
  all: 12,
  pending: 1,
  running: 3,
  completed: 6,
  failed: 1,
  cancelled: 1,
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <AnalysesPage />
    </QueryClientProvider>,
  );
}

describe("AnalysesPage", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    navigationMocks.searchParams = "";
    mockUseAuthToken.mockReturnValue("test-token");
    mockUsePrincipalCapabilities.mockReturnValue({
      data: {
        can_create_analysis: true,
        risk_ratings_restricted: false,
      },
    });
    mockUseAnalyses.mockReturnValue({
      data: {
        items: analyses,
        total: 12,
        page: 1,
        per_page: 20,
        status_counts: statusCounts,
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  it("renders the analyses library shell and search input", () => {
    renderPage();

    expect(screen.getByText("Analysis Library")).toBeInTheDocument();
    expect(screen.getByTestId("analyses-app-surface-header")).toHaveAttribute(
      "data-praviar-app-surface-header",
    );
    expect(
      screen.getByText(
        "Search, triage, review state, and shared report handoffs across every FTO packet for your organization.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Evidence archive")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Matching packets")).toBeInTheDocument();
    expect(screen.getByText("Current page")).toBeInTheDocument();
    expect(screen.getByText("Visible packets")).toBeInTheDocument();
    expect(screen.getByText("Page needs review")).toBeInTheDocument();
    expect(screen.getByText("Page shares")).toBeInTheDocument();
    expect(screen.getByText("Current library scope")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New Analysis" })).toHaveAttribute(
      "href",
      "/analyses/new",
    );
    expect(
      screen.getByPlaceholderText(
        "Search by compound name or submitted input...",
      ),
    ).toHaveAttribute("maxLength", String(ANALYSIS_SEARCH_MAX_LENGTH));
    expect(screen.getByLabelText("Search analyses")).toBeInTheDocument();
    expect(screen.getByLabelText("Analysis status")).toBeInTheDocument();
    expect(screen.getByLabelText("Risk level")).toBeInTheDocument();
    expect(screen.getByLabelText("Sort analyses")).toBeInTheDocument();
    expect(screen.getByText("Search and filter packets")).toBeInTheDocument();
    expect(screen.getByText(/Filter scope is URL-backed/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Status counts are calculated/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Cancelled (1)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Analysis Library evidence packets/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Evidence packets" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Date" })).toHaveAttribute(
      "aria-sort",
      "descending",
    );
    expect(screen.getByRole("columnheader", { name: "Risk" })).toHaveAttribute(
      "aria-sort",
      "none",
    );
  });

  it("keeps the loading state while auth is still resolving", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUseAnalyses.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByTestId("analyses-access-auth")).toHaveAttribute(
      "data-praviar-status-frame",
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Checking analyses access",
    );
    expect(screen.queryByText("No analyses yet")).not.toBeInTheDocument();
  });

  it("hides cached analysis rows when the auth token disappears", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUseAnalyses.mockReturnValue({
      data: {
        items: analyses,
        total: 12,
        page: 1,
        per_page: 20,
        status_counts: statusCounts,
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByTestId("analyses-access-auth")).toHaveAttribute(
      "data-praviar-status-frame",
    );
    expect(screen.queryByText("Aspirin")).not.toBeInTheDocument();
    expect(screen.queryByText("Ibuprofen")).not.toBeInTheDocument();
  });

  it("hides cached analysis rows when access is restricted", () => {
    mockUseAnalyses.mockReturnValue({
      data: {
        items: analyses,
        total: 12,
        page: 1,
        per_page: 20,
        status_counts: statusCounts,
      },
      isLoading: false,
      isError: true,
      error: new APIError(403, "Forbidden"),
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByTestId("analyses-access-restricted")).toHaveAttribute(
      "data-praviar-status-frame",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Analysis library access restricted",
    );
    expect(screen.queryByText("Aspirin")).not.toBeInTheDocument();
    expect(screen.queryByText("Ibuprofen")).not.toBeInTheDocument();
  });

  it("removes counsel-only URL filters for restricted roles without losing the library", () => {
    vi.useFakeTimers();
    navigationMocks.searchParams =
      "risk=high&sort=risk-desc&status=completed&workspace=active";
    mockUsePrincipalCapabilities.mockReturnValue({
      data: {
        can_create_analysis: true,
        risk_ratings_restricted: true,
      },
    });
    mockUseAnalyses.mockReturnValue({
      data: {
        items: analyses.map((analysis) => ({
          ...analysis,
          overall_risk: null,
          blocking_patents_count: null,
          risk_ratings_restricted: true,
          current_user_role: "scientist",
        })),
        total: 2,
        page: 1,
        per_page: 20,
        status_counts: { ...statusCounts, all: 2, completed: 1, running: 1 },
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(mockUseAnalyses.mock.calls.at(-1)?.[4]).toBe("all");
    expect(mockUseAnalyses.mock.calls.at(-1)?.[6]).toBe("date-desc");
    expect(mockUseAnalyses.mock.calls.at(-1)?.[7]).toBe(true);
    expect(screen.queryByLabelText("Risk level")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "Highest risk" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Sort analyses")).toHaveValue("date-desc");
    expect(
      screen.getByText(/Risk filtering and sorting are counsel-restricted/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Counsel restricted")).toHaveLength(2);
    expect(
      screen.queryByText("Analysis library access restricted"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Aspirin")).toBeInTheDocument();

    act(() => {
      vi.runOnlyPendingTimers();
    });

    expect(navigationMocks.replace).toHaveBeenCalledWith(
      "?status=completed&workspace=active",
      { scroll: false },
    );
  });

  it("fails closed while risk capability is unresolved without issuing a risk query", () => {
    navigationMocks.searchParams = "risk=high&sort=risk-asc";
    mockUsePrincipalCapabilities.mockReturnValue({ data: undefined });

    renderPage();

    expect(mockUseAnalyses.mock.calls.at(-1)?.[4]).toBe("all");
    expect(mockUseAnalyses.mock.calls.at(-1)?.[6]).toBe("date-desc");
    expect(mockUseAnalyses.mock.calls.at(-1)?.[7]).toBe(true);
    expect(screen.queryByLabelText("Risk level")).not.toBeInTheDocument();
    expect(screen.getByText("Aspirin")).toBeInTheDocument();
    expect(navigationMocks.replace).not.toHaveBeenCalled();
  });

  it("renders a recovery state when the library index cannot load", () => {
    mockUseAnalyses.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    });

    renderPage();

    expect(
      screen.getByText("Analysis library temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI recovery brief" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Keep saved filters and report links unchanged/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows the running step detail and report action for completed analyses", () => {
    renderPage();

    expect(screen.getByText("Step 3/8")).toBeInTheDocument();
    const reportLink = screen.getByRole("link", {
      name: "Open packet for Aspirin",
    });
    expect(reportLink).toBeInTheDocument();
    expect(reportLink).toHaveAttribute("href", "/analyses/ana-1/report");
    expect(
      screen.getByRole("link", { name: "View run for Ibuprofen" }),
    ).toHaveAttribute("href", "/analyses/ana-2");
  });

  it("surfaces review, share, and provenance signals on evidence packets", () => {
    renderPage();

    expect(screen.getAllByText("Evidence packet").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Under review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Shared · 3 views").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Evidence building").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Private").length).toBeGreaterThan(0);
    expect(
      screen.getByText(
        "Two blocking patent families require counsel review before launch.",
      ),
    ).toBeInTheDocument();
  });

  it("labels an in-progress development fixture without claiming live worker execution", () => {
    mockUseAnalyses.mockReturnValue({
      data: {
        items: [
          {
            ...analyses[1],
            development_fixture: true,
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
        status_counts: { ...statusCounts, all: 1, running: 1 },
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText("Seeded preview")).toBeInTheDocument();
    expect(screen.getByText("Static · Step 3/8")).toBeInTheDocument();
    expect(screen.getAllByText("Development fixture").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByText(/no worker execution or elapsed runtime is implied/i),
    ).toBeInTheDocument();
  });

  it("renders analysis rows as compact cards that become a table on large screens", () => {
    renderPage();

    const aspirinRow = screen.getByText("Aspirin").closest("tr");
    expect(aspirinRow).toHaveClass("block");
    expect(aspirinRow).toHaveClass("xl:table-row");
    expect(screen.getByRole("columnheader", { name: "Compound" })).toHaveClass(
      "px-5",
    );
    expect(
      screen
        .getAllByText("Status")
        .some((element) => element.className.includes("xl:hidden")),
    ).toBe(true);
    expect(screen.getByText("Updated Mar 22, 2026")).toHaveClass(
      "whitespace-nowrap",
    );
    expect(
      screen.getByRole("link", { name: "Open packet for Aspirin" }),
    ).toHaveClass("min-h-11");
  });

  it("filters the table by search query", () => {
    vi.useFakeTimers();
    // Search is server-side: the mock returns filtered data matching the search arg.
    mockUseAnalyses.mockImplementation(
      (_token, _page, _perPage, _status, _risk, search) => ({
        data: {
          items: analyses.filter(
            (a) =>
              !search ||
              a.compound_name.toLowerCase().includes(search.toLowerCase()),
          ),
          total: analyses.filter(
            (a) =>
              !search ||
              a.compound_name.toLowerCase().includes(search.toLowerCase()),
          ).length,
          page: 1,
          per_page: 20,
          status_counts: {
            ...statusCounts,
            all: analyses.filter(
              (a) =>
                !search ||
                a.compound_name.toLowerCase().includes(search.toLowerCase()),
            ).length,
          },
        },
        isLoading: false,
      }),
    );

    renderPage();

    fireEvent.change(
      screen.getByPlaceholderText(
        "Search by compound name or submitted input...",
      ),
      { target: { value: "ibuprofen" } },
    );

    act(() => {
      vi.advanceTimersByTime(260);
    });

    expect(screen.getByText("Ibuprofen")).toBeInTheDocument();
    expect(screen.queryByText("Aspirin")).not.toBeInTheDocument();
  });

  it("keeps the search control focused and mounted while debounced results load", () => {
    vi.useFakeTimers();
    mockUseAnalyses.mockImplementation(
      (_token, _page, _perPage, _status, _risk, search) => {
        if (search) {
          return {
            data: {
              items: analyses,
              total: 12,
              page: 1,
              per_page: 20,
              status_counts: statusCounts,
            },
            isLoading: false,
            isPlaceholderData: true,
            isError: false,
            refetch: vi.fn(),
          };
        }

        return {
          data: {
            items: analyses,
            total: 12,
            page: 1,
            per_page: 20,
            status_counts: statusCounts,
          },
          isLoading: false,
          isError: false,
          refetch: vi.fn(),
        };
      },
    );

    renderPage();

    const searchInput = screen.getByLabelText("Search analyses");
    searchInput.focus();
    fireEvent.change(searchInput, { target: { value: "aspirin" } });

    expect(searchInput).toHaveFocus();
    expect(searchInput).toHaveValue("aspirin");

    act(() => {
      vi.advanceTimersByTime(260);
    });

    expect(screen.getByLabelText("Search analyses")).toHaveFocus();
    expect(screen.getByLabelText("Search analyses")).toHaveValue("aspirin");
    expect(screen.getByText(/Loading matching analyses/i)).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Evidence packets" }),
    ).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Matching packets")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("trims and clamps search before querying and updating the URL", () => {
    vi.useFakeTimers();
    const longSearch = ` ${"a".repeat(ANALYSIS_SEARCH_MAX_LENGTH + 32)} `;
    const clampedSearch = "a".repeat(ANALYSIS_SEARCH_MAX_LENGTH);
    mockUseAnalyses.mockImplementation(
      (_token, _page, _perPage, _status, _risk, search) => ({
        data: {
          items: analyses,
          total: analyses.length,
          page: 1,
          per_page: 20,
          status_counts: statusCounts,
        },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
        meta: search,
      }),
    );

    renderPage();

    fireEvent.change(screen.getByLabelText("Search analyses"), {
      target: { value: longSearch },
    });

    act(() => {
      vi.advanceTimersByTime(260);
    });

    expect(screen.getByLabelText("Search analyses")).toHaveValue(clampedSearch);
    expect(mockUseAnalyses.mock.calls.at(-1)?.[5]).toBe(clampedSearch);
    expect(navigationMocks.replace).toHaveBeenCalledWith(
      `?q=${clampedSearch}`,
      {
        scroll: false,
      },
    );
  });

  it("shows the filtered empty state and clears filters", () => {
    vi.useFakeTimers();
    // Server returns empty when search yields no results; full list when cleared.
    mockUseAnalyses.mockImplementation(
      (_token, _page, _perPage, _status, _risk, search) => ({
        data: {
          items: search ? [] : analyses,
          total: search ? 0 : analyses.length,
          page: 1,
          per_page: 20,
          status_counts: search
            ? {
                all: 0,
                pending: 0,
                running: 0,
                completed: 0,
                failed: 0,
                cancelled: 0,
              }
            : statusCounts,
        },
        isLoading: false,
      }),
    );

    renderPage();

    fireEvent.change(
      screen.getByPlaceholderText(
        "Search by compound name or submitted input...",
      ),
      { target: { value: "zzz" } },
    );

    act(() => {
      vi.advanceTimersByTime(260);
    });

    expect(
      screen.getByText("No analyses match your filters"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByText("Aspirin")).toBeInTheDocument();
  });

  it("clears filter state from the URL while preserving unrelated params", () => {
    navigationMocks.searchParams =
      "risk=high&status=completed&q=aspirin&sort=risk-desc&foo=bar&page=3";
    mockUseAnalyses.mockReturnValue({
      data: {
        items: [],
        total: 0,
        page: 1,
        per_page: 20,
        status_counts: {
          all: 0,
          pending: 0,
          running: 0,
          completed: 0,
          failed: 0,
          cancelled: 0,
        },
      },
      isLoading: false,
    });

    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(navigationMocks.replace).toHaveBeenCalledWith("?foo=bar", {
      scroll: false,
    });
    expect(mockUseAnalyses.mock.calls.at(-1)?.[6]).toBe("date-desc");
  });

  it("contains long active filter chips and returns focus to search when cleared", () => {
    const longQuery = `InChI=1S/${"C".repeat(180)}-patent-family-token`;
    const clampedQuery = longQuery.slice(0, ANALYSIS_SEARCH_MAX_LENGTH);
    navigationMocks.searchParams = `risk=high&status=completed&q=${encodeURIComponent(
      longQuery,
    )}&sort=risk-desc`;

    renderPage();

    const activeFilters = screen.getByRole("list", { name: "Active filters" });
    const searchChipLabel = `Search: ${clampedQuery}`;
    const searchChipText = screen.getByText(searchChipLabel);
    const searchChip = searchChipText.closest('[role="listitem"]');

    expect(mockUseAnalyses.mock.calls.at(-1)?.[5]).toBe(clampedQuery);
    expect(activeFilters).toHaveClass("min-w-0", "max-w-full", "flex-wrap");
    expect(searchChip).toHaveClass("max-w-full", "min-w-0");
    expect(searchChip).toHaveAttribute("title", searchChipLabel);
    expect(searchChip).toHaveAccessibleName(searchChipLabel);
    expect(searchChipText).toHaveClass("min-w-0", "truncate");
    expect(screen.getByText("Status: Completed")).toBeInTheDocument();
    expect(screen.getByText("Risk: High Risk")).toBeInTheDocument();
    expect(screen.getByText("Sort: Highest risk")).toBeInTheDocument();

    const clearButton = screen.getByRole("button", {
      name: "Clear all filters",
    });
    clearButton.focus();
    fireEvent.click(clearButton);

    expect(screen.getByLabelText("Search analyses")).toHaveFocus();
    expect(navigationMocks.replace).toHaveBeenCalledWith("/analyses", {
      scroll: false,
    });
  });

  it("keeps row risk rails aligned with risk badge semantics", () => {
    mockUseAnalyses.mockReturnValue({
      data: {
        items: [
          {
            ...analyses[0],
            id: "ana-low",
            compound_name: "Lowrail",
            overall_risk: "low",
          },
          {
            ...analyses[1],
            id: "ana-clear",
            compound_name: "Clearrail",
            status: "completed",
            overall_risk: "clear",
          },
        ],
        total: 2,
        page: 1,
        per_page: 20,
        status_counts: { ...statusCounts, all: 2, completed: 2, running: 0 },
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText("Lowrail").closest("tr")).toHaveClass(
      "border-l-success",
    );
    expect(screen.getByText("Clearrail").closest("tr")).toHaveClass(
      "border-l-info",
    );
  });

  it("does not present page-local status counts as full-dataset status counts", () => {
    mockUseAnalyses.mockReturnValue({
      data: {
        items: [analyses[0]],
        total: 45,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(
      screen.getByRole("option", { name: "All status (45)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Completed" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "Completed (1)" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Status counts are unavailable for the full dataset/i),
    ).toBeInTheDocument();
  });

  it("gives repeated row actions compound-specific accessible names", () => {
    mockUseAnalyses.mockReturnValue({
      data: {
        items: [
          analyses[0],
          {
            ...analyses[1],
            status: "completed",
            progress_pct: 100,
          },
        ],
        total: 2,
        page: 1,
        per_page: 20,
        status_counts: { ...statusCounts, all: 2, completed: 2, running: 0 },
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(
      screen.getByRole("link", { name: "Open packet for Aspirin" }),
    ).toHaveAttribute("href", "/analyses/ana-1/report");
    expect(
      screen.getByRole("link", { name: "Open packet for Ibuprofen" }),
    ).toHaveAttribute("href", "/analyses/ana-2/report");
  });

  it("renders pending review, singular share views, reviewer metadata, and zero duration", () => {
    mockUseAnalyses.mockReturnValue({
      data: {
        items: [
          {
            ...analyses[0],
            pipeline_duration_seconds: 0,
            share_view_count: 1,
            review_status: {
              status: "pending",
              is_persisted: true,
              reviewer_name: "Dr. Rao",
            },
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
        status_counts: { ...statusCounts, all: 1 },
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getAllByText("Review pending").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Shared · 1 view").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Reviewer: Dr. Rao").length).toBeGreaterThan(0);
    expect(screen.getByText("0s")).toBeInTheDocument();
  });

  it("paginates when the total exceeds one page of results", () => {
    // Server reports 45 total results but only returns the first page of 20.
    mockUseAnalyses.mockReturnValue({
      data: {
        items: analyses,
        total: 45,
        page: 1,
        per_page: 20,
        status_counts: { ...statusCounts, all: 45 },
      },
      isLoading: false,
    });
    renderPage();

    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    const nextButton = screen.getByRole("button", { name: "Next page" });
    expect(nextButton).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Previous page" }),
    ).toBeDisabled();

    fireEvent.click(nextButton);

    // The page state advances and is passed to useAnalyses as the page arg.
    const lastCall = mockUseAnalyses.mock.calls.at(-1);
    expect(lastCall?.[1]).toBe(2);
  });

  it("does not show pagination when results fit on one page", () => {
    renderPage();

    expect(
      screen.queryByRole("button", { name: "Next page" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Page \d+ of \d+/)).not.toBeInTheDocument();
  });

  it("uses grounded empty-state copy when no private records exist", () => {
    mockUseAnalyses.mockReturnValue({
      data: {
        items: [],
        total: 0,
        page: 1,
        per_page: 20,
        status_counts: {
          all: 0,
          pending: 0,
          running: 0,
          completed: 0,
          failed: 0,
          cancelled: 0,
        },
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText("Evidence packet workflow")).toBeInTheDocument();
    expect(screen.queryByText("Evidence packet ready")).not.toBeInTheDocument();
  });

  it("clamps displayed pagination when server totals shrink below the current page", async () => {
    let total = 45;
    mockUseAnalyses.mockImplementation((_token, page, perPage) => ({
      data: {
        items: page <= Math.ceil(total / perPage) ? analyses : [],
        total,
        page,
        per_page: perPage,
        status_counts: { ...statusCounts, all: total },
      },
      isLoading: false,
    }));

    const { rerender } = renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(mockUseAnalyses.mock.calls.at(-1)?.[1]).toBe(3);

    total = 25;
    rerender(
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: { queries: { retry: false } },
          })
        }
      >
        <AnalysesPage />
      </QueryClientProvider>,
    );

    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    expect(
      screen.queryByText("Showing 21-20 of 25 analyses"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Updating matching analyses..."),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(mockUseAnalyses.mock.calls.at(-1)?.[1]).toBe(2);
    });
    expect(screen.getByText("Aspirin")).toBeInTheDocument();
    expect(screen.queryByText("No analyses yet")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));

    expect(mockUseAnalyses.mock.calls.at(-1)?.[1]).toBe(1);
  });
});
