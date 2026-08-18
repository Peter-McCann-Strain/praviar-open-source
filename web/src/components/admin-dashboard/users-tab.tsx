"use client";

import { useEffect, useState } from "react";
import { RefreshCw, UserPlus } from "lucide-react";
import {
  ADMIN_BUTTON_TARGET_CLASS,
  AdminPagedEmptyState,
  AdminRefreshWarning,
  AdminStatusState,
} from "@/components/admin-dashboard/helpers";
import { Button } from "@/components/ui/button";
import {
  useAdminUsers,
  useAdminOperations,
  useInviteUser,
  useReconcileAdminOperation,
  useUpdateUserRole,
} from "@/hooks/use-admin";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import { isAuthBoundaryError } from "@/lib/api-client";
import { UsersTabInvitePanel } from "@/components/admin-dashboard/users-tab-invite-panel";
import { UsersTabPagination } from "@/components/admin-dashboard/users-tab-pagination";
import { UsersTabTable } from "@/components/admin-dashboard/users-tab-table";
import { USERS_PER_PAGE } from "@/components/admin-dashboard/users-tab-helpers";
import type {
  AdminCapabilities,
  AdminOperationNotice,
  AdminOperationStatus,
} from "@/hooks/use-admin";

function reportUserControlsAccessRestriction() {
  console.error("[UsersTab] User controls access restricted");
}

function reportUserDirectoryLoadFailure() {
  console.error("[UsersTab] Failed to load users");
}

const FALLBACK_ADMIN_CAPABILITIES: AdminCapabilities = {
  admin_org_id: "",
  is_platform_superadmin: false,
  can_manage_org_billing: false,
  can_list_cross_org_users: false,
  can_manage_cross_org_user_roles: false,
  can_inspect_task_queue: false,
};

