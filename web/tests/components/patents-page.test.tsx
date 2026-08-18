import { describe, expect, it, beforeEach, vi } from "vitest";
import { StrictMode } from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { APIError } from "@/lib/api-client";
import type { PatentItem } from "@/hooks/use-patents";
import {
  extractJurisdiction,
  filterAndSortPatents,
  formatPatentExpiryDate,
  getPatentExpirySignal,
} from "@/components/patents-page/helpers";

const mockUseAuthToken = vi.fn();
const mockUsePatents = vi.fn();
const principalState = vi.hoisted(() => ({
  role: "attorney",
  riskRatingsRestricted: false,
}));

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/hooks/use-patents", () => ({
  usePatents: (...args: unknown[]) => mockUsePatents(...args),
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      role: principalState.role,
      risk_ratings_restricted: principalState.riskRatingsRestricted,
    },
  }),
}));

import PatentsPage from "@/app/(dashboard)/patents/page";

const patents: PatentItem[] = [
  {
    id: "p1",
    patent_number: "US0000000001A1",
    title: "Fermentation process",
    assignee: "Fictional Meridian Therapeutics",
    risk_level: "high",
    cpc_codes: ["C12P7/46", "C07C51/00", "A61K31/00"],
    expiry_date: "2038-01-15",
    analysis_id: "analysis-1",
    compound_name: "Succinic acid",
  },
  {
    id: "p2",
    patent_number: "US0000000002A1",
    title: "Purification method",
    assignee: "Fictional Atlas Chemistry",
    risk_level: "medium",
    cpc_codes: ["B01D15/00"],
    expiry_date: "2027-01-10",
    analysis_id: "analysis-2",
    compound_name: "Succinic acid",
  },
];

