import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  AnalysisAuthState,
  AnalysisErrorState,
  AnalysisLoadingState,
  AnalysisNotFoundState,
} from "@/components/analysis-detail/analysis-states";

describe("analysis detail status states", () => {
  it("renders auth resolution without implying a missing analysis", () => {
    const { container } = render(<AnalysisAuthState />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(container.querySelector("[data-praviar-mark-frame]")).toBeTruthy();
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Checking analysis access",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No analysis data exposed")).toBeInTheDocument();
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  });

  it("renders a governed loading state with analysis-specific context", () => {
    render(<AnalysisLoadingState />);

    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Loading analysis workspace",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Pipeline status requested")).toBeInTheDocument();
    expect(screen.getByText("Report actions wait")).toBeInTheDocument();
  });

  it("renders temporary failures without exposing raw IDs or diagnostics", () => {
    const onRetry = vi.fn();
    render(<AnalysisErrorState onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Analysis temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No analysis data changed")).toBeInTheDocument();
    expect(screen.queryByText(/ana_/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        /database|api error|forbidden|bearer|traceback|org_id|select \*/i,
      ),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry analysis load" }),
    );

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders unavailable analysis as a neutral team-scoped state", () => {
    render(<AnalysisNotFoundState />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Analysis unavailable in this workspace",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Team-scoped access")).toBeInTheDocument();
    expect(screen.getByText("No analysis data exposed")).toBeInTheDocument();
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to Analyses" }),
    ).toHaveAttribute("href", "/analyses");
  });
});
