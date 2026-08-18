import { afterEach, describe, it, expect, vi } from "vitest";
import { act, render, screen, fireEvent } from "@testing-library/react";
import { ReportSearchBar } from "@/components/report/report-search-bar";
import { emitAuthBoundaryChanged } from "@/lib/auth-events";

afterEach(() => {
  vi.useRealTimers();
});

describe("ReportSearchBar", () => {
  it("renders search input", () => {
    render(<ReportSearchBar onSearch={vi.fn()} onClear={vi.fn()} />);
    expect(
      screen.getByRole("search", { name: "Search reviewed report evidence" }),
    ).toHaveAttribute("data-praviar-report-search");
    expect(
      screen.getByRole("search", { name: "Search reviewed report evidence" }),
    ).toHaveAttribute("data-no-print");
    expect(screen.getByLabelText("Search report")).toHaveAttribute(
      "placeholder",
      "Search reviewed evidence",
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Search reviewed report evidence only.",
    );
    expect(screen.getByLabelText("Search report")).toHaveAccessibleDescription(
      "Search reviewed report evidence only.",
    );
  });

  it("seeds the visible query from a URL-provided initial value", () => {
    render(
      <ReportSearchBar
        onSearch={vi.fn()}
        onClear={vi.fn()}
        initialQuery="blocking claim elements"
      />,
    );

    expect(screen.getByLabelText("Search report")).toHaveValue(
      "blocking claim elements",
    );
    expect(screen.getByLabelText("Clear search")).toBeInTheDocument();
  });

  it("shows clear button when query entered", () => {
    render(<ReportSearchBar onSearch={vi.fn()} onClear={vi.fn()} />);
    const input = screen.getByLabelText("Search report");
    fireEvent.change(input, { target: { value: "test query" } });
    expect(screen.getByLabelText("Clear search")).toHaveClass("h-11", "w-11");
  });

  it("shows spinner when searching", () => {
    const { container } = render(
      <ReportSearchBar onSearch={vi.fn()} onClear={vi.fn()} isSearching />,
    );
    expect(container.querySelector(".animate-spin")).toBeTruthy();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Searching reviewed evidence.",
    );
  });

  it("shows interpreted query", () => {
    render(
      <ReportSearchBar
        onSearch={vi.fn()}
        onClear={vi.fn()}
        interpretedQuery='Searching for: "test"'
        resultCount={3}
      />,
    );
    expect(screen.getByText(/Searching for/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Reviewed evidence only:",
    );
    expect(screen.getByRole("status")).toHaveClass("[overflow-wrap:anywhere]");
    expect(screen.getByText("(3 results)")).toBeInTheDocument();
    expect(screen.getByLabelText("Search report")).toHaveAccessibleDescription(
      /Reviewed evidence only:/,
    );
  });

  it("announces zero interpreted results when provided", () => {
    render(
      <ReportSearchBar
        onSearch={vi.fn()}
        onClear={vi.fn()}
        interpretedQuery='Searching for: "no blockers"'
        resultCount={0}
      />,
    );

    expect(screen.getByText("(0 results)")).toBeInTheDocument();
  });

  it("renders safe search errors as alerts", () => {
    render(
      <ReportSearchBar
        onSearch={vi.fn()}
        onClear={vi.fn()}
        error="Search could not be completed. Existing report view is unchanged."
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Search could not be completed. Existing report view is unchanged.",
    );
    expect(screen.getByLabelText("Search report")).toHaveAccessibleDescription(
      /Search could not be completed. Existing report view is unchanged./,
    );
  });

  it("trims debounced searches before submitting them", () => {
    vi.useFakeTimers();
    const onSearch = vi.fn();

    render(<ReportSearchBar onSearch={onSearch} onClear={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Search report"), {
      target: { value: "  claim 1 fermentation route  " },
    });

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(onSearch).toHaveBeenCalledWith("claim 1 fermentation route");
  });

  it("submits a publication ID immediately on Enter and cancels the debounce", () => {
    vi.useFakeTimers();
    const onSearch = vi.fn();

    render(<ReportSearchBar onSearch={onSearch} onClear={vi.fn()} />);

    const input = screen.getByLabelText("Search report");
    fireEvent.change(input, { target: { value: "  WO2011123645  " } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onSearch).toHaveBeenCalledTimes(1);
    expect(onSearch).toHaveBeenCalledWith("WO2011123645");

    act(() => {
      vi.advanceTimersByTime(350);
    });
    expect(onSearch).toHaveBeenCalledTimes(1);
  });

  it("clears query text, cancels pending search, and returns focus", () => {
    vi.useFakeTimers();
    const onSearch = vi.fn();
    const onClear = vi.fn();

    render(<ReportSearchBar onSearch={onSearch} onClear={onClear} />);

    const input = screen.getByLabelText("Search report");
    fireEvent.change(input, { target: { value: "private patent query" } });
    input.focus();
    fireEvent.click(screen.getByLabelText("Clear search"));

    act(() => {
      vi.advanceTimersByTime(350);
    });

    expect(input).toHaveValue("");
    expect(input).toHaveFocus();
    expect(onClear).toHaveBeenCalledTimes(1);
    expect(onSearch).not.toHaveBeenCalled();
  });

  it("clears private query text and cancels pending search on auth boundary changes", () => {
    vi.useFakeTimers();
    const onSearch = vi.fn();
    const onClear = vi.fn();

    render(<ReportSearchBar onSearch={onSearch} onClear={onClear} />);

    const input = screen.getByLabelText("Search report");
    fireEvent.change(input, { target: { value: "private patent query" } });

    expect(input).toHaveValue("private patent query");
    expect(screen.getByLabelText("Clear search")).toBeInTheDocument();

    act(() => {
      emitAuthBoundaryChanged({ refreshToken: false });
    });
    act(() => {
      vi.advanceTimersByTime(350);
    });

    expect(input).toHaveValue("");
    expect(onClear).toHaveBeenCalledTimes(1);
    expect(onSearch).not.toHaveBeenCalled();
  });
});