export function UsersTab() {
  const [page, setPage] = useState(1);
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteEmailError, setInviteEmailError] = useState<string | null>(null);
  const [inviteRole, setInviteRole] = useState("scientist");
  const [inviteSubmissionLocked, setInviteSubmissionLocked] = useState(false);
  const { data, isLoading, error, refetch } = useAdminUsers(page);
  const updateRole = useUpdateUserRole();
  const inviteUser = useInviteUser();
  const operations = useAdminOperations();
  const reconcileOperation = useReconcileAdminOperation();
  const authoritativeOperation =
    operations.data?.items.find(
      (operation) => operation.reconciliation_required,
    ) ?? operations.data?.items[0];
  const authoritativeNotice = authoritativeOperation
    ? operationNoticeFromStatus(authoritativeOperation)
    : null;
  const localNotice = updateRole.operationNotice ?? inviteUser.operationNotice;
  const visibleNotice = authoritativeNotice ?? localNotice;
  const unsynchronizedUserCount =
    data?.items.filter(
      (user) =>
        user.membership_active === false ||
        user.membership_synchronized === false,
    ).length ?? 0;
  const inviteSubmissionPending =
    inviteUser.isPending || inviteSubmissionLocked;
  const accessRestricted = isAuthBoundaryError(error);
  const initialLoading = isLoading && !data;
  const userDirectoryUnavailable = Boolean(
    !initialLoading && error && !data && !accessRestricted,
  );
  const hasUnconfirmedOperation =
    (operations.data?.open_total ?? 0) > 0 ||
    visibleNotice?.canReconcile === true;
  const operationRecoveryUnavailable = Boolean(operations.error);
  const adminControlsLocked =
    Boolean(error) ||
    hasUnconfirmedOperation ||
    operationRecoveryUnavailable ||
    operations.isLoading;

  const isValidEmail = (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

  const handleInvite = () => {
    if (inviteSubmissionPending || adminControlsLocked) {
      return;
    }

    const email = inviteEmail.trim();
    if (!email || !isValidEmail(email)) {
      setInviteEmailError(
        "Enter a valid work email address before sending an invite.",
      );
      return;
    }
    setInviteEmailError(null);
    setInviteSubmissionLocked(true);
    inviteUser.mutate(
      { email, role: inviteRole },
      {
        onSuccess: () => {
          setInviteEmail("");
          setInviteEmailError(null);
          setInviteRole("scientist");
          setInviteSubmissionLocked(false);
          setShowInvite(false);
        },
        onError: () => {
          setInviteSubmissionLocked(false);
        },
      },
    );
  };

  const totalPages = Math.ceil((data?.total ?? 0) / USERS_PER_PAGE);
  const displayPage = totalPages >= 1 ? Math.min(page, totalPages) : page;
  const hasPagedEmptyState = Boolean(
    data && data.items.length === 0 && data.total > 0,
  );

  useEffect(() => {
    if (!adminControlsLocked) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setShowInvite(false);
      setInviteEmailError(null);
    });
    return () => {
      cancelled = true;
    };
  }, [adminControlsLocked]);

  useEffect(() => {
    if (!showInvite || adminControlsLocked) return;
    const frame = requestAnimationFrame(() => {
      document.getElementById("invite-user-email")?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [adminControlsLocked, showInvite]);

  useErrorDiagnostic(
    !initialLoading && accessRestricted,
    error,
    reportUserControlsAccessRestriction,
  );
  useErrorDiagnostic(
    userDirectoryUnavailable,
    error,
    reportUserDirectoryLoadFailure,
  );

  if (initialLoading) {
    return <AdminStatusState surface="users" variant="loading" />;
  }

  if (accessRestricted) {
    return (
      <AdminStatusState
        surface="users"
        variant="restricted"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (error && !data) {
    return (
      <AdminStatusState
        surface="users"
        variant="temporary"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (!data) {
    return <AdminStatusState surface="users" variant="auth" />;
  }

  return (
    <div className="space-y-4">
      {visibleNotice ? (
        <AdminOperationStatusPanel
          label={operationStatusLabel(authoritativeOperation)}
          notice={visibleNotice}
          isReconciling={reconcileOperation.isPending}
          onReconcile={() => {
            if (authoritativeOperation) {
              reconcileOperation.mutate({
                operationId: authoritativeOperation.operation_id,
                recoveryAction: authoritativeOperation.recovery_available
                  ? "retry_rejected_role"
                  : undefined,
              });
            }
          }}
        />
      ) : null}
      {!visibleNotice && unsynchronizedUserCount > 0 ? (
        <AdminAuthorityRecoveryPanel
          unsynchronizedUserCount={unsynchronizedUserCount}
          onRefresh={() => {
            void refetch();
            void operations.refetch();
          }}
        />
      ) : null}
      {error ? <AdminRefreshWarning label="User controls" /> : null}
      {operations.error ? (
        <AdminRefreshWarning label="Admin operation recovery" />
      ) : null}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-[var(--text-tertiary)]">
          {data.total} total users
        </p>
        <Button
          className={`${ADMIN_BUTTON_TARGET_CLASS} w-full gap-2 sm:w-auto`}
          size="sm"
          disabled={inviteSubmissionPending || adminControlsLocked}
          aria-expanded={showInvite}
          aria-controls="invite-user-panel"
          onClick={() => {
            if (adminControlsLocked) return;
            setInviteEmailError(null);
            setShowInvite(!showInvite);
          }}
        >
          <UserPlus className="h-4 w-4" aria-hidden="true" />
          {showInvite ? "Close invite form" : "Invite User"}
        </Button>
      </div>

      {showInvite && !adminControlsLocked && (
        <div id="invite-user-panel">
          <UsersTabInvitePanel
            email={inviteEmail}
            emailError={inviteEmailError}
            role={inviteRole}
            loading={inviteSubmissionPending}
            onEmailChange={(value) => {
              setInviteEmail(value);
              if (inviteEmailError) setInviteEmailError(null);
            }}
            onRoleChange={setInviteRole}
            onSubmit={handleInvite}
          />
        </div>
      )}

      {hasPagedEmptyState ? (
        <AdminPagedEmptyState
          title="No users on this page"
          description="The user directory still has records, but this page no longer has rows. Return to the first page to reload the active user list."
          actionLabel="Return to first page"
          onAction={() => setPage(1)}
        />
      ) : (
        <UsersTabTable
          users={data.items}
          capabilities={data.capabilities ?? FALLBACK_ADMIN_CAPABILITIES}
          onRoleChange={(args, options) => updateRole.mutate(args, options)}
          pendingUserId={
            updateRole.isPending ? updateRole.variables?.userId : undefined
          }
          controlsDisabled={adminControlsLocked}
        />
      )}

      {totalPages > 1 && (
        <UsersTabPagination
          page={displayPage}
          totalPages={totalPages}
          onPrevious={() =>
            setPage((current) =>
              current > totalPages ? totalPages : Math.max(1, current - 1),
            )
          }
          onNext={() => setPage((current) => Math.min(totalPages, current + 1))}
          disabled={adminControlsLocked}
        />
      )}
    </div>
  );
}

function operationNoticeFromStatus(
  operation: AdminOperationStatus,
): AdminOperationNotice {
  if (operation.state === "completed") {
    return {
      kind: "reconciled",
      message: "Provider and Praviar authority are reconciled and confirmed.",
      canReconcile: false,
    };
  }
  if (operation.state === "failed") {
    if (operation.recovery_available) {
      return {
        kind: "unconfirmed",
        message:
          "Clerk accepted the least-privilege role metadata but rejected the coarse role change. Access remains denied; retry only that proven-rejected step.",
        canReconcile: true,
      };
    }
    return {
      kind: "failed",
      message:
        "The operation was rejected and was not applied. A new submission will create a new operation.",
      canReconcile: false,
    };
  }
  return {
    kind: "unconfirmed",
    message:
      "Provider outcome is unconfirmed. Reconcile authoritative state before another admin mutation.",
    canReconcile: true,
  };
}

function operationStatusLabel(operation?: AdminOperationStatus): string {
  if (!operation) return "Admin operation";
  if (operation.operation_type === "invite") {
    return operation.target_email_normalized
      ? `Invitation to ${operation.target_email_normalized}`
      : "Invitation operation";
  }
  return operation.target_user_id
    ? `Role update for ${operation.target_user_id}`
    : "Role operation";
}

function AdminOperationStatusPanel({
  label,
  notice,
  isReconciling,
  onReconcile,
}: {
  label: string;
  notice: AdminOperationNotice;
  isReconciling: boolean;
  onReconcile: () => void;
}) {
  const needsAttention = notice.kind !== "reconciled";
  return (
    <div
      role={needsAttention ? "alert" : "status"}
      data-testid="admin-operation-status-panel"
      className={`scroll-mt-20 flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between ${
        notice.kind === "reconciled"
          ? "border-success/25 bg-success/10"
          : notice.kind === "failed"
            ? "border-error/25 bg-error/10"
            : "border-warning/30 bg-warning/10"
      }`}
    >
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
          {label}: {notice.kind}
        </p>
        <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
          {notice.message}
        </p>
      </div>
      {notice.canReconcile ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className={`${ADMIN_BUTTON_TARGET_CLASS} shrink-0 gap-2`}
          loading={isReconciling}
          disabled={isReconciling}
          onClick={onReconcile}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Reconcile now
        </Button>
      ) : null}
    </div>
  );
}

function AdminAuthorityRecoveryPanel({
  unsynchronizedUserCount,
  onRefresh,
}: {
  unsynchronizedUserCount: number;
  onRefresh: () => void;
}) {
  const subject =
    unsynchronizedUserCount === 1
      ? "1 user remains"
      : `${unsynchronizedUserCount} users remain`;

  return (
    <div
      role="alert"
      data-testid="admin-authority-unsynchronized-panel"
      className="scroll-mt-20 rounded-lg border border-warning/30 bg-warning/10 p-4"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-warning">
            Clerk authority reconciliation required
          </p>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            {subject} read-only because membership authority is not
            synchronized. Recheck authoritative state before changing roles.
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className={`${ADMIN_BUTTON_TARGET_CLASS} w-full shrink-0 gap-2 sm:w-auto`}
          onClick={onRefresh}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Recheck authority
        </Button>
      </div>
    </div>
  );
}
