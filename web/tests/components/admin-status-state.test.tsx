import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  AdminRefreshWarning,
  AdminStatusState,
  relativeTime,
} from "@/components/admin-dashboard/helpers";

describe("admin formatting helpers", () => {
  it("handles invalid and future timestamps without misleading output", () => {
    const now = vi
      .spyOn(Date, "now")
      .mockReturnValue(new Date("2026-07-25T12:00:00.000Z").getTime());

    expect(relativeTime("not-a-date")).toBe("Unknown");
    expect(relativeTime("2026-07-26T12:00:00.000Z")).toBe("Scheduled");
    expect(relativeTime("2026-07-25T11:30:00.000Z")).toBe("30m ago");

    now.mockRestore();
  });
});

describe("AdminStatusState", () => {
  it("renders loading as a polite busy admin status", () => {
    const { container } = render(
      <AdminStatusState surface="users" variant="loading" />,
    );

    const state = screen.getByTestId("admin-users-status-loading");
    expect(state).toHaveAttribute("data-praviar-status-frame");
    expect(state).toHaveClass("praviar-operational-field", "scroll-mt-20");
    expect(state).not.toHaveClass("praviar-report-decision-field");
    const liveRegion = screen.getByRole("status");
    expect(liveRegion).toHaveAttribute("aria-live", "polite");
    expect(liveRegion).toHaveAttribute("aria-busy", "true");
    expect(liveRegion).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", { name: "Loading user controls" }),
    ).toBeInTheDocument();
    expect(container.querySelector("svg.animate-spin")).toHaveClass(
      "h-5",
      "w-5",
      "sm:h-6",
      "sm:w-6",
      "motion-reduce:animate-none",
    );
  });

  it("renders temporary failures without backend details and wires retry", () => {
    const onRetry = vi.fn();
    render(
      <AdminStatusState
        surface="audit-logs"
        variant="temporary"
        onRetry={onRetry}
      />,
    );

    expect(
      screen.getByTestId("admin-audit-logs-status-temporary"),
    ).toHaveAttribute("data-praviar-status-frame");
    expect(screen.getByRole("alert")).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", {
        name: "Audit log temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Detail:|ECONNREFUSED|database password/i),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry admin load" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders restricted admin access as an assertive fail-closed alert", () => {
    const onRetry = vi.fn();
    render(
      <AdminStatusState
        surface="organizations"
        variant="restricted"
        onRetry={onRetry}
      />,
    );

    expect(
      screen.getByTestId("admin-organizations-status-restricted"),
    ).toHaveClass("scroll-mt-20");
    const state = screen.getByTestId("admin-organizations-status-restricted");
    expect(state.firstElementChild).toHaveClass("py-3", "sm:py-5");
    expect(state.children[1]?.children[0]).toHaveClass("p-3", "sm:p-6");
    expect(state.children[1]?.children[1]).toHaveClass("p-3", "sm:p-6");
    const liveRegion = screen.getByRole("alert");
    expect(liveRegion).toHaveAttribute("aria-live", "assertive");
    expect(liveRegion).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", {
        name: "Organization controls access restricted",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Cached admin data hidden")).toBeInTheDocument();
    expect(
      screen.queryByText(/Acme Therapeutics|database password|Detail:/i),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry admin load" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("AdminRefreshWarning", () => {
  it("announces stale admin data without raw diagnostics", () => {
    render(<AdminRefreshWarning label="User controls" />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "User controls refresh failed",
    );
    expect(
      screen.queryByText(/Failed to fetch|database/i),
    ).not.toBeInTheDocument();
  });
});
