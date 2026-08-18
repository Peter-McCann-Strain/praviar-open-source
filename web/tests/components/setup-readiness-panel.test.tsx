import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockUseSetupReadiness = vi.fn();

vi.mock("@/hooks/use-setup-readiness", () => ({
  useSetupReadiness: (...args: unknown[]) => mockUseSetupReadiness(...args),
}));

import { SetupReadinessPanel } from "@/components/dashboard/setup-readiness-panel";

describe("SetupReadinessPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.__praviarAnalyticsQueue = [];
    mockUseSetupReadiness.mockReturnValue({
      data: {
        overall_status: "action_required",
        current_user_role: "attorney",
        completed_items: 1,
        applicable_items: 2,
        observed_at: "2026-07-13T10:00:00Z",
        items: [
          {
            id: "identity",
            label: "Identity and organization",
            description: "Confirm the tenant boundary.",
            status: "complete",
            owner: "Workspace administrator",
            recovery_label: "Ask a workspace administrator",
            recovery_href: null,
            evidence: "The persisted identity and organization agree.",
          },
          {
            id: "first_analysis",
            label: "First analysis",
            description: "Complete the first governed workflow.",
            status: "action_required",
            owner: "Analysis team",
            recovery_label: "Start an analysis",
            recovery_href: "/analyses/new",
            evidence: "No completed analysis was found.",
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  it("shows authoritative evidence, progress, owners, and actionable recovery", () => {
    render(<SetupReadinessPanel token="token" />);

    expect(mockUseSetupReadiness).toHaveBeenCalledWith("token");
    expect(
      screen.getByRole("region", { name: "Workspace launch checklist" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Workspace launch checklist",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", { name: "Workspace setup readiness" }),
    ).toHaveAttribute("aria-valuenow", "1");
    expect(
      screen.getByText("1 of 2 applicable checks verified"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No completed analysis was found."),
    ).toBeInTheDocument();
    expect(screen.getByText("2026-07-13 10:00 UTC")).toBeInTheDocument();
    const startAnalysisLink = screen.getByRole("link", {
      name: /Start an analysis/,
    });
    expect(startAnalysisLink).toHaveAttribute("href", "/analyses/new");
    expect(startAnalysisLink).toHaveClass("min-h-11");
  });

  it("renders non-admin ownership guidance without a dead-end admin link", () => {
    render(<SetupReadinessPanel token="token" />);

    expect(
      screen.getByText("Ask a workspace administrator"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Ask a workspace administrator" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /workspace settings/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps populated-dashboard details collapsed behind an accessible summary", () => {
    render(<SetupReadinessPanel token="token" compact />);

    const details = screen.getByTestId("setup-readiness-details");
    expect(details).not.toHaveAttribute("open");
    expect(
      screen.getByText("Review setup evidence and recovery actions"),
    ).toBeVisible();
  });

  it("fails closed and retries when the server snapshot is unavailable", () => {
    const refetch = vi.fn();
    mockUseSetupReadiness.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch,
    });

    render(<SetupReadinessPanel token="token" />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "No checklist item is marked complete",
    );
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Setup verification unavailable",
      }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Retry setup verification" }),
    );
    expect(refetch).toHaveBeenCalledOnce();
    expect(
      screen.getByRole("button", { name: "Retry setup verification" }),
    ).toHaveClass("min-h-11");
  });
});
