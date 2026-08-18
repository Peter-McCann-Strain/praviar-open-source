import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HelpPage from "@/app/(dashboard)/help/page";
import { getHelpResultCounts } from "@/components/help/helpers";

const principalState = vi.hoisted(() => ({
  capabilities: {} as Record<string, boolean | string>,
}));

const ADMIN_CAPABILITIES = {
  role: "admin",
  can_create_analysis: true,
  can_view_patents: true,
  can_manage_monitors: true,
  can_view_review_queue: true,
  can_assign_review: true,
  can_resolve_review: true,
  can_escalate_review: true,
  can_create_batch: true,
  can_manage_config: true,
  can_export_report: true,
  can_share_report: true,
  can_deliver_report: true,
  can_view_billing: true,
  can_manage_billing: true,
  can_manage_api_keys: true,
  can_view_platform_admin: true,
  risk_ratings_restricted: false,
  api_key_report_export_scope_available: false,
};

const CLIENT_CAPABILITIES = {
  role: "client",
  can_create_analysis: false,
  can_view_patents: false,
  can_manage_monitors: false,
  can_view_review_queue: false,
  can_assign_review: false,
  can_resolve_review: false,
  can_escalate_review: false,
  can_create_batch: false,
  can_manage_config: false,
  can_export_report: false,
  can_share_report: false,
  can_deliver_report: false,
  can_view_billing: true,
  can_manage_billing: false,
  can_manage_api_keys: false,
  can_view_platform_admin: false,
  risk_ratings_restricted: true,
  api_key_report_export_scope_available: false,
};

vi.mock("@/hooks/use-auth-token", () => ({
  useAuthToken: () => "token",
}));

vi.mock("@/hooks/use-principal-capabilities", async () => {
  const actual = await vi.importActual<
    typeof import("@/hooks/use-principal-capabilities")
  >("@/hooks/use-principal-capabilities");
  return {
    ...actual,
    usePrincipalCapabilities: () => ({
      data: principalState.capabilities,
    }),
  };
});

beforeEach(() => {
  principalState.capabilities = { ...ADMIN_CAPABILITIES };
});

