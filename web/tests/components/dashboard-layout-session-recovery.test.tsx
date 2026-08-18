import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/constants", () => ({
  DEMO_MODE_ENABLED: true,
  DEV_AUTH_BYPASS_ENABLED: false,
}));
vi.mock("@/components/auth/organization-workspace-boundary", () => ({
  OrganizationWorkspaceBoundary: ({
    children,
  }: {
    children: React.ReactNode;
  }) => <>{children}</>,
}));
vi.mock("@/components/auth/session-recovery-banner", () => ({
  SessionRecoveryBanner: () => <div data-testid="session-recovery" />,
}));
vi.mock("@/components/layout/sidebar", () => ({
  Sidebar: () => <div data-testid="sidebar" />,
}));
vi.mock("@/components/layout/topbar", () => ({
  Topbar: () => <div data-testid="topbar" />,
}));
vi.mock("@/components/layout/workspace-boundary-banner", () => ({
  WorkspaceBoundaryBanner: () => <div data-testid="workspace-boundary" />,
}));
vi.mock("@/components/layout/dashboard-content", () => ({
  DashboardContent: ({ children }: { children: React.ReactNode }) => (
    <section data-testid="dashboard-content">{children}</section>
  ),
}));
vi.mock("@/components/ui/toast", () => ({
  ToastContainer: () => null,
}));
vi.mock("@/components/shared/command-palette", () => ({
  CommandPalette: () => null,
}));
vi.mock("@/components/shared/page-transition", () => ({
  PageTransition: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));
vi.mock("@/components/shared/welcome-modal", () => ({
  WelcomeModal: () => null,
}));

import DashboardLayout from "@/app/(dashboard)/layout";

function expectBefore(first: HTMLElement, second: HTMLElement) {
  expect(
    first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
}

describe("DashboardLayout session recovery placement", () => {
  it("places recovery directly below the topbar and above workspace banners and content", () => {
    render(
      <DashboardLayout>
        <div data-testid="page-content" />
      </DashboardLayout>,
    );

    const topbar = screen.getByTestId("topbar");
    const sessionRecovery = screen.getByTestId("session-recovery");
    const workspaceBoundary = screen.getByTestId("workspace-boundary");
    const main = document.getElementById("main-content");

    expect(main).not.toBeNull();
    expectBefore(topbar, sessionRecovery);
    expectBefore(sessionRecovery, workspaceBoundary);
    expectBefore(workspaceBoundary, main as HTMLElement);
  });
});
