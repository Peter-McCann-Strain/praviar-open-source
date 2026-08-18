import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { APIError } from "@/lib/api-client";
import CompoundsPage from "@/app/(dashboard)/compounds/page";
import { MAX_COMPOUND_SEARCH_LENGTH } from "@/components/compounds/helpers";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mockUseAuthToken = vi.fn();
const mockUseCompounds = vi.fn();

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => mockUseAuthToken(),
}));

vi.mock("@/hooks/use-principal-capabilities", () => ({
  usePrincipalCapabilities: () => ({
    data: {
      can_create_analysis: true,
    },
  }),
}));

vi.mock("@/hooks/use-compounds", () => ({
  useCompounds: (...args: unknown[]) => mockUseCompounds(...args),
}));

const compounds = [
  {
    id: "c1",
    canonical_smiles: "CC(=O)OC1=CC=CC=C1C(=O)O",
    inchi_key: "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
    name: "Aspirin",
    molecular_formula: "C9H8O4",
    molecular_weight: 180.16,
    functional_groups: ["ester", "carboxylic acid"],
    pubchem_cid: 2244,
    first_analyzed_at: "2026-03-20T12:00:00Z",
    analysis_count: 4,
  },
  {
    id: "c2",
    canonical_smiles: "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
    inchi_key: "HEFNNWSXXWATRW-UHFFFAOYSA-N",
    name: "Ibuprofen",
    molecular_formula: "C13H18O2",
    molecular_weight: 206.28,
    functional_groups: [],
    pubchem_cid: null,
    first_analyzed_at: "2026-03-21T12:00:00Z",
    analysis_count: 2,
  },
];

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const createUi = () => (
    <QueryClientProvider client={queryClient}>
      <CompoundsPage />
    </QueryClientProvider>
  );
  const view = render(createUi());
  return {
    ...view,
    rerenderPage: () => view.rerender(createUi()),
  };
}

function renderStrictPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <CompoundsPage />
      </QueryClientProvider>
    </StrictMode>,
  );
}