describe("HelpPage", () => {
  it("renders a premium command layer for default workflow routing", () => {
    const { container } = render(<HelpPage />);

    const header = screen.getByTestId("help-app-surface-header");
    expect(header).toHaveAttribute(
      "data-praviar-app-surface-density",
      "compact",
    );
    expect(header).toHaveClass(
      "max-[359px]:[&_[data-praviar-mark-frame]]:hidden",
    );
    expect(header.querySelector("[data-praviar-mark-frame]")).toHaveClass(
      "h-10",
      "w-10",
    );
    expect(screen.getByText("Help command layer")).toBeInTheDocument();
    expect(
      screen.getByText("Start from the workflow, not the manual"),
    ).toBeInTheDocument();
    const commandLayer = screen.getByRole("region", {
      name: "Start from the workflow, not the manual",
    });
    expect(within(commandLayer).getByText("Task routed")).toBeInTheDocument();
    expect(within(commandLayer).getByText("Command brief")).toBeInTheDocument();
    expect(
      within(commandLayer).getByText("Route, verify, hand off"),
    ).toBeInTheDocument();
    expect(within(commandLayer).getByText("Role routes")).toBeInTheDocument();
    expect(within(commandLayer).getByText("4")).toBeInTheDocument();
    expect(within(commandLayer).getByText("Evidence map")).toBeInTheDocument();
    expect(within(commandLayer).getByText("8 steps")).toBeInTheDocument();
    expect(within(commandLayer).getByText("Handoff paths")).toBeInTheDocument();
    expect(within(commandLayer).getByText("3")).toBeInTheDocument();
    expect(within(commandLayer).getByText("4 actions")).toBeInTheDocument();
    expect(
      within(commandLayer).getByRole("link", {
        name: /Counsel Verify material risk/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Inspect billing architecture/i }),
    ).toHaveAttribute("href", "/billing");
    expect(
      screen.getByRole("navigation", { name: "Help sections" }),
    ).toHaveTextContent("Common Tasks");
    for (const link of within(
      screen.getByRole("navigation", { name: "Help sections" }),
    ).getAllByRole("link")) {
      expect(link).toHaveClass("min-h-11");
    }
    expect(
      container.querySelectorAll("[data-help-command-layer] a a"),
    ).toHaveLength(0);
    expect(container.querySelector("main")).toBeNull();
    expect(container.querySelector("aside")).toBeNull();
  });

  it("keeps visible help sections aligned with the search result summary", () => {
    render(<HelpPage />);

    const search = screen.getByRole("textbox", { name: "Search help topics" });

    fireEvent.change(search, {
      target: { value: "zzzz no matching help topic" },
    });

    expect(
      screen.getByText(/No results for "zzzz no matching help topic"/),
    ).toBeInTheDocument();
    expect(screen.getByText(/No matching help guidance/)).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Help sections" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Start from the workflow, not the manual"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Command brief")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Three steps to your first FTO analysis"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Support posture")).not.toBeInTheDocument();
  });

  it("filters shortcut results to the matching command", () => {
    render(<HelpPage />);

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search help topics" }),
      {
        target: { value: "Ctrl+K" },
      },
    );

    expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
    expect(screen.getByText("Open command palette")).toBeInTheDocument();
    expect(screen.queryByText("Close modal or panel")).not.toBeInTheDocument();
    expect(screen.getByText(/1 matching result/)).toBeInTheDocument();
  });

  it("promotes matching workflow actions before explanatory FAQ content", () => {
    render(<HelpPage />);

    const search = screen.getByRole("textbox", { name: "Search help topics" });
    fireEvent.change(search, {
      target: { value: "credit" },
    });

    const creditWorkflow = screen.getByRole("link", {
      name: /Inspect billing architecture/i,
    });
    const billingFaq = screen.getByRole("button", {
      name: "How do credits and billing work?",
    });

    expect(
      search.compareDocumentPosition(creditWorkflow) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      creditWorkflow.compareDocumentPosition(billingFaq) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("makes visible help section labels searchable", () => {
    render(<HelpPage />);

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search help topics" }),
      {
        target: { value: "keyboard shortcuts" },
      },
    );

    expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
    expect(screen.getByText("Open command palette")).toBeInTheDocument();
    expect(screen.getByText("Close modal or panel")).toBeInTheDocument();
    expect(screen.queryByText("Getting Started")).not.toBeInTheDocument();
  });

  it("keeps focused getting-started searches from overpromising three steps", () => {
    render(<HelpPage />);

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search help topics" }),
      {
        target: { value: "Enter a compound" },
      },
    );

    expect(
      screen.getByText("Matching setup guidance for your first FTO analysis"),
    ).toBeInTheDocument();
    expect(screen.getByText("Enter a compound")).toBeInTheDocument();
    expect(
      screen.queryByText("Three steps to your first FTO analysis"),
    ).not.toBeInTheDocument();
  });

  it("keeps deployment-support searches focused on honest support boundaries", () => {
    render(<HelpPage />);

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search help topics" }),
      {
        target: { value: "deployment operator" },
      },
    );

    expect(screen.getByText("Not published in preview")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Review deployment boundary" }),
    ).toHaveAttribute("href", "/trust#assurance-heading");
    expect(screen.getByText(/2 matching results/)).toBeInTheDocument();
    expect(
      screen.queryByText("Move from guidance to action"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Help command layer")).not.toBeInTheDocument();
  });

  it("keeps focused audience searches on the matching route", () => {
    render(<HelpPage />);

    fireEvent.change(
      screen.getByRole("textbox", { name: "Search help topics" }),
      {
        target: { value: "attorney" },
      },
    );

    expect(screen.getByText("1 route match")).toBeInTheDocument();
    expect(screen.getByText("Verify material risk")).toBeInTheDocument();
    expect(
      screen.queryByText("Understand compound inputs"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Command brief")).not.toBeInTheDocument();
  });

  it("pins help result counts for task, support, and monitoring queries", () => {
    expect(getHelpResultCounts("settings")).toMatchObject({
      audience: 1,
      support: 1,
      total: 2,
      workflows: 0,
    });
    expect(getHelpResultCounts("deployment operator")).toMatchObject({
      audience: 0,
      contact: 1,
      support: 1,
      total: 2,
    });
    expect(getHelpResultCounts("monitoring")).toMatchObject({
      faq: 0,
      risks: 1,
      support: 1,
      total: 2,
    });
    expect(getHelpResultCounts("credit")).toMatchObject({
      faq: 1,
      total: 2,
      workflows: 1,
    });
  });

  it("shows clients only workflows they can actually use", () => {
    principalState.capabilities = { ...CLIENT_CAPABILITIES };

    render(<HelpPage />);

    expect(
      screen.queryByRole("link", { name: "Start analysis" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Inspect billing architecture/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Open admin settings/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Review deployment boundary" }),
    ).toHaveAttribute("href", "/trust#assurance-heading");
  });
});
