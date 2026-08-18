import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEMO_COUNSEL_WORKSPACE_HREF } from "@/components/capabilities/capability-catalog";

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

async function renderCapabilitiesPage({
  demoMode = true,
  devAuthBypass = false,
  role = "admin",
}: {
  demoMode?: boolean;
  devAuthBypass?: boolean;
  role?: "admin" | "client";
} = {}) {
  principalState.capabilities = {
    ...(role === "client" ? CLIENT_CAPABILITIES : ADMIN_CAPABILITIES),
  };
  vi.resetModules();
  vi.doMock("@/lib/constants", () => ({
    DEMO_MODE_ENABLED: demoMode,
    DEV_AUTH_BYPASS_ENABLED: devAuthBypass,
  }));

  const { default: CapabilitiesPage } =
    await import("@/app/(dashboard)/capabilities/page");
  render(<CapabilitiesPage />);
}

beforeEach(() => {
  principalState.capabilities = { ...ADMIN_CAPABILITIES };
});

afterEach(() => {
  vi.doUnmock("@/lib/constants");
  vi.resetModules();
});

describe("CapabilitiesPage", () => {
  it("renders the workflow atlas and buyer-safe workflow map", async () => {
    await renderCapabilitiesPage();

    expect(
      screen.getByRole("heading", { name: "FTO Workflow Atlas" }),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("capabilities-app-surface-header"),
    ).toHaveAttribute("data-praviar-app-surface-header");
    expect(screen.getByText("Decision router")).toBeInTheDocument();
    expect(screen.getAllByText("Decision roles").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Workflow actions").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Reviewable proof").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Can this route proceed?").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("What can I share safely?").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Which compounds need attention?").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Where is the work stuck?").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("AI blocker brief preloaded")).toBeInTheDocument();
    expect(
      screen.getByText("AI external readout preloaded"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("AI reviewer questions preloaded"),
    ).toBeInTheDocument();
    expect(screen.getByText("Live state view")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Canonical fictional research preview, not legal advice/u,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Case Walkthrough")).toBeInTheDocument();
    expect(screen.getByText("Trust Bar")).toBeInTheDocument();
    expect(screen.queryByText("Backend showcase")).not.toBeInTheDocument();
    expect(screen.queryByText("Backend endpoints")).not.toBeInTheDocument();
    expect(screen.queryByText("Role paths")).not.toBeInTheDocument();

    const mobileJumpRail = screen.getByRole("navigation", {
      name: "Workflow atlas sections",
    });
    expect(mobileJumpRail).toHaveClass(
      "grid",
      "grid-flow-col",
      "grid-rows-2",
      "auto-cols-[minmax(8rem,1fr)]",
      "overflow-x-auto",
      "snap-x",
      "snap-mandatory",
      "gap-1",
      "p-1",
    );
    const mobileJumpLinks = Array.from(
      mobileJumpRail.querySelectorAll<HTMLAnchorElement>("a"),
    );
    expect(mobileJumpLinks.slice(0, 3).map((link) => link.textContent)).toEqual(
      ["Decide", "Walkthrough", "Case Creation"],
    );
    for (const link of mobileJumpLinks.slice(0, 3)) {
      expect(link).toHaveClass(
        "min-h-11",
        "min-w-0",
        "snap-start",
        "px-2",
        "[overflow-wrap:anywhere]",
      );
      expect(link).not.toHaveClass("whitespace-nowrap");
    }
  });

  it("links directly into the flagship demo workspace and review workflows in demo mode", async () => {
    await renderCapabilitiesPage();

    expect(
      screen.getByRole("link", { name: "Open counsel case" }),
    ).toHaveAttribute("href", DEMO_COUNSEL_WORKSPACE_HREF);
    expect(
      screen
        .getAllByRole("link", {
          name: /Walk counsel case|Review blocker brief/,
        })
        .some(
          (link) => link.getAttribute("href") === DEMO_COUNSEL_WORKSPACE_HREF,
        ),
    ).toBe(true);
    expect(
      screen.getByRole("link", { name: "Open review queue" }),
    ).toHaveAttribute("href", "/reviews");
  });

  it("routes API-mode buyers into the database-backed analysis library", async () => {
    await renderCapabilitiesPage({ demoMode: false, devAuthBypass: false });

    expect(
      screen.getByRole("link", { name: "Open analysis library" }),
    ).toHaveAttribute("href", "/analyses");
    expect(
      screen.getByRole("link", { name: "Review live analyses" }),
    ).toHaveAttribute("href", "/analyses");

    const links = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(links.some((href) => href?.includes("ana_demo_"))).toBe(false);
  });

  it("shows governed evidence, review, monitor, export, and platform capabilities", async () => {
    await renderCapabilitiesPage();

    expect(screen.getByText("Governed evidence search")).toBeInTheDocument();
    expect(screen.getByText("AI review workspace")).toBeInTheDocument();
    expect(screen.getByText("Review queue")).toBeInTheDocument();
    expect(screen.getByText("Patent monitors")).toBeInTheDocument();
    expect(screen.getByText("Exports and sharing")).toBeInTheDocument();
    expect(screen.getByText("Admin analytics")).toBeInTheDocument();
    expect(
      screen.getAllByText(/ proof · \d+ routes?$/u).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText("POST /reports/{analysis_id}/evidence-search"),
    ).toBeInTheDocument();
  });

  it("fails closed for client-only workflows while preserving public proof", async () => {
    await renderCapabilitiesPage({ role: "client" });

    expect(
      screen.queryByRole("link", { name: "Start adaptive analysis" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Open review queue" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Admin analytics")).not.toBeInTheDocument();
    expect(screen.queryByText("Patent monitors")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open counsel case" }),
    ).toHaveAttribute("href", DEMO_COUNSEL_WORKSPACE_HREF);
  });
});
