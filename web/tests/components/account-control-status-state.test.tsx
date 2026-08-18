import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountControlStatusState } from "@/components/shared/account-control-status-state";

describe("AccountControlStatusState", () => {
  it("renders loading as a polite busy status", () => {
    render(<AccountControlStatusState surface="settings" variant="loading" />);

    const state = screen.getByTestId("settings-account-control-loading");
    expect(state).toHaveAttribute("data-praviar-status-frame");
    expect(state).toHaveClass("praviar-operational-field");
    expect(state).not.toHaveClass("praviar-report-decision-field");
    const liveRegion = screen.getByRole("status");
    expect(liveRegion).toHaveAttribute("aria-live", "polite");
    expect(liveRegion).toHaveAttribute("aria-busy", "true");
    expect(liveRegion).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", { name: "Loading API key settings" }),
    ).toBeInTheDocument();
  });

  it("renders temporary failures without backend details and wires retry", () => {
    const onRetry = vi.fn();
    render(
      <AccountControlStatusState
        surface="billing"
        variant="temporary"
        onRetry={onRetry}
      />,
    );

    const state = screen.getByTestId("billing-account-control-temporary");
    expect(state).toHaveAttribute("data-praviar-status-frame");
    expect(screen.getByRole("alert")).toHaveAttribute("aria-atomic", "true");
    expect(
      screen.getByRole("heading", {
        name: "Billing controls temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Detail:|Failed to fetch|ECONNREFUSED/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "AI recovery brief" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Keep plan, invoice, and Report Credit records unchanged/,
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry control load" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