describe("CompoundsPage", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthToken.mockReturnValue("test-token");
    mockUseCompounds.mockReturnValue({
      data: { items: compounds, total: 2, page: 1, per_page: 20 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  it("renders the compounds library shell and search input", () => {
    renderPage();

    expect(screen.getByText("Compound Library")).toBeInTheDocument();
    expect(
      screen.getByText(/All compounds analyzed by your organization/i),
    ).toBeInTheDocument();
    expect(screen.getByTestId("compounds-app-surface-header")).toHaveAttribute(
      "data-praviar-app-surface-header",
    );
    expect(
      screen
        .getByText("Compound Library")
        .closest(".praviar-report-decision-field"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Library matches")).toBeInTheDocument();
    expect(screen.getByText("Visible page")).toBeInTheDocument();
    expect(screen.getByText("Repeat dossiers")).toBeInTheDocument();
    expect(screen.getByText("Detail focus")).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Search compounds" }),
    ).toHaveClass("h-11");
    expect(
      screen.getByRole("textbox", { name: "Search compounds" }),
    ).not.toHaveClass("sm:h-9");
    expect(screen.getByText("Matching records")).toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: "Compound records horizontal scroll area",
      }),
    ).toHaveClass("md:overflow-x-auto");
    expect(
      screen.getByRole("region", {
        name: "Compound records horizontal scroll area",
      }),
    ).toHaveAttribute("tabindex", "0");
    expect(screen.getByText("Visible analyses")).toBeInTheDocument();
    expect(screen.getAllByText("Functional groups")[0]).toBeInTheDocument();
    expect(screen.getByText("Identity readiness")).toBeInTheDocument();
    expect(screen.getByText("Core identity complete")).toBeInTheDocument();
    expect(screen.getByText("PubChem linked")).toBeInTheDocument();
    expect(screen.getByText("Needs enrichment")).toBeInTheDocument();
    expect(screen.getByText("Private workspace")).toBeInTheDocument();
  });

  it("toggles the detail card when a row is selected", () => {
    renderPage();

    const detailsButton = screen.getByRole("button", {
      name: "Show details for Aspirin",
    });
    expect(detailsButton).toHaveClass("min-h-11");
    expect(detailsButton).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(detailsButton);
    expect(detailsButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Matched PubChem reference")).toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Open PubChem CID 2244 for Aspirin in PubChem",
      }),
    ).toHaveAttribute("href", "https://pubchem.ncbi.nlm.nih.gov/compound/2244");
    expect(screen.getByText("First analyzed in workspace")).toBeInTheDocument();
    expect(screen.getByText("Workspace analyses")).toBeInTheDocument();
    expect(screen.getByText("Functional Groups")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Close compound details" }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Hide details for Aspirin" }),
    );
    expect(
      screen.queryByText("Matched PubChem reference"),
    ).not.toBeInTheDocument();
  });

  it("shows the empty state after a search returns no compounds", async () => {
    vi.useFakeTimers();
    mockUseCompounds.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 20 },
      isLoading: false,
    });

    renderPage();

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search compounds" }),
      { target: { value: "zzz" } },
    );

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(
      screen.getByText("No compounds match this search"),
    ).toBeInTheDocument();
  });

  it("links empty compound libraries to the analysis launch flow", () => {
    mockUseCompounds.mockReturnValue({
      data: { items: [], total: 0, page: 1, per_page: 20 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText("No compounds yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New Analysis" })).toHaveAttribute(
      "href",
      "/analyses/new",
    );
  });

  it("renders pagination when more than one page exists", () => {
    mockUseCompounds.mockReturnValue({
      data: { items: compounds, total: 40, page: 1, per_page: 20 },
      isLoading: false,
    });

    renderPage();

    expect(
      screen.getAllByText("Showing 1-2 of 40 compounds")[0],
    ).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Previous compounds page" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Next compounds page" }),
    ).toBeEnabled();
  });

  it("shows a refresh state instead of impossible pagination for an empty page window", () => {
    mockUseCompounds.mockReturnValue({
      data: { items: [], total: 40, page: 2, per_page: 20 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText("Refreshing compound page")).toBeInTheDocument();
    expect(
      screen.getAllByText("Showing 0 of 40 compounds")[0],
    ).toBeInTheDocument();
    expect(screen.queryByText(/Showing 21-20/)).not.toBeInTheDocument();
    expect(screen.queryByText("No compounds yet")).not.toBeInTheDocument();
  });

  it("updates the visible range when moving through pages", async () => {
    mockUseCompounds.mockImplementation(
      (_token: string, page: number, perPage: number) => ({
        data: { items: compounds, total: 40, page, per_page: perPage },
        isLoading: false,
        isError: false,
        error: null,
        refetch: vi.fn(),
      }),
    );

    renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "Next compounds page" }),
    );

    await waitFor(() => {
      expect(mockUseCompounds).toHaveBeenLastCalledWith(
        "test-token",
        2,
        20,
        undefined,
      );
    });
    expect(
      screen.getAllByText("Showing 21-22 of 40 compounds")[0],
    ).toBeInTheDocument();
  });

  it("keeps pagination copy tied to the rendered data page", async () => {
    mockUseCompounds.mockReturnValue({
      data: { items: compounds, total: 40, page: 1, per_page: 20 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "Next compounds page" }),
    );

    await waitFor(() => {
      expect(mockUseCompounds).toHaveBeenLastCalledWith(
        "test-token",
        2,
        20,
        undefined,
      );
    });
    expect(
      screen.getAllByText("Showing 1-2 of 40 compounds")[0],
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Showing 21-22 of 40 compounds"),
    ).not.toBeInTheDocument();
  });

  it("shows an access-checking state while the compound library query is gated", () => {
    mockUseAuthToken.mockReturnValue(null);
    mockUseCompounds.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByText("Compound Library")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Checking compound library access",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No library data exposed")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("Search by name, SMILES, or InChI Key..."),
    ).not.toBeInTheDocument();
  });

  it("fails closed when a token is lost while previous compound data exists", () => {
    const view = renderPage();

    expect(screen.getByText("Aspirin")).toBeInTheDocument();

    mockUseAuthToken.mockReturnValue(null);
    mockUseCompounds.mockReturnValue({
      data: { items: compounds, total: 2, page: 1, per_page: 20 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    view.rerenderPage();

    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Checking compound library access",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Aspirin")).not.toBeInTheDocument();
    expect(
      screen.queryByText(compounds[0].canonical_smiles),
    ).not.toBeInTheDocument();
  });

  it("hides cached compound rows when a background access refresh is restricted", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseCompounds.mockReturnValue({
      data: { items: compounds, total: 2, page: 1, per_page: 20 },
      isLoading: false,
      isError: true,
      error: new APIError(403, "Forbidden"),
      refetch,
    });

    renderPage();

    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Compound library access restricted",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Aspirin")).not.toBeInTheDocument();
    expect(
      screen.queryByText(compounds[0].canonical_smiles),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry library load" }));

    expect(refetch).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledWith(
      "[CompoundsPage] Compound library access restricted",
    );
    consoleError.mockRestore();
  });

  it("shows a governed loading state before compound data arrives", () => {
    mockUseCompounds.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Loading compound library",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Showing 2 of 40 compounds"),
    ).not.toBeInTheDocument();
  });

  it("keeps existing compound rows visible during a background reload", () => {
    mockUseCompounds.mockReturnValue({
      data: { items: compounds, total: 40, page: 1, per_page: 20 },
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });

    renderPage();

    expect(
      screen.getAllByText("Showing 1-2 of 40 compounds")[0],
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        level: 2,
        name: "Loading compound library",
      }),
    ).not.toBeInTheDocument();
  });

  it("warns when existing compound rows are shown after a background refresh fails", () => {
    mockUseCompounds.mockReturnValue({
      data: { items: compounds, total: 40, page: 1, per_page: 20 },
      isLoading: false,
      isError: true,
      error: new Error("API error: 500 should stay hidden"),
      refetch: vi.fn(),
    });

    renderPage();

    expect(
      screen.getAllByText("Showing 1-2 of 40 compounds")[0],
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        level: 2,
        name: "Compound library temporarily unavailable",
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/API error: 500/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/Compound library refresh failed/i),
    ).toBeInTheDocument();
  });

  it("shows a safe retry state when compound library loading fails", () => {
    const refetch = vi.fn();
    const consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseCompounds.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("API error: 500 SELECT * FROM compounds"),
      refetch,
    });

    renderStrictPage();

    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Compound library temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/SELECT \*|API error: 500/),
    ).not.toBeInTheDocument();
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "[CompoundsPage] Failed to load compound library",
    );
    expect(consoleErrorSpy).toHaveBeenCalledTimes(1);
    expect(consoleErrorSpy).not.toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ message: expect.stringMatching(/SELECT \*/) }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry library load" }));

    expect(refetch).toHaveBeenCalledTimes(1);
    consoleErrorSpy.mockRestore();
  });

  it("debounces compound searches and trims the query sent to the API", async () => {
    vi.useFakeTimers();
    renderPage();

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search compounds" }),
      {
        target: { value: "  aspirin  " },
      },
    );

    act(() => {
      vi.advanceTimersByTime(299);
    });
    expect(mockUseCompounds).not.toHaveBeenCalledWith(
      "test-token",
      1,
      20,
      "aspirin",
    );

    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(mockUseCompounds).toHaveBeenLastCalledWith(
      "test-token",
      1,
      20,
      "aspirin",
    );
  });

  it("caps compound search input before sending it to the API", () => {
    vi.useFakeTimers();
    const overlongQuery = `CC(=O)OC1=CC=CC=C1${"C".repeat(
      MAX_COMPOUND_SEARCH_LENGTH + 40,
    )}`;
    const cappedQuery = overlongQuery.slice(0, MAX_COMPOUND_SEARCH_LENGTH);
    renderPage();

    const searchInput = screen.getByRole("textbox", {
      name: "Search compounds",
    });
    fireEvent.change(searchInput, { target: { value: overlongQuery } });

    expect(searchInput).toHaveValue(cappedQuery);
    expect(screen.getByLabelText("Compound search length")).toHaveTextContent(
      `${MAX_COMPOUND_SEARCH_LENGTH} / ${MAX_COMPOUND_SEARCH_LENGTH}`,
    );

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(mockUseCompounds).toHaveBeenLastCalledWith(
      "test-token",
      1,
      20,
      cappedQuery,
    );
  });

  it("cancels a pending debounced query when compound search is cleared", () => {
    vi.useFakeTimers();
    renderPage();

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search compounds" }),
      {
        target: { value: "zzz" },
      },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Clear compound search" }),
    );

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(mockUseCompounds).not.toHaveBeenCalledWith(
      "test-token",
      1,
      20,
      "zzz",
    );
    expect(mockUseCompounds).toHaveBeenLastCalledWith(
      "test-token",
      1,
      20,
      undefined,
    );
  });

  it("contains long active compound search chips and returns focus when cleared", () => {
    const longQuery = `C1=CC=CC=C1C(=O)OCCN${"C".repeat(180)}`;
    const displayedQuery = longQuery.slice(0, MAX_COMPOUND_SEARCH_LENGTH);

    renderPage();

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search compounds" }),
      {
        target: { value: longQuery },
      },
    );

    const searchChipLabel = `Search: ${displayedQuery}`;
    const activeFilters = screen.getByRole("group", {
      name: "Active compound filters",
    });
    const searchChip = screen.getByLabelText(searchChipLabel);
    const searchChipText = screen.getByText(searchChipLabel);

    expect(activeFilters).toHaveClass("min-w-0", "max-w-full", "flex-wrap");
    expect(searchChip).toHaveClass("max-w-full", "min-w-0");
    expect(searchChip).toHaveAttribute("title", searchChipLabel);
    expect(searchChipText).toHaveClass("min-w-0", "truncate");

    const clearButton = screen.getByRole("button", {
      name: "Clear compound search",
    });
    clearButton.focus();
    fireEvent.click(clearButton);

    expect(
      screen.getByRole("textbox", { name: "Search compounds" }),
    ).toHaveFocus();
    expect(
      screen.getByRole("textbox", { name: "Search compounds" }),
    ).toHaveValue("");
  });

  it("keeps compound search focused and mounted while filtered results load", () => {
    vi.useFakeTimers();
    mockUseCompounds.mockImplementation(
      (_token: string, page: number, perPage: number, searchQuery?: string) => {
        if (searchQuery) {
          return {
            data: undefined,
            isLoading: true,
            isError: false,
            error: null,
            refetch: vi.fn(),
          };
        }

        return {
          data: { items: compounds, total: 2, page, per_page: perPage },
          isLoading: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        };
      },
    );

    renderPage();

    const searchInput = screen.getByRole("textbox", {
      name: "Search compounds",
    });
    searchInput.focus();
    fireEvent.change(searchInput, { target: { value: "aspirin" } });

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(
      screen.getByRole("textbox", { name: "Search compounds" }),
    ).toHaveFocus();
    expect(
      screen.getByRole("textbox", { name: "Search compounds" }),
    ).toHaveValue("aspirin");
    expect(screen.getByText("Loading matching compounds")).toBeInTheDocument();
  });

  it("keeps controls mounted during an uncached page fetch", async () => {
    mockUseCompounds.mockImplementation(
      (_token: string, page: number, perPage: number) => {
        if (page === 2) {
          return {
            data: undefined,
            isLoading: true,
            isError: false,
            error: null,
            refetch: vi.fn(),
          };
        }

        return {
          data: { items: compounds, total: 40, page, per_page: perPage },
          isLoading: false,
          isError: false,
          error: null,
          refetch: vi.fn(),
        };
      },
    );

    renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "Next compounds page" }),
    );

    await waitFor(() => {
      expect(mockUseCompounds).toHaveBeenLastCalledWith(
        "test-token",
        2,
        20,
        undefined,
      );
    });
    expect(
      screen.getByRole("textbox", { name: "Search compounds" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Loading compound records")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        level: 2,
        name: "Loading compound library",
      }),
    ).not.toBeInTheDocument();
  });

  it("retains selected compound state through transient loading gaps", () => {
    const view = renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "Show details for Aspirin" }),
    );
    expect(screen.getByText("Matched PubChem reference")).toBeInTheDocument();

    mockUseCompounds.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    view.rerenderPage();

    mockUseCompounds.mockReturnValue({
      data: { items: compounds, total: 2, page: 1, per_page: 20 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    view.rerenderPage();

    expect(screen.getByText("Matched PubChem reference")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Hide details for Aspirin" }),
    ).toHaveAttribute("aria-expanded", "true");
  });

  it("uses distinct copy controls and resets copied state between compounds", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });

    renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "Show details for Aspirin" }),
    );
    expect(
      screen.getByRole("button", { name: "Copy SMILES" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Copy InChI Key" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy SMILES" }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(compounds[0].canonical_smiles);
    });
    expect(
      screen.getByRole("button", { name: "SMILES copied" }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Show details for Ibuprofen" }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Copy SMILES" }),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: "SMILES copied" }),
    ).not.toBeInTheDocument();

    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
    });
  });

  it("preserves long compound metadata while preventing orphan wraps in mobile cards", () => {
    const longName = `N-(4-hydroxyphenyl)-${"very-long-compound-".repeat(8)}`;
    const longSmiles = `CC(=O)OC1=CC=CC=C1C(=O)O${"C".repeat(120)}`;
    const longGroup = `macrocyclic-polyfunctionalized-carboxamide-${"x".repeat(120)}`;

    mockUseCompounds.mockReturnValue({
      data: {
        items: [
          {
            ...compounds[0],
            name: longName,
            canonical_smiles: longSmiles,
            functional_groups: [longGroup, " ester ", "amide", "Ester"],
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

    renderPage();

    const tableName = screen.getByText(longName);
    const tableSmiles = screen.getByText(longSmiles);
    const tableGroup = screen.getByText(longGroup);
    expect(tableName).toHaveAttribute("title", longName);
    expect(tableName).toHaveClass("break-words", "[overflow-wrap:anywhere]");
    expect(tableSmiles).toHaveAttribute("title", longSmiles);
    expect(tableSmiles).toHaveClass(
      "max-w-full",
      "overflow-hidden",
      "text-ellipsis",
      "whitespace-nowrap",
    );
    expect(tableSmiles.closest("p")).toHaveAttribute(
      "aria-label",
      `SMILES: ${longSmiles}`,
    );
    expect(tableGroup).toHaveAttribute("title", longGroup);
    expect(tableGroup).toHaveAttribute(
      "aria-label",
      `Functional group: ${longGroup}`,
    );
    expect(tableGroup).toHaveClass(
      "max-w-full",
      "overflow-hidden",
      "text-ellipsis",
      "whitespace-nowrap",
    );
    expect(screen.getByText("+1")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: `Show details for ${longName}` }),
    );

    const detailGroup = screen.getAllByText(longGroup).at(-1)!;
    expect(detailGroup).toHaveClass(
      "max-w-full",
      "whitespace-normal",
      "break-words",
      "[overflow-wrap:break-word]",
      "[word-break:normal]",
    );
  });

  it("clears stale selected compound details when the result page changes", () => {
    vi.useFakeTimers();
    const view = renderPage();

    fireEvent.click(
      screen.getByRole("button", { name: "Show details for Aspirin" }),
    );
    expect(screen.getByText("Matched PubChem reference")).toBeInTheDocument();

    mockUseCompounds.mockReturnValue({
      data: { items: [compounds[1]], total: 1, page: 1, per_page: 20 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    view.rerenderPage();

    act(() => {
      vi.runOnlyPendingTimers();
    });

    mockUseCompounds.mockReturnValue({
      data: { items: compounds, total: 2, page: 1, per_page: 20 },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
    view.rerenderPage();

    expect(
      screen.queryByText("Matched PubChem reference"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Show details for Aspirin" }),
    ).toHaveAttribute("aria-expanded", "false");
  });

  it("formats compound library dates in UTC", () => {
    mockUseCompounds.mockReturnValue({
      data: {
        items: [
          {
            ...compounds[0],
            first_analyzed_at: "2026-03-20T00:30:00Z",
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

    renderPage();

    expect(screen.getAllByText("Mar 20, 2026")[0]).toBeInTheDocument();
  });
});
