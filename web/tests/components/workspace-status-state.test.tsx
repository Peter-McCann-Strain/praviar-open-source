import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceStatusState } from "@/components/shared/workspace-status-state";

describe("WorkspaceStatusState", () => {
  it("renders loading as a polite busy status", () => {
    const { container } = render(
      <WorkspaceStatusState surface="batch" variant="loading" />,
    );

    const state = screen.getByTestId("batch-workspace-status-loading");
    expect(state).toHaveAttribute("data-praviar-status-frame");
    const liveRegion = screen.getByRole("status");
    expect(liveRegion).toHaveAttribute("aria-live", "polite");
    expect(liveRegion).toHaveAttribute("aria-busy", "true");
    expect(liveRegion).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", {
        name: "Loading diligence portfolio workspace",
      }),
    ).toBeInTheDocument();
    expect(container.querySelector("svg.animate-spin")).toHaveClass(
      "motion-reduce:animate-none",
    );
  });

  it("renders temporary failures as safe alerts without backend details", () => {
    const onRetry = vi.fn();
    render(
      <WorkspaceStatusState
        surface="monitors"
        variant="temporary"
        onRetry={onRetry}
      />,
    );

    const state = screen.getByTestId("monitors-workspace-status-temporary");
    expect(state).toHaveAttribute("data-praviar-status-frame");
    const liveRegion = screen.getByRole("alert");
    expect(liveRegion).toHaveAttribute("aria-live", "assertive");
    expect(liveRegion).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", {
        name: "Patent monitoring temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Failed to fetch|ECONNREFUSED|Detail:/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI recovery brief" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Keep monitor schedules and watch targets unchanged/),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry workspace load" }),
    );
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders restricted access as an assertive fail-closed alert", () => {
    const onRetry = vi.fn();
    render(
      <WorkspaceStatusState
        surface="batch"
        variant="restricted"
        onRetry={onRetry}
      />,
    );

    const state = screen.getByTestId("batch-workspace-status-restricted");
    expect(state).toHaveAttribute("data-praviar-status-frame");
    const liveRegion = screen.getByRole("alert");
    expect(liveRegion).toHaveAttribute("aria-live", "assertive");
    expect(liveRegion).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", {
        name: "Diligence portfolio workspace access restricted",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Cached records hidden")).toBeInTheDocument();
    expect(
      screen.queryByText(/batch-1|database|Forbidden|Detail:/i),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Retry workspace load" }),
    );
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
