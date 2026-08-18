import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ShareStatusState } from "@/app/share/[token]/share-status-state";

describe("ShareStatusState", () => {
  it("renders a specific temporary-unavailable state", () => {
    render(<ShareStatusState variant="error" onRetry={vi.fn()} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Shared report temporarily unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Ask the sender to confirm the link/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Something Went Wrong/i)).not.toBeInTheDocument();
    expect(
      screen.getByText("Retry or share this reference"),
    ).toBeInTheDocument();
    expect(screen.getByText("Share access check")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(
      screen.getByText(/do not send the private share token/i),
    ).toBeInTheDocument();

    const stepStates = Array.from(
      screen
        .getByRole("alert")
        .querySelectorAll("[data-praviar-share-access-step-state]"),
    ).map((step) => step.getAttribute("data-praviar-share-access-step-state"));
    expect(stepStates).toEqual(["verified", "issue", "attention"]);
    expect(
      within(screen.getByRole("alert")).getByText("Access check started"),
    ).toBeInTheDocument();
  });

  it("renders an expired-link state with sender recovery copy", () => {
    render(<ShareStatusState variant="expired" />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Share link expired" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/generate a fresh link from the report workspace/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Request a fresh link")).toBeInTheDocument();

    const stepStates = Array.from(
      screen
        .getByRole("alert")
        .querySelectorAll("[data-praviar-share-access-step-state]"),
    ).map((step) => step.getAttribute("data-praviar-share-access-step-state"));
    expect(stepStates).toEqual(["verified", "verified", "attention"]);
  });

  it("allows password-gate failures to pass a precise unavailable reason", () => {
    render(
      <ShareStatusState
        variant="not-found"
        description="This share link has expired."
      />,
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "Report not available" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("This share link has expired."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Confirm the link with the sender"),
    ).toBeInTheDocument();
  });
});
