import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import { createMotionMock } from "../helpers/mock-motion";
import { AuditLogsTab } from "@/components/admin-dashboard/audit-logs-tab";
import { MetricsTab } from "@/components/admin-dashboard/metrics-tab";
import { OrganizationsTab } from "@/components/admin-dashboard/organizations-tab";
import { OverviewTab } from "@/components/admin-dashboard/overview-tab";
import { TasksTab } from "@/components/admin-dashboard/tasks-tab";
import { UsersTab } from "@/components/admin-dashboard/users-tab";
import { APIError } from "@/lib/api-client";
import type {
  AdminCapabilities,
  AuditLogEntry,
  DailyMetric,
  OrgSummary,
  TaskInfo,
} from "@/hooks/use-admin";

vi.mock("motion/react", () => createMotionMock());

const mockUseAdminTasks = vi.fn();
const mockUseAdminOrganizations = vi.fn();
const mockUseUpdateOrg = vi.fn();
const mockUpdateOrgMutate = vi.fn();
const mockUseAdminAuditLogs = vi.fn();
const mockUseAdminMetrics = vi.fn();
const mockUseAdminHealth = vi.fn();
const mockUseAdminUsers = vi.fn();
const mockUseAdminOperations = vi.fn();
const mockUseUpdateUserRole = vi.fn();
const mockUseInviteUser = vi.fn();
const mockUseReconcileAdminOperation = vi.fn();

vi.mock("@/hooks/use-admin", () => ({
  useAdminTasks: (...args: unknown[]) => mockUseAdminTasks(...args),
  useAdminOrganizations: (...args: unknown[]) =>
    mockUseAdminOrganizations(...args),
  useUpdateOrg: () => mockUseUpdateOrg(),
  useAdminAuditLogs: (...args: unknown[]) => mockUseAdminAuditLogs(...args),
  useAdminMetrics: (...args: unknown[]) => mockUseAdminMetrics(...args),
  useAdminHealth: (...args: unknown[]) => mockUseAdminHealth(...args),
  useAdminUsers: (...args: unknown[]) => mockUseAdminUsers(...args),
  useAdminOperations: (...args: unknown[]) => mockUseAdminOperations(...args),
  useUpdateUserRole: () => mockUseUpdateUserRole(),
  useInviteUser: () => mockUseInviteUser(),
  useReconcileAdminOperation: () => mockUseReconcileAdminOperation(),
}));

