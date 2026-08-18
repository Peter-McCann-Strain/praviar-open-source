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
import { UsersTab } from "@/components/admin-dashboard/users-tab";
import { APIError } from "@/lib/api-client";
import type { AdminCapabilities, UserSummary } from "@/hooks/use-admin";

const mockUseAdminUsers = vi.fn();
const mockUpdateRoleMutate = vi.fn();
const mockUseUpdateUserRole = vi.fn();
const mockInviteMutate = vi.fn();
const mockUseInviteUser = vi.fn();
const mockUseAdminOperations = vi.fn();
const mockReconcileOperationMutate = vi.fn();
const mockUseReconcileAdminOperation = vi.fn();

vi.mock("@/hooks/use-admin", () => ({
  useAdminUsers: (...args: unknown[]) => mockUseAdminUsers(...args),
  useUpdateUserRole: () => mockUseUpdateUserRole(),
  useInviteUser: () => mockUseInviteUser(),
  useAdminOperations: () => mockUseAdminOperations(),
  useReconcileAdminOperation: () => mockUseReconcileAdminOperation(),
}));

describe("UsersTab", () => {
  const tenantCapabilities: AdminCapabilities = {
    admin_org_id: "org-1",
    is_platform_superadmin: false,
    can_manage_org_billing: false,
    can_list_cross_org_users: false,
    can_manage_cross_org_user_roles: false,
    can_inspect_task_queue: false,
  };
  const users: UserSummary[] = [
    {
      id: "user-1",
      email: "alice@example.com",
      full_name: "Alice Example",
      role: "admin",
      org_id: "org-1",
      org_name: "Acme Corp",
      last_active_at: "2026-04-13T11:00:00.000Z",
      created_at: "2026-04-01T00:00:00.000Z",
    },
    {
      id: "user-2",
      email: "bob@example.com",
      full_name: "",
      role: "scientist",
      org_id: "org-1",
      org_name: "Acme Corp",
      last_active_at: null,
      created_at: "2026-04-01T00:00:00.000Z",
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAdminUsers.mockReturnValue({
      data: { items: users, total: 40, capabilities: tenantCapabilities },
      isLoading: false,
      error: null,
    });
    mockUpdateRoleMutate.mockReset();
    mockUseUpdateUserRole.mockReturnValue({ mutate: mockUpdateRoleMutate });
    mockInviteMutate.mockReset();
    mockUseInviteUser.mockReturnValue({
      mutate: mockInviteMutate,
      isPending: false,
    });
    mockUseAdminOperations.mockReturnValue({
      data: { items: [], open_total: 0, has_more: false },
      isLoading: false,
      error: null,
    });
    mockReconcileOperationMutate.mockReset();
    mockUseReconcileAdminOperation.mockReturnValue({
      mutate: mockReconcileOperationMutate,
      isPending: false,
    });
    mockInviteMutate.mockImplementation(
      (
        _payload: { email: string; role: string },
        options?: { onSuccess?: () => void },
      ) => {
        options?.onSuccess?.();
      },
    );
  });

  it("renders the users table, updates roles, and sends an invite", async () => {
    render(<UsersTab />);

    expect(screen.getByText("40 total users")).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Email" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Last Active" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("cell", { name: "alice@example.com" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Never" })).toBeInTheDocument();

    const inviteButton = screen.getByRole("button", { name: "Invite User" });
    expect(inviteButton).toHaveClass("min-h-11");
    expect(inviteButton).not.toHaveClass("sm:min-h-0");
    fireEvent.click(inviteButton);
    fireEvent.change(screen.getByLabelText("Email Address"), {
      target: { value: "  new.user@example.com  " },
    });
    fireEvent.change(screen.getByLabelText("Invite role"), {
      target: { value: "client" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send Invite" }));

    await waitFor(() => {
      expect(mockInviteMutate).toHaveBeenCalledWith(
        { email: "new.user@example.com", role: "client" },
        expect.objectContaining({
          onSuccess: expect.any(Function),
        }),
      );
    });

    await waitFor(() => {
      expect(screen.queryByLabelText("Email Address")).not.toBeInTheDocument();
    });

    const userTableRegion = screen.getByRole("region", {
      name: "Admin user access table",
    });
    expect(userTableRegion).toHaveClass("overflow-x-auto");
    const usersTable = screen.getByRole("table", {
      name: /Admin user access table/i,
    });
    expect(usersTable).toHaveClass(
      "w-full",
      "min-w-0",
      "lg:min-w-[980px]",
      "lg:table-fixed",
    );
    expect(
      Array.from(usersTable.querySelectorAll("col")).map(
        (column) => column.className,
      ),
    ).toEqual([
      "w-[23%]",
      "w-[13%]",
      "w-[14%]",
      "w-[18%]",
      "w-[10%]",
      "w-[22%]",
    ]);
    expect(
      screen.getByRole("columnheader", { name: "Last Active" }),
    ).toHaveClass("whitespace-nowrap", "px-4");
    expect(screen.getByText("alice@example.com").closest("tr")).toHaveClass(
      "block",
      "rounded-lg",
      "lg:table-row",
    );
    const emailValue = screen.getByText("alice@example.com");
    expect(emailValue).toHaveClass(
      "[overflow-wrap:anywhere]",
      "lg:block",
      "lg:truncate",
    );
    expect(emailValue).toHaveAttribute("title", "alice@example.com");
    expect(emailValue.closest("td")).toHaveClass(
      "grid-cols-1",
      "sm:grid-cols-[6.75rem_minmax(0,1fr)]",
    );
    expect(
      within(emailValue.closest("tr") as HTMLElement)
        .getByText("Governance")
        .closest("div"),
    ).toHaveClass("grid-cols-1", "sm:grid-cols-[6.75rem_minmax(0,1fr)]");
    expect(
      screen.getByText(/Admin user access table with role, organization/i),
    ).toBeInTheDocument();

    fireEvent.change(
      screen.getByLabelText("Review role change for alice@example.com"),
      {
        target: { value: "attorney" },
      },
    );

    expect(mockUpdateRoleMutate).not.toHaveBeenCalled();
    expect(screen.getByText("Review role change")).toBeInTheDocument();
    expect(screen.getByText(/Admin to Attorney/i)).toBeInTheDocument();
    const proposedRoleStatus = screen.getByText("Proposed: Attorney");
    expect(proposedRoleStatus).toBeInTheDocument();
    expect(
      screen.getByLabelText("Review role change for alice@example.com"),
    ).toHaveValue("admin");
    expect(
      screen.getByLabelText("Review role change for alice@example.com"),
    ).toHaveAttribute("aria-describedby", proposedRoleStatus.id);
    const roleDialog = screen.getByRole("dialog", {
      name: "Review role change",
    });
    expect(within(roleDialog).getAllByText("Acme Corp").length).toBeGreaterThan(
      0,
    );
    expect(within(roleDialog).getByText("Current access")).toBeInTheDocument();
    expect(within(roleDialog).getByText("Proposed access")).toBeInTheDocument();
    expect(
      within(roleDialog).getByText(/governed review workflows/i),
    ).toBeInTheDocument();
    expect(
      within(roleDialog).getByText(
        "Backend permission checks remain authoritative after this change.",
        { exact: true },
      ),
    ).toBeInTheDocument();
    expect(
      within(roleDialog)
        .getByText("Compare permission impact", { exact: true })
        .closest("summary"),
    ).toHaveClass("min-h-11");
    expect(
      screen.queryByPlaceholderText("Optional local note before applying"),
    ).not.toBeInTheDocument();

    const applyRoleButton = screen.getByRole("button", {
      name: "Apply role change for alice@example.com",
    });
    fireEvent.click(applyRoleButton);
    fireEvent.click(applyRoleButton);

    expect(mockUpdateRoleMutate).toHaveBeenCalledWith(
      {
        userId: "user-1",
        role: "attorney",
      },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
    expect(mockUpdateRoleMutate).toHaveBeenCalledTimes(1);
    expect(applyRoleButton).toBeDisabled();

    const mutationOptions = mockUpdateRoleMutate.mock.calls[0]?.[1] as {
      onSuccess: () => void;
      onError: () => void;
    };

    act(() => {
      mutationOptions.onError();
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Role update outcome is unconfirmed",
    );

    act(() => {
      mutationOptions.onSuccess();
    });
    expect(screen.queryByText("Review role change")).not.toBeInTheDocument();
  });

  it("wraps long user identity strings in the role-review dialog", () => {
    const longEmail =
      "external.counsel.with.a.very.long.identity.for.markush.review@cross-border-diligence.example";
    const longOrg =
      "Acme Therapeutics International FTO Continuation Monitoring and Board Diligence Consortium";
    mockUseAdminUsers.mockReturnValue({
      data: {
        items: [
          {
            ...users[0],
            email: longEmail,
            full_name: "External Counsel",
            role: "scientist",
            org_name: longOrg,
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

    fireEvent.change(
      screen.getByLabelText(`Review role change for ${longEmail}`),
      {
        target: { value: "attorney" },
      },
    );

    const roleDialog = screen.getByRole("dialog", {
      name: "Review role change",
    });
    const emailSpan = within(roleDialog).getByText(longEmail);
    expect(emailSpan).toHaveClass("[overflow-wrap:anywhere]");
    expect(emailSpan.closest("p")).toHaveClass("[overflow-wrap:anywhere]");

    within(roleDialog)
      .getAllByText(longOrg)
      .forEach((orgSpan) => {
        expect(orgSpan).toHaveClass("[overflow-wrap:anywhere]");
      });
  });

  it("announces invalid invite email before sending", () => {
    render(<UsersTab />);

    fireEvent.click(screen.getByRole("button", { name: "Invite User" }));
    const emailInput = screen.getByLabelText("Email Address");
    fireEvent.change(emailInput, {
      target: { value: "not-an-email" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send Invite" }));

    expect(mockInviteMutate).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a valid work email address",
    );
    expect(emailInput).toHaveAttribute("aria-invalid", "true");

    fireEvent.change(emailInput, {
      target: { value: "new.user@example.com" },
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("hides cached user rows and logs once when admin access is revoked", async () => {
    const refetch = vi.fn();
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    mockUseAdminUsers.mockReturnValue({
      data: { items: users, total: 2, capabilities: tenantCapabilities },
      isLoading: false,
      error: new APIError(403, "Forbidden"),
      refetch,
    });

    render(
      <StrictMode>
        <UsersTab />
      </StrictMode>,
    );

    expect(screen.getByTestId("admin-users-status-restricted")).toHaveAttribute(
      "data-praviar-status-frame",
    );
    expect(screen.getByTestId("admin-users-status-restricted")).toHaveClass(
      "scroll-mt-20",
    );
    expect(
      screen.getByText("User controls access restricted"),
    ).toBeInTheDocument();
    expect(screen.queryByText("alice@example.com")).not.toBeInTheDocument();
    expect(screen.queryByText("2 total users")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Invite User" }),
    ).not.toBeInTheDocument();
    await waitFor(() => {
      expect(consoleError).toHaveBeenCalledTimes(1);
    });
    expect(consoleError).toHaveBeenCalledWith(
      "[UsersTab] User controls access restricted",
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry admin load" }));
    expect(refetch).toHaveBeenCalledTimes(1);
    consoleError.mockRestore();
  });

  it("keeps stale user rows visible but locks admin mutations when refresh fails", () => {
    mockUseAdminUsers.mockReturnValue({
      data: { items: users, total: 40, capabilities: tenantCapabilities },
      isLoading: false,
      error: new Error("user directory refresh failed"),
      refetch: vi.fn(),
    });

    render(<UsersTab />);

    expect(screen.getByText("40 total users")).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(
      screen.getByText(/User controls refresh failed/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Invite User" })).toBeDisabled();
    expect(
      screen.getByLabelText("Review role change for alice@example.com"),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Invite User" }));
    expect(screen.queryByLabelText("Email Address")).not.toBeInTheDocument();
    fireEvent.change(
      screen.getByLabelText("Review role change for alice@example.com"),
      {
        target: { value: "attorney" },
      },
    );
    expect(screen.queryByText("Review role change")).not.toBeInTheDocument();
    expect(mockUpdateRoleMutate).not.toHaveBeenCalled();
  });

  it("locks the invite form while a send request is pending", () => {
    mockInviteMutate.mockImplementation(() => {});

    render(<UsersTab />);

    fireEvent.click(screen.getByRole("button", { name: "Invite User" }));
    const emailInput = screen.getByLabelText("Email Address");
    const roleSelect = screen.getByLabelText("Invite role");
    const sendButton = screen.getByRole("button", { name: "Send Invite" });
    fireEvent.change(emailInput, {
      target: { value: "new.user@example.com" },
    });
    fireEvent.click(sendButton);
    fireEvent.click(sendButton);

    expect(mockInviteMutate).toHaveBeenCalledTimes(1);
    expect(emailInput).toBeDisabled();
    expect(roleSelect).toBeDisabled();
    expect(sendButton).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Close invite form" }),
    ).toBeDisabled();
  });

  it("keeps an unconfirmed operation visible and requires explicit reconciliation", async () => {
    const openOperation = {
      operation_id: "operation-role-1",
      operation_type: "role_update",
      state: "role_call_started",
      outcome_confirmed: false,
      reconciliation_required: true,
      provider_resource_id: null,
      target_user_id: "user-1",
      target_email_normalized: null,
      requested_role: "attorney",
      updated_at: "2026-07-14T08:00:00Z",
    };
    mockUseAdminOperations.mockReturnValue({
      data: { items: [openOperation] },
      isLoading: false,
      error: null,
    });

    const firstMount = render(<UsersTab />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Role update for user-1: unconfirmed",
    );
    expect(screen.getByTestId("admin-operation-status-panel")).toHaveClass(
      "scroll-mt-20",
    );
    expect(screen.getByRole("button", { name: "Reconcile now" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Invite User" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Reconcile now" }));
    await waitFor(() =>
      expect(mockReconcileOperationMutate).toHaveBeenCalledWith({
        operationId: "operation-role-1",
        recoveryAction: undefined,
      }),
    );

    firstMount.unmount();
    const secondMount = render(<UsersTab />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Role update for user-1: unconfirmed",
    );
    expect(screen.getByRole("button", { name: "Reconcile now" })).toBeVisible();

    mockUseAdminOperations.mockReturnValue({
      data: {
        items: [
          {
            ...openOperation,
            state: "completed",
            outcome_confirmed: true,
            reconciliation_required: false,
          },
        ],
      },
      isLoading: false,
      error: null,
    });
    secondMount.rerender(<UsersTab />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Role update for user-1: reconciled",
    );
    expect(
      screen.queryByRole("button", { name: "Reconcile now" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Invite User" })).toBeEnabled();
  });

  it("keeps controls locked until the refreshed open operation count reaches zero", () => {
    const completedOperation = {
      operation_id: "operation-terminal-1",
      operation_type: "role_update",
      state: "completed",
      outcome_confirmed: true,
      reconciliation_required: false,
      provider_resource_id: null,
      target_user_id: "user-1",
      target_email_normalized: null,
      requested_role: "attorney",
      updated_at: "2026-07-14T08:00:00Z",
    };
    mockUseAdminOperations.mockReturnValue({
      data: {
        items: [completedOperation],
        open_total: 1,
        has_more: true,
      },
      isLoading: false,
      error: null,
    });

    const view = render(<UsersTab />);

    expect(screen.getByRole("button", { name: "Invite User" })).toBeDisabled();
    expect(
      screen.getByLabelText("Review role change for alice@example.com"),
    ).toBeDisabled();

    mockUseAdminOperations.mockReturnValue({
      data: {
        items: [completedOperation],
        open_total: 0,
        has_more: false,
      },
      isLoading: false,
      error: null,
    });
    view.rerender(<UsersTab />);

    expect(screen.getByRole("button", { name: "Invite User" })).toBeEnabled();
    expect(
      screen.getByLabelText("Review role change for alice@example.com"),
    ).toBeEnabled();
  });

  it("unlocks the workspace after terminal failure while keeping the unsynchronized target read-only", () => {
    mockUseAdminUsers.mockReturnValue({
      data: {
        items: [
          {
            ...users[0],
            role: "client",
            membership_active: true,
            membership_synchronized: false,
          },
          users[1],
        ],
        total: 2,
        capabilities: tenantCapabilities,
      },
      isLoading: false,
      error: null,
    });
    mockUseAdminOperations.mockReturnValue({
      data: {
        items: [
          {
            operation_id: "operation-partial-rejection-1",
            operation_type: "role_update",
            state: "failed",
            outcome_confirmed: false,
            reconciliation_required: false,
            provider_resource_id: null,
            target_user_id: "user-1",
            target_email_normalized: null,
            requested_role: "client",
            updated_at: "2026-07-14T08:00:00Z",
          },
        ],
        open_total: 0,
        has_more: false,
      },
      isLoading: false,
      error: null,
    });

    render(<UsersTab />);

    expect(screen.getByRole("button", { name: "Invite User" })).toBeEnabled();
    expect(
      screen.getByLabelText(
        "Role controls for alice@example.com are read-only",
      ),
    ).toHaveTextContent("Clerk authority must reconcile before role changes");
    expect(
      screen.getByLabelText("Review role change for bob@example.com"),
    ).toBeEnabled();
  });

  it("offers a persistent authority recheck when membership synchronization is stale", () => {
    const usersRefetch = vi.fn();
    const operationsRefetch = vi.fn();
    mockUseAdminUsers.mockReturnValue({
      data: {
        items: [
          {
            ...users[0],
            membership_active: true,
            membership_synchronized: false,
          },
        ],
        total: 1,
        capabilities: tenantCapabilities,
      },
      isLoading: false,
      error: null,
      refetch: usersRefetch,
    });
    mockUseAdminOperations.mockReturnValue({
      data: { items: [], open_total: 0, has_more: false },
      isLoading: false,
      error: null,
      refetch: operationsRefetch,
    });

    render(<UsersTab />);

    const recovery = screen.getByTestId("admin-authority-unsynchronized-panel");
    expect(recovery).toHaveClass("scroll-mt-20");
    expect(recovery).toHaveTextContent(
      "1 user remains read-only because membership authority is not synchronized",
    );
    const recheck = within(recovery).getByRole("button", {
      name: "Recheck authority",
    });
    expect(recheck).toHaveClass("min-h-11", "w-full", "sm:w-auto");

    fireEvent.click(recheck);

    expect(usersRefetch).toHaveBeenCalledTimes(1);
    expect(operationsRefetch).toHaveBeenCalledTimes(1);
  });

  it("offers only the explicit proven-rejected coarse-role recovery", async () => {
    mockUseAdminOperations.mockReturnValue({
      data: {
        items: [
          {
            operation_id: "operation-partial-rejection-1",
            operation_type: "role_update",
            state: "failed",
            outcome_confirmed: false,
            reconciliation_required: true,
            recovery_available: true,
            recovery_action: "retry_rejected_role",
            provider_resource_id: null,
            target_user_id: "user-1",
            target_email_normalized: null,
            requested_role: "client",
            updated_at: "2026-07-14T08:00:00Z",
          },
        ],
        open_total: 0,
        has_more: false,
      },
      isLoading: false,
      error: null,
    });

    render(<UsersTab />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "retry only that proven-rejected step",
    );
    expect(screen.getByRole("button", { name: "Invite User" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Reconcile now" }));
    await waitFor(() =>
      expect(mockReconcileOperationMutate).toHaveBeenCalledWith({
        operationId: "operation-partial-rejection-1",
        recoveryAction: "retry_rejected_role",
      }),
    );
  });

  it("keeps cross-org role rows read-only when the API cannot mutate them", () => {
    mockUseAdminUsers.mockReturnValue({
      data: {
        items: [
          {
            ...users[0],
            id: "user-cross-org",
            email: "other-org@example.com",
            org_id: "org-2",
            org_name: "Other Therapeutics",
          },
        ],
        total: 1,
        capabilities: {
          ...tenantCapabilities,
          is_platform_superadmin: true,
          can_list_cross_org_users: true,
        },
      },
      isLoading: false,
      error: null,
    });

    render(<UsersTab />);

    expect(screen.getByText("Read-only")).toBeInTheDocument();
    const readOnlyControl = screen.getByLabelText(
      "Role controls for other-org@example.com are read-only",
    );
    expect(readOnlyControl).toHaveAccessibleDescription(
      "Role changes stay within the admin's organization",
    );
    expect(
      screen.queryByLabelText("Review role change for other-org@example.com"),
    ).not.toBeInTheDocument();
  });

  it("shows loading and empty states through the shell", () => {
    mockUseAdminUsers.mockReturnValueOnce({
      data: undefined,
      isLoading: true,
      error: null,
    });

    const { rerender } = render(<UsersTab />);
    expect(screen.getByRole("status", { hidden: true })).toBeInTheDocument();

    mockUseAdminUsers.mockReturnValueOnce({
      data: { items: [], total: 0, capabilities: tenantCapabilities },
      isLoading: false,
      error: null,
    });

    rerender(<UsersTab />);
    expect(screen.getByText("No users")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Users will appear here once they join your organization.",
      ),
    ).toBeInTheDocument();
  });

  it("paginates when there are multiple pages", () => {
    render(<UsersTab />);

    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(mockUseAdminUsers).toHaveBeenLastCalledWith(2);
  });
});