describe("PatentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthToken.mockReturnValue("test-token");
    principalState.role = "attorney";
    principalState.riskRatingsRestricted = false;
    mockUsePatents.mockImplementation(
      (
        _token: string,
        page: number,
        perPage: number,
        _riskFilter?: string,
        searchQuery?: string,
      ) => ({
        data: {
          items: searchQuery ? [] : patents,
          total: searchQuery ? 0 : 40,
          page,
          per_page: perPage,
        },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      }),
    );
  });

  it("renders the browser shell and preserves filters, actions, and pagination", async () => {
    render(<PatentsPage />);

    expect(screen.getByText("Patent Evidence Library")).toBeInTheDocument();
    expect(
      screen.getByText(/Browse verified patent evidence published/i),
    ).toBeInTheDocument();
    expect(
      screen
        .getByText("Patent Evidence Library")
        .closest("[data-praviar-app-surface-header]"),
    ).toBeInTheDocument();
    expect(screen.getByText("Library matches")).toBeInTheDocument();
    expect(screen.getByText("Visible page")).toBeInTheDocument();
    expect(screen.getByText("Page high risk")).toBeInTheDocument();
    expect(screen.getByText("Term attention")).toBeInTheDocument();
    expect(screen.getByLabelText("Search patents")).toHaveClass("h-11");
    expect(screen.getByLabelText("Risk filter")).toHaveClass("h-11");
    expect(screen.getByLabelText("Sort library")).toHaveClass("h-11");
    expect(screen.getByLabelText("Search patents")).not.toHaveClass("sm:h-9");
    expect(screen.getByLabelText("Risk filter")).not.toHaveClass("sm:h-9");
    expect(screen.getByLabelText("Sort library")).not.toHaveClass("sm:h-9");
    expect(
      screen.getByText(/query the verified library before pagination/i),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("region", { name: "Patent evidence summary" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Matching records")).toBeInTheDocument();
    expect(screen.getByText("Visible high risk")).toBeInTheDocument();
    expect(screen.getAllByText("Expiring <2y").length).toBeGreaterThanOrEqual(
      1,
    );
    expect(screen.getByText("Evidence readiness")).toBeInTheDocument();
    expect(screen.getByText(/Ready for review/i)).toBeInTheDocument();
    expect(screen.getByText("CPC indexed")).toBeInTheDocument();
    expect(screen.getByText("Term signals")).toBeInTheDocument();
    expect(screen.getByText("Report handoff")).toHaveClass(
      "leading-4",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("Evidence readiness").closest(".grid")).toHaveClass(
      "min-[1440px]:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]",
    );
    expect(screen.getByRole("table")).toHaveClass("min-[1440px]:min-w-[920px]");
    expect(screen.getByText("US0000000001A1").closest("tr")).toHaveClass(
      "block",
      "min-[1440px]:table-row",
    );
    expect(
      screen.getAllByText("Showing 1-2 of 40 patents").length,
    ).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toHaveClass(
      "min-h-11",
    );
    expect(
      screen.getByRole("link", {
        name: "Open patent evidence for US0000000001A1",
      }),
    ).toHaveClass("min-h-11");
    expect(
      screen.getByRole("link", {
        name: "Open patent evidence for US0000000001A1",
      }),
    ).toHaveAttribute(
      "href",
      "/analyses/analysis-1/report?tab=patents&patent=US0000000001A1",
    );
    expect(
      screen.getByRole("link", {
        name: "Open patent evidence for US0000000002A1",
      }),
    ).toHaveAttribute(
      "href",
      "/analyses/analysis-2/report?tab=patents&patent=US0000000002A1",
    );
    expect(screen.getByText("C12P7/46")).toBeInTheDocument();
    expect(
      screen.getByLabelText("1 additional CPC code: A61K31/00"),
    ).toHaveTextContent("+1");
    expect(screen.getByText("Jan 15, 2038")).toBeInTheDocument();
    expect(screen.getByText("Active term")).toBeInTheDocument();
    expect(screen.getAllByText("Expires <2y").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Clear filters")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search patents"), {
      target: { value: "no-match" },
    });

    await waitFor(() => {
      expect(
        screen.getByText("No patents match your filters"),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Try adjusting your search or risk filter/i),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Clear filters" }),
      ).toBeInTheDocument();
    });

    const emptyClearButton = screen.getByRole("button", {
      name: "Clear filters",
    });
    emptyClearButton.focus();
    fireEvent.click(emptyClearButton);

    await waitFor(() => {
      expect(screen.getByLabelText("Search patents")).toHaveValue("");
      expect(screen.getByLabelText("Search patents")).toHaveFocus();
      expect(
        screen.queryByText("No patents match your filters"),
      ).not.toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Risk filter"), {
      target: { value: "high" },
    });

    await waitFor(() => {
      expect(mockUsePatents).toHaveBeenLastCalledWith(
        "test-token",
        1,
        20,
        "high",
        undefined,
        "risk-desc",
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(mockUsePatents).toHaveBeenLastCalledWith(
        "test-token",
        2,
        20,
        "high",
        undefined,
        "risk-desc",
      );
    });

    fireEvent.change(screen.getByLabelText("Risk filter"), {
      target: { value: "all" },
    });

    await waitFor(() => {
      expect(mockUsePatents).toHaveBeenLastCalledWith(
        "test-token",
        1,
        20,
        undefined,
        undefined,
        "risk-desc",
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(screen.getByLabelText("Sort library"), {
      target: { value: "id-desc" },
    });

    await waitFor(() => {
      expect(mockUsePatents).toHaveBeenLastCalledWith(
        "test-token",
        1,
        20,
        undefined,
        undefined,
        "id-desc",
      );
    });
  });

  it.each([
    {
      role: "scientist",
      riskRatingsRestricted: true,
      linkName: "Open patent evidence for US0000000001A1",
      href: "/analyses/analysis-1/report/summary",
    },
    {
      role: "scientist",
      riskRatingsRestricted: false,
      linkName: "Open patent evidence for US0000000001A1",
      href: "/analyses/analysis-1/report?tab=patents&patent=US0000000001A1",
    },
    {
      role: "client",
      riskRatingsRestricted: false,
      linkName: "Open patent evidence for US0000000001A1",
      href: "/analyses/analysis-1/report/summary",
    },
    {
      role: "attorney",
      riskRatingsRestricted: true,
      linkName: "Open patent evidence for US0000000001A1",
      href: "/analyses/analysis-1/report?tab=patents&patent=US0000000001A1",
    },
  ])(
    "routes $role patent handoffs to the authorized report surface",
    ({ role, riskRatingsRestricted, linkName, href }) => {
      principalState.role = role;
      principalState.riskRatingsRestricted = riskRatingsRestricted;

      render(<PatentsPage />);

      expect(screen.getByRole("link", { name: linkName })).toHaveAttribute(
        "href",
        href,
      );
    },
  );

  it("fails closed for risk-restricted principals across queries and rendered patent surfaces", () => {
    principalState.role = "scientist";
    principalState.riskRatingsRestricted = true;
    const restrictedPatents: PatentItem[] = [
      {
        ...patents[0],
        risk_level: "high",
      },
      {
        ...patents[1],
        risk_level: undefined,
      },
    ];
    mockUsePatents.mockReturnValue({
      data: {
        items: restrictedPatents,
        total: 2,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = render(<PatentsPage />);

    expect(mockUsePatents).toHaveBeenLastCalledWith(
      "test-token",
      1,
      20,
      undefined,
      undefined,
      "id-asc",
    );
    expect(screen.queryByLabelText("Risk filter")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Sort library")).toHaveValue("id-asc");
    expect(
      screen.queryByRole("option", { name: "High risk first" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "Low risk first" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Page high risk")).not.toBeInTheDocument();
    expect(screen.queryByText("Visible high risk")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: "Risk" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Visible assignees")).toBeInTheDocument();
    expect(
      screen.getByText(/Counsel-governed risk remains restricted/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("table")).toHaveClass("min-[1440px]:min-w-[820px]");
    expect(container.querySelector("tbody tr")).toHaveClass(
      "border-l-[var(--border-default)]",
    );
    expect(
      screen.getByRole("link", {
        name: "Open patent evidence for US0000000001A1",
      }),
    ).toHaveAttribute("href", "/analyses/analysis-1/report/summary");
  });

  it("neutralizes active risk controls immediately when capabilities become restricted", async () => {
    const { rerender } = render(<PatentsPage />);

    fireEvent.change(screen.getByLabelText("Risk filter"), {
      target: { value: "high" },
    });

    await waitFor(() => {
      expect(mockUsePatents).toHaveBeenLastCalledWith(
        "test-token",
        1,
        20,
        "high",
        undefined,
        "risk-desc",
      );
    });

    principalState.role = "scientist";
    principalState.riskRatingsRestricted = true;
    rerender(<PatentsPage />);

    await waitFor(() => {
      expect(mockUsePatents).toHaveBeenLastCalledWith(
        "test-token",
        1,
        20,
        undefined,
        undefined,
        "id-asc",
      );
    });
    expect(screen.queryByLabelText("Risk filter")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Sort library")).toHaveValue("id-asc");
  });

  it("cancels pending debounced search when filters are cleared", async () => {
    vi.useFakeTimers();
    try {
      render(<PatentsPage />);

      fireEvent.change(screen.getByLabelText("Search patents"), {
        target: { value: "no-match" },
      });
      fireEvent.click(
        screen.getByRole("button", { name: "Clear patent filters" }),
      );

      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      expect(screen.getByLabelText("Search patents")).toHaveValue("");
      expect(mockUsePatents).toHaveBeenLastCalledWith(
        "test-token",
        1,
        20,
        undefined,
        undefined,
        "risk-desc",
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("contains long active patent filter chips and returns focus when cleared", () => {
    const longQuery = `InChI=1S/${"C".repeat(180)}-patent-family-token`;
    const clampedQuery = longQuery.slice(0, 200);

    render(<PatentsPage />);

    fireEvent.change(screen.getByLabelText("Search patents"), {
      target: { value: longQuery },
    });
    fireEvent.change(screen.getByLabelText("Risk filter"), {
      target: { value: "high" },
    });

    const activeFilters = screen.getByRole("list", {
      name: "Active patent filters",
    });
    const searchChipLabel = `Search: ${clampedQuery}`;
    const searchChipText = screen.getByText(searchChipLabel);
    const searchChip = searchChipText.closest('[role="listitem"]');

    expect(activeFilters).toHaveClass("min-w-0", "max-w-full", "flex-wrap");
    expect(searchChip).toHaveClass("max-w-full", "min-w-0");
    expect(searchChip).toHaveAttribute("title", searchChipLabel);
    expect(searchChip).toHaveAccessibleName(searchChipLabel);
    expect(searchChipText).toHaveClass("min-w-0", "truncate");
    expect(screen.getByLabelText("Search patents")).toHaveValue(clampedQuery);

    const clearButton = screen.getByRole("button", {
      name: "Clear patent filters",
    });
    clearButton.focus();
    fireEvent.click(clearButton);

    expect(screen.getByLabelText("Search patents")).toHaveFocus();
    expect(screen.getByLabelText("Search patents")).toHaveValue("");
  });

  it("ignores whitespace-only patent searches as inactive filters", async () => {
    vi.useFakeTimers();
    try {
      render(<PatentsPage />);

      fireEvent.change(screen.getByLabelText("Search patents"), {
        target: { value: "   " },
      });

      expect(
        screen.queryByRole("list", { name: "Active patent filters" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Clear patent filters" }),
      ).not.toBeInTheDocument();

      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      expect(mockUsePatents).toHaveBeenLastCalledWith(
        "test-token",
        1,
        20,
        undefined,
        undefined,
        "risk-desc",
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("clamps overlong patent searches before querying the API", async () => {
    vi.useFakeTimers();
    try {
      const longQuery = `US${"9".repeat(240)}`;
      const clampedQuery = longQuery.slice(0, 200);
      render(<PatentsPage />);

      fireEvent.change(screen.getByLabelText("Search patents"), {
        target: { value: longQuery },
      });

      expect(screen.getByLabelText("Search patents")).toHaveValue(clampedQuery);

      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      expect(mockUsePatents).toHaveBeenLastCalledWith(
        "test-token",
        1,
        20,
        undefined,
        clampedQuery,
        "risk-desc",
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps patent search focused and mounted while filtered results load", async () => {
    vi.useFakeTimers();
    try {
      mockUsePatents.mockImplementation(
        (
          _token: string,
          page: number,
          perPage: number,
          _riskFilter?: string,
          searchQuery?: string,
        ) => {
          if (searchQuery) {
            return {
              data: {
                items: patents,
                total: 40,
                page,
                per_page: perPage,
              },
              isLoading: false,
              isFetching: true,
              isError: false,
              error: null,
              refetch: vi.fn(),
            };
          }

          return {
            data: {
              items: patents,
              total: 40,
              page,
              per_page: perPage,
            },
            isLoading: false,
            isFetching: false,
            isError: false,
            error: null,
            refetch: vi.fn(),
          };
        },
      );

      render(<PatentsPage />);

      const searchInput = screen.getByLabelText("Search patents");
      searchInput.focus();
      fireEvent.change(searchInput, { target: { value: "aspirin" } });

      await act(async () => {
        vi.advanceTimersByTime(350);
      });

      expect(screen.getByLabelText("Search patents")).toHaveFocus();
      expect(screen.getByLabelText("Search patents")).toHaveValue("aspirin");
      expect(screen.getByText(/updating result page/i)).toBeInTheDocument();
      expect(screen.getByText("Fermentation process")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps the patent workspace mounted during a placeholder page transition", async () => {
    mockUsePatents.mockImplementation(
      (_token: string, page: number, perPage: number) => {
        if (page === 2) {
          return {
            data: {
              items: patents,
              total: 40,
              page: 1,
              per_page: perPage,
            },
            isLoading: false,
            isFetching: true,
            isError: false,
            error: null,
            refetch: vi.fn(),
          };
        }

        return {
          data: {
            items: patents,
            total: 40,
            page,
            per_page: perPage,
          },
          isLoading: false,
          isFetching: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        };
      },
    );

    render(<PatentsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(mockUsePatents).toHaveBeenLastCalledWith(
        "test-token",
        2,
        20,
        undefined,
        undefined,
        "risk-desc",
      );
    });

    expect(screen.getByLabelText("Search patents")).toBeInTheDocument();
    expect(screen.getByText("Evidence records")).toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: "Patent evidence records horizontal scroll area",
      }),
    ).toHaveClass("min-[1440px]:overflow-x-auto");
    expect(
      screen.getByRole("region", {
        name: "Patent evidence records horizontal scroll area",
      }),
    ).toHaveAttribute("tabindex", "0");
    expect(screen.getByText(/updating result page/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();
  });

  it("normalizes risk and jurisdiction casing before sorting and rendering rows", () => {
    mockUsePatents.mockReturnValue({
      data: {
        items: [
          {
            ...patents[1],
            id: "mixed-risk-medium",
            patent_number: "ep10987654b2",
            risk_level: "Medium",
          },
          {
            ...patents[0],
            id: "mixed-risk-high",
            patent_number: "us0000000001a1",
            risk_level: "HIGH",
          },
        ],
        total: 2,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = render(<PatentsPage />);

    const rows = Array.from(container.querySelectorAll("tbody tr"));
    expect(rows[0]).toHaveTextContent("us0000000001a1");
    expect(rows[0]).toHaveClass("border-l-error");
    expect(rows[0]).toHaveTextContent("US");
    expect(rows[1]).toHaveTextContent("ep10987654b2");
    expect(rows[1]).toHaveClass("border-l-warning");
    expect(rows[1]).toHaveTextContent("EP");
  });

  it("keeps low and clear patent row rails aligned with shared risk badge semantics", () => {
    mockUsePatents.mockReturnValue({
      data: {
        items: [
          {
            ...patents[0],
            id: "low-risk-patent",
            patent_number: "US10000001B2",
            risk_level: "low",
          },
          {
            ...patents[1],
            id: "clear-risk-patent",
            patent_number: "US10000002B2",
            risk_level: "clear",
          },
        ],
        total: 2,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    const { container } = render(<PatentsPage />);

    const rows = Array.from(container.querySelectorAll("tbody tr"));
    expect(rows[0]).toHaveTextContent("US10000001B2");
    expect(rows[0]).toHaveClass("border-l-success");
    expect(rows[1]).toHaveTextContent("US10000002B2");
    expect(rows[1]).toHaveClass("border-l-info");
  });

  it("keeps unknown risk rows last when sorting by risk", () => {
    const unknownRiskPatent: PatentItem = {
      ...patents[0],
      id: "unknown-risk-patent",
      patent_number: "US00000000B2",
      risk_level: "",
    };

    expect(
      filterAndSortPatents(
        [unknownRiskPatent, patents[0], patents[1]],
        "",
        "risk-asc",
      ).map((patent) => patent.patent_number),
    ).toEqual(["US0000000002A1", "US0000000001A1", "US00000000B2"]);

    expect(
      filterAndSortPatents(
        [unknownRiskPatent, patents[1], patents[0]],
        "",
        "risk-desc",
      ).map((patent) => patent.patent_number),
    ).toEqual(["US0000000001A1", "US0000000002A1", "US00000000B2"]);
  });

  it("only renders recognized patent authority prefixes as jurisdictions", () => {
    expect(extractJurisdiction("US0000000001A1")).toBe("US");
    expect(extractJurisdiction("ep10987654b2")).toBe("EP");
    expect(extractJurisdiction("PCT/US2026/000123")).toBe("PCT");
    expect(extractJurisdiction("internal-record-123")).toBe("\u2014");
    expect(extractJurisdiction("ZZ123456")).toBe("\u2014");
  });

  it("contains long patent titles and CPC tokens inside responsive rows", () => {
    const longTitle = `${"Crystalline-polymorph-".repeat(16)}terminal`;
    const longCpc = `C07D${"9".repeat(96)}/unbroken-token`;
    mockUsePatents.mockReturnValue({
      data: {
        items: [
          {
            ...patents[0],
            title: longTitle,
            cpc_codes: [longCpc],
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<PatentsPage />);

    expect(screen.getByText(longTitle)).toHaveClass(
      "break-words",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longCpc)).toHaveClass(
      "max-w-full",
      "break-all",
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText(longCpc)).toHaveAttribute("title", longCpc);
  });

  it("shows an access-checking state while the private library query is gated", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUsePatents.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<PatentsPage />);

    expect(screen.getByText("Patent Evidence Library")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Checking patent evidence library access",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No library data exposed")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText(
        "Search by patent ID, title, assignee, or compound...",
      ),
    ).not.toBeInTheDocument();
  });

  it("fails closed when a token is lost while previous patent data exists", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUsePatents.mockReturnValue({
      data: {
        items: patents,
        total: 40,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<PatentsPage />);

    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Checking patent evidence library access",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Fermentation process")).not.toBeInTheDocument();
    expect(screen.queryByText("Purification method")).not.toBeInTheDocument();
  });

  it("shows a governed loading state before patent data arrives", () => {
    mockUsePatents.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<PatentsPage />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Loading patent evidence library",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Showing 1-2 of 40 patents"),
    ).not.toBeInTheDocument();
  });

  it("keeps existing patent rows visible during a background reload", () => {
    mockUsePatents.mockReturnValue({
      data: {
        items: patents,
        total: 40,
        page: 1,
        per_page: 20,
      },
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<PatentsPage />);

    expect(
      screen.getAllByText("Showing 1-2 of 40 patents").length,
    ).toBeGreaterThanOrEqual(2);
    expect(
      screen.queryByRole("heading", {
        level: 2,
        name: "Loading patent evidence library",
      }),
    ).not.toBeInTheDocument();
  });

  it("warns when existing patent rows are shown after a background refresh fails", () => {
    mockUsePatents.mockReturnValue({
      data: {
        items: patents,
        total: 40,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isError: true,
      error: new Error("API error: 500 should stay hidden"),
      refetch: vi.fn(),
    });

    render(<PatentsPage />);

    expect(
      screen.getAllByText("Showing 1-2 of 40 patents").length,
    ).toBeGreaterThanOrEqual(2);
    expect(
      screen.queryByRole("heading", {
        level: 2,
        name: "Patent evidence library temporarily unavailable",
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Patent library refresh failed/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/API error: 500/)).not.toBeInTheDocument();
  });

  it("hides cached patent rows when a background access refresh is restricted", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUsePatents.mockReturnValue({
      data: {
        items: patents,
        total: 40,
        page: 1,
        per_page: 20,
      },
      isLoading: false,
      isError: true,
      error: new APIError(403, "Forbidden"),
      refetch,
    });

    render(<PatentsPage />);

    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Patent evidence library access restricted",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Fermentation process")).not.toBeInTheDocument();
    expect(screen.queryByText("Purification method")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry library load" }));

    expect(refetch).toHaveBeenCalledTimes(1);
    consoleError.mockRestore();
  });

  it("shows a safe retry state when patent library loading fails", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUsePatents.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("API error: 500 DATABASE_URL org_id"),
      refetch,
    });

    render(
      <StrictMode>
        <PatentsPage />
      </StrictMode>,
    );

    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Patent evidence library temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/DATABASE_URL|org_id|API error: 500/),
    ).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith(
      "[PatentsPage] Failed to load patent library",
    );
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.stringMatching(/DATABASE_URL|org_id|API error: 500/),
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry library load" }));

    expect(refetch).toHaveBeenCalledTimes(1);
    consoleError.mockRestore();
  });

  it("formats patent expiry dates in UTC and classifies term status", () => {
    expect(formatPatentExpiryDate("2038-01-15")).toBe("Jan 15, 2038");
    expect(
      getPatentExpirySignal("2027-01-10", new Date("2026-06-19T12:00:00.000Z")),
    ).toMatchObject({
      dateLabel: "Jan 10, 2027",
      statusLabel: "Expires <2y",
      tone: "soon",
    });
    expect(
      getPatentExpirySignal("2024-01-10", new Date("2026-06-19T12:00:00.000Z")),
    ).toMatchObject({
      statusLabel: "Expired",
      tone: "expired",
    });
    expect(getPatentExpirySignal(null)).toMatchObject({
      statusLabel: "Unknown expiry",
      tone: "unknown",
    });
  });
});