describe("admin dashboard responsive tables", () => {
  const tenantCapabilities: AdminCapabilities = {
    admin_org_id: "org-1",
    is_platform_superadmin: false,
    can_manage_org_billing: false,
    can_list_cross_org_users: false,
    can_manage_cross_org_user_roles: false,
    can_inspect_task_queue: false,
  };
  const platformCapabilities: AdminCapabilities = {
    admin_org_id: "org-1",
    is_platform_superadmin: true,
    can_manage_org_billing: true,
    can_list_cross_org_users: true,
    can_manage_cross_org_user_roles: false,
    can_inspect_task_queue: true,
  };
  const runningTask: TaskInfo = {
    id: "task-running-0000000000000001",
    name: "Generate FTO report",
    args: [],
    status: "active",
  };
  const reservedTask: TaskInfo = {
    id: "task-reserved-0000000000000002",
    name: "Refresh monitor",
    args: [],
    status: "reserved",
  };
  const organization: OrgSummary = {
    id: "org-1",
    name: "Acme Therapeutics",
    slug: "acme-therapeutics",
    plan: "pro",
    user_count: 7,
    analysis_count: 42,
    max_analyses_per_month: 100,
    free_analyses_remaining: 3,
    created_at: "2026-06-01T00:00:00Z",
  };
  const auditEntry: AuditLogEntry = {
    id: "audit-1",
    action: "admin.user_role.updated",
    user_id: "user-1",
    user_email: "admin@acme.example",
    analysis_id: "analysis-1",
    details: { target_user_id: "user-2", new_role: "attorney" },
    ip_address: "203.0.113.12",
    created_at: "2026-06-12T09:30:00Z",
  };
  const dailyMetric: DailyMetric = {
    date: "2026-06-12",
    count: 5,
    cost: 2.75,
    errors: 1,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAdminTasks.mockReturnValue({
      data: {
        backend: "celery",
        detail: "worker pool healthy",
        inspectable: true,
        active: [runningTask],
        reserved: [reservedTask],
        scheduled_count: 2,
      },
      isLoading: false,
      error: null,
    });
    mockUseAdminOrganizations.mockReturnValue({
      data: {
        items: [organization],
        total: 40,
        capabilities: platformCapabilities,
      },
      isLoading: false,
      error: null,
    });
    mockUpdateOrgMutate.mockReset();
    mockUseUpdateOrg.mockReturnValue({
      mutate: mockUpdateOrgMutate,
      isPending: false,
    });
    mockUseAdminAuditLogs.mockReturnValue({
      data: { items: [auditEntry], total: 40 },
      isLoading: false,
      error: null,
    });
    mockUseAdminMetrics.mockReturnValue({
      data: {
        daily: [dailyMetric],
        total_analyses: 5,
        total_cost: 2.75,
        avg_duration_seconds: 612,
        error_rate: 0.02,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAdminHealth.mockReturnValue({
      data: {
        services: [{ name: "api", status: "healthy", detail: "ok" }],
        table_counts: { analyses: 1 },
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAdminUsers.mockReturnValue({
      data: { items: [], total: 0, capabilities: tenantCapabilities },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseAdminOperations.mockReturnValue({
      data: { items: [], open_total: 0, has_more: false },
      isLoading: false,
      error: null,
    });
    mockUseUpdateUserRole.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
    mockUseInviteUser.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
    mockUseReconcileAdminOperation.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    });
  });

  it("renders task queue rows with mobile field labels exposed to assistive technology", () => {
    render(<TasksTab />);

    expect(screen.getByText("Running Tasks (1)")).toBeInTheDocument();
    expect(screen.getByText(runningTask.id)).toBeInTheDocument();
    expect(screen.getByText("Generate FTO report")).toBeInTheDocument();
    expect(screen.getByText("Reserved Tasks (1)")).toBeInTheDocument();
    expect(screen.getByText("Refresh monitor")).toBeInTheDocument();
    const mobileTaskIdLabels = screen
      .getAllByText("Task ID")
      .filter((node) => node.tagName === "SPAN");
    expect(mobileTaskIdLabels).toHaveLength(2);
    for (const label of mobileTaskIdLabels) {
      expect(label).not.toHaveAttribute("aria-hidden");
    }
  });

  it("wraps long task names and constrains unexpected backend statuses", () => {
    const longTaskName =
      "praviar_pipeline.workers.legal_review.refresh_markush_ocsr_adaptive_evidence_packet_without_natural_breakpoints";
    const longStatus =
      "temporarily_unavailable_due_to_queue_backpressure_and_retrying_after_provider_window";
    mockUseAdminTasks.mockReturnValue({
      data: {
        backend: "celery",
        detail: "worker pool healthy",
        inspectable: true,
        active: [
          {
            ...runningTask,
            id: "task-long-00000000000000000000000000000001",
            name: longTaskName,
            status: longStatus,
          },
        ],
        reserved: [],
        scheduled_count: 0,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<TasksTab />);

    expect(screen.getByText(longTaskName)).toHaveClass(
      "min-w-0",
      "[overflow-wrap:anywhere]",
      "md:block",
    );
    const statusPill = screen.getByText(longStatus);
    expect(statusPill).toHaveClass(
      "max-w-full",
      "min-w-0",
      "[overflow-wrap:anywhere]",
      "md:max-w-[12rem]",
      "md:truncate",
    );
    expect(statusPill).toHaveAttribute("title", longStatus);
  });

  it("keeps organization plan updates and pagination working", async () => {
    render(<OrganizationsTab />);

    expect(screen.getByText("Acme Therapeutics")).toBeInTheDocument();
    expect(screen.getByText("Acme Therapeutics")).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("acme-therapeutics")).toBeInTheDocument();

    const organizationTableRegion = screen.getByRole("region", {
      name: "Admin organization plan table",
    });
    expect(organizationTableRegion).toHaveClass("overflow-x-auto");
    expect(
      screen.getByRole("table", { name: /Admin organization plan table/i }),
    ).toHaveClass("w-full", "min-w-0", "md:min-w-[920px]");
    expect(screen.getByText("Acme Therapeutics").closest("tr")).toHaveClass(
      "block",
      "rounded-lg",
      "md:table-row",
    );

    fireEvent.change(
      screen.getByLabelText("Review plan change for Acme Therapeutics"),
      {
        target: { value: "enterprise" },
      },
    );
    expect(
      screen.getByLabelText("Review plan change for Acme Therapeutics"),
    ).toHaveClass("h-11", "focus-visible:ring-2");
    expect(mockUpdateOrgMutate).not.toHaveBeenCalled();
    expect(screen.getByText("Review plan change")).toBeInTheDocument();
    expect(screen.getByText(/Pro to Enterprise/i)).toBeInTheDocument();
    const proposedPlanStatus = screen.getByText("Proposed: Enterprise");
    expect(proposedPlanStatus).toBeInTheDocument();
    expect(
      screen.getByLabelText("Review plan change for Acme Therapeutics"),
    ).toHaveValue("pro");
    expect(
      screen.getByLabelText("Review plan change for Acme Therapeutics"),
    ).toHaveAttribute("aria-describedby", proposedPlanStatus.id);
    const planDialog = screen.getByRole("dialog", {
      name: "Review plan change",
    });
    expect(within(planDialog).getByText("Acme Therapeutics")).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(within(planDialog).getByText("Current plan")).toBeInTheDocument();
    expect(within(planDialog).getByText("Proposed plan")).toBeInTheDocument();
    expect(
      within(planDialog).getByText(
        /Full platform tier for active FTO programs/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(planDialog).getByText("Included Report Credits"),
    ).toBeInTheDocument();
    expect(within(planDialog).getByText("100 / month")).toBeInTheDocument();
    expect(
      within(planDialog).getByText("Report requests used"),
    ).toBeInTheDocument();
    expect(within(planDialog).getByText("42")).toBeInTheDocument();
    expect(
      within(planDialog).getByText("Included remaining"),
    ).toBeInTheDocument();
    expect(within(planDialog).getByText("3")).toBeInTheDocument();
    expect(
      screen.getByText(/subscription and Report Credit ledger/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("Optional local note before applying"),
    ).not.toBeInTheDocument();

    const applyPlanButton = screen.getByRole("button", {
      name: "Apply plan change for Acme Therapeutics",
    });
    fireEvent.click(applyPlanButton);
    fireEvent.click(applyPlanButton);

    expect(mockUpdateOrgMutate).toHaveBeenCalledWith(
      {
        orgId: "org-1",
        data: { plan: "enterprise" },
      },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
    expect(mockUpdateOrgMutate).toHaveBeenCalledTimes(1);
    expect(applyPlanButton).toBeDisabled();

    const mutationOptions = mockUpdateOrgMutate.mock.calls[0]?.[1] as {
      onSuccess: () => void;
      onError: () => void;
    };

    act(() => {
      mutationOptions.onError();
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Plan change was not applied",
    );

    act(() => {
      mutationOptions.onSuccess();
    });
    expect(screen.queryByText("Review plan change")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(mockUseAdminOrganizations).toHaveBeenLastCalledWith(2);
    });
  });

  it("renders organization plan controls read-only for tenant admins", () => {
    mockUseAdminOrganizations.mockReturnValue({
      data: {
        items: [organization],
        total: 1,
        capabilities: tenantCapabilities,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<OrganizationsTab />);

    expect(screen.getByText("Read-only")).toBeInTheDocument();
    const readOnlyControl = screen.getByLabelText(
      "Plan controls for Acme Therapeutics are read-only",
    );
    expect(readOnlyControl).toHaveAccessibleDescription(
      "Plan changes require platform superadmin access.",
    );
    expect(
      screen.queryByLabelText("Review plan change for Acme Therapeutics"),
    ).not.toBeInTheDocument();
    expect(mockUpdateOrgMutate).not.toHaveBeenCalled();
  });

  it("keeps stale organization rows visible but locks plan mutations when refresh fails", () => {
    mockUseAdminOrganizations.mockReturnValue({
      data: {
        items: [organization],
        total: 40,
        capabilities: platformCapabilities,
      },
      isLoading: false,
      error: new Error("organization directory refresh failed"),
      refetch: vi.fn(),
    });

    render(<OrganizationsTab />);

    expect(screen.getByText("Acme Therapeutics")).toBeInTheDocument();
    expect(
      screen.getByText(/Organization controls refresh failed/i),
    ).toBeInTheDocument();
    const planSelect = screen.getByLabelText(
      "Review plan change for Acme Therapeutics",
    );
    expect(planSelect).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    fireEvent.change(planSelect, { target: { value: "enterprise" } });
    expect(screen.queryByText("Review plan change")).not.toBeInTheDocument();
    expect(mockUpdateOrgMutate).not.toHaveBeenCalled();
  });

  it("keeps audit filtering and detail rows readable", async () => {
    render(<AuditLogsTab />);

    expect(screen.getByText("admin.user_role.updated")).toBeInTheDocument();
    expect(screen.getByText("admin@acme.example")).toBeInTheDocument();
    expect(screen.getByText("203.0.113.12")).toBeInTheDocument();
    expect(
      screen.getByText("Target user reference, New role recorded"),
    ).toBeInTheDocument();
    expect(screen.getByText("2026-06-12 09:30:00Z UTC")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Admin audit event table" }),
    ).toHaveClass("overflow-x-auto");
    expect(
      screen.queryByText('{"compound":"succinic acid"}'),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Filter by action/i), {
      target: { value: "admin.user_role.updated" },
    });
    await waitFor(() => {
      expect(mockUseAdminAuditLogs).toHaveBeenLastCalledWith(
        1,
        "admin.user_role.updated",
      );
    });
  });

  it("constrains long audit action labels on mobile rows", () => {
    const longAction =
      "admin.organization.entitlement.sync.completed_from_provider_webhook_without_natural_breakpoints";
    mockUseAdminAuditLogs.mockReturnValue({
      data: {
        items: [{ ...auditEntry, action: longAction }],
        total: 1,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<AuditLogsTab />);

    const actionPill = screen.getByText(longAction);
    expect(actionPill).toHaveClass(
      "max-w-full",
      "min-w-0",
      "[overflow-wrap:anywhere]",
      "md:max-w-[18rem]",
      "md:truncate",
    );
    expect(actionPill).toHaveAttribute("title", longAction);
  });

  it("renders daily metrics as a labelled scroll table", () => {
    render(<MetricsTab />);

    expect(screen.getByText("Daily Activity")).toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: "Admin platform daily activity table",
      }),
    ).toHaveAttribute("tabIndex", "0");
    expect(
      screen.getByText(/Admin platform daily activity table with date/i),
    ).toBeInTheDocument();
    for (const header of screen.getAllByRole("columnheader")) {
      expect(header).toHaveAttribute("scope", "col");
    }
    expect(screen.getByText("2026-06-12")).toBeInTheDocument();
    expect(screen.getAllByText("$2.75").length).toBeGreaterThan(0);
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("renders the admin overview as an operational posture cockpit", () => {
    render(<OverviewTab />);

    const controlField = screen.getByTestId("admin-overview-control-field");
    expect(controlField).toBeInTheDocument();
    expect(controlField).toHaveClass("praviar-operational-field");
    expect(
      controlField.querySelector("[class*='praviar-admin-control-field']"),
    ).toBeNull();
    expect(screen.getByText("Operations posture")).toBeInTheDocument();
    expect(within(controlField).getByText("Operational")).toBeInTheDocument();
    expect(screen.getAllByText("1 of 1 healthy").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Records tracked").length).toBeGreaterThan(0);
    expect(screen.getByText("Largest table")).toBeInTheDocument();
    expect(screen.getAllByText("analyses").length).toBeGreaterThan(0);
  });

  it("surfaces degraded admin services as attention needed", () => {
    mockUseAdminHealth.mockReturnValue({
      data: {
        services: [
          { name: "api", status: "healthy", detail: "ok" },
          {
            name: "worker",
            status: "degraded",
            detail: "queue latency high postgres://secret sk_live_secret",
          },
        ],
        table_counts: { analyses: 8, organizations: 2 },
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<OverviewTab />);

    const controlField = screen.getByTestId("admin-overview-control-field");
    expect(
      within(controlField).getByText("Attention needed"),
    ).toBeInTheDocument();
    expect(
      within(controlField).getByText(
        /1 check needs triage across 2 monitored services/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("1 of 2 healthy").length).toBeGreaterThan(0);
    expect(screen.getByText("Service requires attention")).toBeInTheDocument();
    expect(screen.queryByText(/queue latency high/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/postgres:\/\/secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sk_live_secret/i)).not.toBeInTheDocument();
  });

  it("treats an empty admin health feed as unknown coverage", () => {
    mockUseAdminHealth.mockReturnValue({
      data: {
        services: [],
        table_counts: {},
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<OverviewTab />);

    const controlField = screen.getByTestId("admin-overview-control-field");
    expect(
      within(controlField).getAllByText("Coverage unknown").length,
    ).toBeGreaterThan(0);
    expect(
      within(controlField).getByText(/No service checks are configured/i),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("No service checks configured").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(/Admin health coverage is unknown/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/All 0 monitored services/i),
    ).not.toBeInTheDocument();
  });

  it("constrains long unknown service status labels", () => {
    const longStatus = "temporarily_unavailable_due_to_queue_backpressure";
    mockUseAdminHealth.mockReturnValue({
      data: {
        services: [
          {
            name: "worker",
            status: longStatus,
            detail: "backend status returned a long literal",
          },
        ],
        table_counts: { analyses: 3 },
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<OverviewTab />);

    const statusBadge = screen.getByText(longStatus);
    expect(statusBadge).toHaveClass("max-w-[9rem]", "truncate");
    expect(statusBadge).toHaveAttribute("title", longStatus);
    expect(screen.getByText("Incident review")).toBeInTheDocument();
  });

  it("renders admin load errors without raw backend diagnostics and retries", () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseAdminHealth.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("database password leaked"),
      refetch,
    });

    render(
      <StrictMode>
        <OverviewTab />
      </StrictMode>,
    );

    expect(
      screen.getByText("System overview temporarily unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/database password leaked/i),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry admin load" }));
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledWith(
      "[OverviewTab] Failed to load system health",
    );
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.any(String),
      expect.any(Error),
    );
    consoleError.mockRestore();
  });

  it("reports each remaining admin load failure once under StrictMode", () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const cases = [
      {
        configure: () =>
          mockUseAdminTasks.mockReturnValue({
            data: undefined,
            isLoading: false,
            error: new Error("private task backend detail"),
            refetch: vi.fn(),
          }),
        diagnostic: "[TasksTab] Failed to load task queue",
        renderSurface: () =>
          render(
            <StrictMode>
              <TasksTab />
            </StrictMode>,
          ),
      },
      {
        configure: () =>
          mockUseAdminOrganizations.mockReturnValue({
            data: undefined,
            isLoading: false,
            error: new Error("private organization backend detail"),
            refetch: vi.fn(),
          }),
        diagnostic: "[OrganizationsTab] Failed to load organizations",
        renderSurface: () =>
          render(
            <StrictMode>
              <OrganizationsTab />
            </StrictMode>,
          ),
      },
      {
        configure: () =>
          mockUseAdminMetrics.mockReturnValue({
            data: undefined,
            isLoading: false,
            error: new Error("private metrics backend detail"),
            refetch: vi.fn(),
          }),
        diagnostic: "[MetricsTab] Failed to load platform metrics",
        renderSurface: () =>
          render(
            <StrictMode>
              <MetricsTab />
            </StrictMode>,
          ),
      },
      {
        configure: () =>
          mockUseAdminAuditLogs.mockReturnValue({
            data: undefined,
            isLoading: false,
            error: new Error("private audit backend detail"),
            refetch: vi.fn(),
          }),
        diagnostic: "[AuditLogsTab] Failed to load audit log",
        renderSurface: () =>
          render(
            <StrictMode>
              <AuditLogsTab />
            </StrictMode>,
          ),
      },
    ];

    for (const testCase of cases) {
      testCase.configure();
      const view = testCase.renderSurface();
      expect(consoleError).toHaveBeenCalledTimes(1);
      expect(consoleError).toHaveBeenCalledWith(testCase.diagnostic);
      expect(consoleError).not.toHaveBeenCalledWith(
        expect.stringMatching(/private .* backend detail/i),
      );
      view.unmount();
      consoleError.mockClear();
    }

    consoleError.mockRestore();
  });

  it("does not show an empty user list while admin auth is unavailable", () => {
    mockUseAdminUsers.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<UsersTab />);

    expect(
      screen.getByText("Checking user controls access"),
    ).toBeInTheDocument();
    expect(screen.queryByText("0 total users")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Invite User" }),
    ).not.toBeInTheDocument();
  });

  it("keeps admin user role controls touch-safe with visible focus rings", () => {
    mockUseAdminUsers.mockReturnValue({
      data: {
        items: [
          {
            id: "user-1",
            email: "analyst@acme.example",
            full_name: "Analyst User",
            role: "scientist",
            org_id: "org-1",
            org_name: "Acme Therapeutics",
            last_active_at: null,
            created_at: "2026-06-01T00:00:00Z",
          },
        ],
        total: 1,
        capabilities: tenantCapabilities,
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<UsersTab />);

    expect(screen.getByText("Analyst User")).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(screen.getByText("Acme Therapeutics")).toHaveClass(
      "[overflow-wrap:anywhere]",
    );
    expect(
      screen.getByLabelText("Review role change for analyst@acme.example"),
    ).toHaveClass("h-11", "focus-visible:ring-2");
  });

  it("distinguishes stale paged-empty admin slices from true empty states", () => {
    mockUseAdminUsers.mockReturnValue({
      data: { items: [], total: 21, capabilities: tenantCapabilities },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    const { unmount } = render(<UsersTab />);

    expect(screen.getByText("No users on this page")).toBeInTheDocument();
    expect(screen.queryByText("No users")).not.toBeInTheDocument();

    unmount();

    mockUseAdminOrganizations.mockReturnValue({
      data: { items: [], total: 21, capabilities: tenantCapabilities },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    const organizationRender = render(<OrganizationsTab />);

    expect(
      screen.getByText("No organizations on this page"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No platform organizations yet"),
    ).not.toBeInTheDocument();

    organizationRender.unmount();

    mockUseAdminAuditLogs.mockReturnValue({
      data: { items: [], total: 21 },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<AuditLogsTab />);

    expect(
      screen.getByText("No audit events on this page"),
    ).toBeInTheDocument();
    expect(screen.queryByText("No audit events yet")).not.toBeInTheDocument();
  });

  it("preserves stale admin data when a background refresh fails", () => {
    mockUseAdminMetrics.mockReturnValue({
      data: {
        daily: [dailyMetric],
        total_analyses: 5,
        total_cost: 2.75,
        avg_duration_seconds: 612,
        error_rate: 0.02,
      },
      isLoading: false,
      error: new Error("background refresh failed"),
      refetch: vi.fn(),
    });

    render(<MetricsTab />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Platform metrics refresh failed",
    );
    expect(screen.getByText("Daily Activity")).toBeInTheDocument();
    expect(
      screen.queryByText(/background refresh failed/i),
    ).not.toBeInTheDocument();
  });

  it("hides cached admin tab data on auth boundary errors", () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    mockUseAdminOrganizations.mockReturnValue({
      data: {
        items: [organization],
        total: 1,
        capabilities: platformCapabilities,
      },
      isLoading: false,
      error: new APIError(403, "Forbidden"),
      refetch: vi.fn(),
    });
    const organizationRender = render(<OrganizationsTab />);
    expect(
      screen.getByTestId("admin-organizations-status-restricted"),
    ).toHaveAttribute("data-praviar-status-frame");
    expect(screen.queryByText("Acme Therapeutics")).not.toBeInTheDocument();
    organizationRender.unmount();

    mockUseAdminAuditLogs.mockReturnValue({
      data: { items: [auditEntry], total: 1 },
      isLoading: false,
      error: new APIError(401, "Authentication required"),
      refetch: vi.fn(),
    });
    const auditRender = render(<AuditLogsTab />);
    expect(
      screen.getByTestId("admin-audit-logs-status-restricted"),
    ).toHaveAttribute("data-praviar-status-frame");
    expect(screen.queryByText("admin@acme.example")).not.toBeInTheDocument();
    auditRender.unmount();

    mockUseAdminMetrics.mockReturnValue({
      data: {
        daily: [dailyMetric],
        total_analyses: 5,
        total_cost: 2.75,
        avg_duration_seconds: 612,
        error_rate: 0.02,
      },
      isLoading: false,
      error: new APIError(403, "Forbidden"),
      refetch: vi.fn(),
    });
    const metricsRender = render(<MetricsTab />);
    expect(
      screen.getByTestId("admin-metrics-status-restricted"),
    ).toHaveAttribute("data-praviar-status-frame");
    expect(screen.queryByText("Daily Activity")).not.toBeInTheDocument();
    metricsRender.unmount();

    mockUseAdminHealth.mockReturnValue({
      data: {
        services: [{ name: "api", status: "healthy", detail: "ok" }],
        table_counts: { analyses: 1 },
      },
      isLoading: false,
      error: new APIError(401, "Authentication required"),
      refetch: vi.fn(),
    });
    const overviewRender = render(<OverviewTab />);
    expect(
      screen.getByTestId("admin-overview-status-restricted"),
    ).toHaveAttribute("data-praviar-status-frame");
    expect(screen.queryByText("Operations posture")).not.toBeInTheDocument();
    overviewRender.unmount();

    mockUseAdminTasks.mockReturnValue({
      data: {
        backend: "celery",
        detail: "worker pool healthy",
        inspectable: true,
        active: [runningTask],
        reserved: [reservedTask],
        scheduled_count: 2,
      },
      isLoading: false,
      error: new APIError(403, "Forbidden"),
      refetch: vi.fn(),
    });
    render(<TasksTab />);
    expect(screen.getByTestId("admin-tasks-status-restricted")).toHaveAttribute(
      "data-praviar-status-frame",
    );
    expect(screen.queryByText("Running Tasks (1)")).not.toBeInTheDocument();

    consoleError.mockRestore();
  });
});
