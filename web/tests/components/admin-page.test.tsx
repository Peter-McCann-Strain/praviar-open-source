import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminPage from "@/app/(dashboard)/admin/page";

const adminNavigation = vi.hoisted(() => ({
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: adminNavigation.replace }),
}));

vi.mock("@/components/admin-dashboard/overview-tab", () => ({
  OverviewTab: () => <div>Overview panel</div>,
}));

vi.mock("@/components/admin-dashboard/organizations-tab", () => ({
  OrganizationsTab: () => <div>Organizations panel</div>,
}));

vi.mock("@/components/admin-dashboard/users-tab", () => ({
  UsersTab: () => <div>Users panel</div>,
}));

vi.mock("@/components/admin-dashboard/metrics-tab", () => ({
  MetricsTab: () => <div>Metrics panel</div>,
}));

vi.mock("@/components/admin-dashboard/audit-logs-tab", () => ({
  AuditLogsTab: () => <div>Audit logs panel</div>,
}));

vi.mock("@/components/admin-dashboard/tasks-tab", () => ({
  TasksTab: () => <div>Tasks panel</div>,
}));

describe("AdminPage", () => {
  beforeEach(() => {
    adminNavigation.replace.mockReset();
    window.history.replaceState({}, "", "/admin");
  });

  it("uses accessible tab semantics for admin sections", async () => {
    const { rerender } = render(<AdminPage />);

    const header = screen.getByTestId("admin-app-surface-header");

    expect(header).toBeInTheDocument();
    expect(header).toHaveAttribute(
      "data-praviar-app-surface-density",
      "compact",
    );
    expect(header).toHaveClass("py-4");
    expect(screen.getByText("Service checks")).toBeInTheDocument();
    expect(screen.getByText("User roles")).toBeInTheDocument();
    expect(screen.getByText("Task ledger")).toBeInTheDocument();

    const tabList = screen.getByRole("tablist", {
      name: "Admin dashboard sections",
    });
    expect(tabList).toHaveClass(
      "grid-cols-2",
      "sm:grid-cols-3",
      "lg:inline-flex",
      "lg:overflow-x-auto",
    );

    const overviewTab = screen.getByRole("tab", { name: "Overview" });
    expect(overviewTab).toHaveAttribute("aria-selected", "true");
    expect(overviewTab).toHaveAttribute(
      "aria-controls",
      "admin-panel-overview",
    );
    expect(overviewTab).toHaveClass(
      "min-h-11",
      "w-full",
      "shrink-0",
      "lg:w-auto",
    );
    expect(
      screen.getByRole("tabpanel", { name: "Overview" }),
    ).toHaveTextContent("Overview panel");

    const usersTab = screen.getByRole("tab", { name: "Users" });
    expect(usersTab).toHaveClass("min-h-11", "shrink-0");
    fireEvent.mouseDown(usersTab, { button: 0, ctrlKey: false });

    expect(adminNavigation.replace).toHaveBeenCalledWith("/admin?tab=users", {
      scroll: false,
    });
    rerender(<AdminPage />);

    await waitFor(() => {
      expect(usersTab).toHaveAttribute("aria-selected", "true");
    });
    expect(usersTab).toHaveAttribute("aria-controls", "admin-panel-users");
    expect(screen.getByRole("tabpanel", { name: "Users" })).toHaveTextContent(
      "Users panel",
    );
  });

  it("opens a valid notification deep-link and preserves it in navigation", async () => {
    window.history.replaceState({}, "", "/admin?tab=users&source=notification");

    render(<AdminPage />);

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Users" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
    });
    expect(screen.getByRole("tabpanel", { name: "Users" })).toHaveTextContent(
      "Users panel",
    );

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Ops Snapshot" }), {
      button: 0,
      ctrlKey: false,
    });
    expect(adminNavigation.replace).toHaveBeenCalledWith(
      "/admin?tab=metrics&source=notification",
      { scroll: false },
    );
  });
});
