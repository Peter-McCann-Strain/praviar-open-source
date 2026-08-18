"use client";

import { useEffect, useRef, useState } from "react";
import { Users } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ADMIN_BUTTON_TARGET_CLASS,
  ADMIN_FIELD_CLASS,
  ROLE_OPTIONS,
  relativeTime,
} from "@/components/admin-dashboard/helpers";
import { formatRoleLabel } from "@/components/admin-dashboard/users-tab-helpers";
import type { AdminCapabilities, UserSummary } from "@/hooks/use-admin";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";

interface RoleChangeMutationOptions {
  onSuccess?: () => void;
  onError?: () => void;
}

const ROLE_REVIEW_COPY: Record<string, { summary: string; guardrail: string }> =
  {
    admin: {
      summary:
        "Can operate organization admin controls and governed review workflows where backend policy permits.",
      guardrail:
        "Highest tenant role. Use only for people accountable for access governance.",
    },
    attorney: {
      summary:
        "Can review restricted report details, reviewer decisions, comments, and governed presets.",
      guardrail:
        "Best for qualified legal reviewers and patent counsel workflows.",
    },
    scientist: {
      summary:
        "Can run compound workflows and collaborate on evidence without admin governance controls.",
      guardrail:
        "Best for R&D users who need practical analysis access, not tenant administration.",
    },
    client: {
      summary:
        "Can view assigned report/evidence surfaces without reviewer or admin controls.",
      guardrail: "Best for external or limited-access stakeholders.",
    },
  };

export function UsersTabTable({
  users,
  capabilities,
  onRoleChange,
  pendingUserId,
  controlsDisabled = false,
}: {
  users: UserSummary[];
  capabilities: AdminCapabilities;
  onRoleChange: (
    args: { userId: string; role: string },
    options?: RoleChangeMutationOptions,
  ) => void;
  pendingUserId?: string;
  controlsDisabled?: boolean;
}) {
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);
  const [draftChange, setDraftChange] = useState<{
    userId: string;
    role: string;
  } | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const activeDraftChange = controlsDisabled ? null : draftChange;
  const draftUser = activeDraftChange
    ? (users.find((user) => user.id === activeDraftChange.userId) ?? null)
    : null;
  const hasActiveDraft = Boolean(
    draftUser && activeDraftChange && draftUser.role !== activeDraftChange.role,
  );

  useEffect(() => {
    if (!controlsDisabled) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setDraftChange(null);
      setDraftError(null);
    });
    return () => {
      cancelled = true;
    };
  }, [controlsDisabled]);

  if (users.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={Users}
            title="No users"
            description="Users will appear here once they join your organization."
            surface="embedded"
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card className="overflow-hidden">
        <CardContent className="p-0">
          <div
            aria-label="Admin user access table"
            className="overflow-x-auto p-3 [scrollbar-gutter:stable] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] lg:p-0"
            role="region"
            tabIndex={0}
          >
            <table className="w-full min-w-0 text-sm lg:min-w-[980px] lg:table-fixed">
              <caption className="sr-only">
                Admin user access table with role, organization, last activity,
                and reviewed role-change controls.
              </caption>
              <colgroup className="hidden lg:table-column-group">
                <col className="w-[23%]" />
                <col className="w-[13%]" />
                <col className="w-[14%]" />
                <col className="w-[18%]" />
                <col className="w-[10%]" />
                <col className="w-[22%]" />
              </colgroup>
              <thead className="sr-only lg:not-sr-only lg:table-header-group">
                <tr className="border-b border-[var(--border-subtle)]">
                  <th
                    scope="col"
                    className="whitespace-nowrap px-4 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Email
                  </th>
                  <th
                    scope="col"
                    className="whitespace-nowrap px-4 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Name
                  </th>
                  <th
                    scope="col"
                    className="whitespace-nowrap px-4 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Role
                  </th>
                  <th
                    scope="col"
                    className="whitespace-nowrap px-4 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Organization
                  </th>
                  <th
                    scope="col"
                    className="whitespace-nowrap px-4 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Last Active
                  </th>
                  <th
                    scope="col"
                    className="whitespace-nowrap px-4 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Role governance
                  </th>
                </tr>
              </thead>
              <tbody className="block space-y-3 lg:table-row-group lg:divide-y lg:divide-[var(--border-subtle)] lg:space-y-0">
                {users.map((user) => {
                  const proposedRole =
                    activeDraftChange?.userId === user.id &&
                    activeDraftChange.role !== user.role
                      ? activeDraftChange.role
                      : null;
                  const isPending = pendingUserId === user.id;
                  const isCrossOrgUser =
                    user.org_id !== capabilities.admin_org_id;
                  const isAuthoritySynchronized =
                    user.membership_active !== false &&
                    user.membership_synchronized !== false;
                  const canReviewRoleChange =
                    isAuthoritySynchronized &&
                    (!isCrossOrgUser ||
                      capabilities.can_manage_cross_org_user_roles);
                  const roleLockReasonId = `user-role-lock-${user.id}`;
                  const proposedRoleId = `user-role-proposed-${user.id}`;

                  return (
                    <tr
                      key={user.id}
                      className="block rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3 shadow-[var(--shadow-xs)] transition-colors hover:bg-[var(--surface-subtle)] lg:table-row lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none"
                    >
                      <td className="grid grid-cols-1 items-start gap-1.5 py-2 text-sm text-[var(--text-primary)] sm:grid-cols-[6.75rem_minmax(0,1fr)] sm:gap-3 lg:table-cell lg:px-4 lg:py-3">
                        <span
                          aria-hidden="true"
                          className="text-xs font-medium uppercase text-[var(--text-tertiary)] lg:hidden"
                        >
                          Email
                        </span>
                        <span
                          className="min-w-0 font-semibold [overflow-wrap:anywhere] lg:block lg:truncate lg:font-normal"
                          title={user.email}
                        >
                          {user.email}
                        </span>
                      </td>
                      <td className="grid grid-cols-1 items-start gap-1.5 py-2 text-sm text-[var(--text-primary)] sm:grid-cols-[6.75rem_minmax(0,1fr)] sm:gap-3 lg:table-cell lg:px-4 lg:py-3">
                        <span
                          aria-hidden="true"
                          className="text-xs font-medium uppercase text-[var(--text-tertiary)] lg:hidden"
                        >
                          Name
                        </span>
                        <span
                          className="min-w-0 [overflow-wrap:anywhere] lg:block lg:truncate"
                          title={user.full_name || "--"}
                        >
                          {user.full_name || "--"}
                        </span>
                      </td>
                      <td className="grid grid-cols-1 items-start gap-1.5 py-2 sm:grid-cols-[6.75rem_minmax(0,1fr)] sm:items-center sm:gap-3 lg:table-cell lg:px-4 lg:py-3">
                        <span
                          aria-hidden="true"
                          className="text-xs font-medium uppercase text-[var(--text-tertiary)] lg:hidden"
                        >
                          Role
                        </span>
                        <div className="space-y-1.5">
                          <span className="inline-flex items-center rounded-full border border-[var(--border-default)] px-2.5 py-0.5 text-xs font-medium capitalize text-[var(--text-secondary)]">
                            {user.role}
                          </span>
                          <p
                            className={`text-xs ${
                              isAuthoritySynchronized
                                ? "text-[var(--text-tertiary)]"
                                : "font-medium text-warning"
                            }`}
                          >
                            {isAuthoritySynchronized
                              ? "Clerk synchronized"
                              : "Reconciliation required"}
                          </p>
                        </div>
                      </td>
                      <td className="grid grid-cols-1 items-start gap-1.5 py-2 text-sm text-[var(--text-secondary)] sm:grid-cols-[6.75rem_minmax(0,1fr)] sm:gap-3 lg:table-cell lg:px-4 lg:py-3">
                        <span
                          aria-hidden="true"
                          className="text-xs font-medium uppercase text-[var(--text-tertiary)] lg:hidden"
                        >
                          Organization
                        </span>
                        <span
                          className="min-w-0 [overflow-wrap:anywhere] lg:block lg:truncate"
                          title={user.org_name}
                        >
                          {user.org_name}
                        </span>
                      </td>
                      <td className="grid grid-cols-1 items-start gap-1.5 py-2 text-xs tabular-nums text-[var(--text-tertiary)] sm:grid-cols-[6.75rem_minmax(0,1fr)] sm:items-center sm:gap-3 lg:table-cell lg:px-4 lg:py-3 lg:text-right">
                        <span
                          aria-hidden="true"
                          className="text-xs font-medium uppercase text-[var(--text-tertiary)] lg:hidden"
                        >
                          Last active
                        </span>
                        <span className="whitespace-nowrap">
                          {user.last_active_at
                            ? formatRelativeTime(user.last_active_at)
                            : "Never"}
                        </span>
                      </td>
                      <td className="block pt-3 lg:table-cell lg:px-4 lg:py-3 lg:text-right">
                        <div className="grid grid-cols-1 items-start gap-1.5 sm:grid-cols-[6.75rem_minmax(0,1fr)] sm:gap-3 lg:block">
                          <span
                            aria-hidden="true"
                            className="text-xs font-medium uppercase text-[var(--text-tertiary)] lg:hidden"
                          >
                            Governance
                          </span>
                          {canReviewRoleChange ? (
                            <div className="min-w-0 space-y-3">
                              <select
                                value={user.role}
                                disabled={isPending || controlsDisabled}
                                onChange={(e) => {
                                  if (controlsDisabled) return;
                                  const role = e.target.value;
                                  setDraftError(null);
                                  setDraftChange(
                                    role === user.role
                                      ? null
                                      : { userId: user.id, role },
                                  );
                                }}
                                aria-label={`Review role change for ${user.email}`}
                                aria-describedby={
                                  proposedRole ? proposedRoleId : undefined
                                }
                                className={`${ADMIN_FIELD_CLASS} w-full text-[var(--text-secondary)] lg:w-auto`}
                              >
                                {ROLE_OPTIONS.map((role) => (
                                  <option key={role} value={role}>
                                    {formatRoleLabel(role)}
                                  </option>
                                ))}
                              </select>
                              {proposedRole ? (
                                <p
                                  id={proposedRoleId}
                                  role="status"
                                  className="text-xs leading-5 text-warning"
                                >
                                  Proposed: {formatRoleLabel(proposedRole)}
                                </p>
                              ) : null}
                            </div>
                          ) : (
                            <div
                              aria-describedby={roleLockReasonId}
                              aria-label={`Role controls for ${user.email} are read-only`}
                              className="flex w-full max-w-none flex-col items-start rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/60 px-3 py-2 text-left lg:inline-flex lg:items-end lg:text-right"
                            >
                              <span className="text-xs font-semibold text-[var(--text-secondary)]">
                                Read-only
                              </span>
                              <span
                                id={roleLockReasonId}
                                className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]"
                              >
                                {isAuthoritySynchronized
                                  ? "Role changes stay within the admin's organization"
                                  : "Clerk authority must reconcile before role changes"}
                              </span>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      {draftUser && activeDraftChange && hasActiveDraft ? (
        <RoleChangeReviewDialog
          currentRole={draftUser.role}
          proposedRole={activeDraftChange.role}
          email={draftUser.email}
          orgName={draftUser.org_name}
          isPending={pendingUserId === draftUser.id}
          error={draftError}
          onApply={() => {
            setDraftError(null);
            onRoleChange(
              { userId: draftUser.id, role: activeDraftChange.role },
              {
                onSuccess: () => {
                  setDraftChange(null);
                },
                onError: () => {
                  setDraftError(
                    "Role update outcome is unconfirmed. Authoritative membership state is being refreshed; retry is safe.",
                  );
                },
              },
            );
          }}
          onCancel={() => {
            setDraftChange(null);
            setDraftError(null);
          }}
        />
      ) : null}
    </>
  );
}

function RoleChangeReviewDialog({
  currentRole,
  proposedRole,
  email,
  orgName,
  isPending,
  error,
  onApply,
  onCancel,
}: {
  currentRole: string;
  proposedRole: string;
  email: string;
  orgName: string;
  isPending: boolean;
  error: string | null;
  onApply: () => void;
  onCancel: () => void;
}) {
  const submittedRef = useRef(false);
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const currentRoleCopy = getRoleReviewCopy(currentRole);
  const proposedRoleCopy = getRoleReviewCopy(proposedRole);
  const applyPending = isPending || (hasSubmitted && !error);

  useEffect(() => {
    if (!error) return;
    submittedRef.current = false;
  }, [error]);

  const handleApply = () => {
    if (applyPending || submittedRef.current) return;
    submittedRef.current = true;
    setHasSubmitted(true);
    try {
      onApply();
    } catch (error) {
      submittedRef.current = false;
      setHasSubmitted(false);
      throw error;
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !applyPending) onCancel();
      }}
    >
      <DialogContent className="max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] gap-3 p-4 sm:max-h-[calc(100dvh-2rem)] sm:w-full sm:gap-4 sm:p-6">
        <DialogHeader className="pr-8 text-left">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-warning">
            Role review
          </p>
          <DialogTitle>Review role change</DialogTitle>
          <DialogDescription className="[overflow-wrap:anywhere]">
            {formatRoleLabel(currentRole)} to {formatRoleLabel(proposedRole)}{" "}
            for{" "}
            <span className="font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {email}
            </span>{" "}
            in{" "}
            <span className="font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {orgName}
            </span>
            <span className="hidden sm:inline">
              . Praviar records the applied role change in the admin audit log.
            </span>
            <span className="sm:hidden">.</span>
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/50 p-2 text-sm sm:gap-3 sm:p-3">
          <RoleImpactColumn
            label="Current access"
            role={currentRole}
            summary={currentRoleCopy.summary}
            guardrail={currentRoleCopy.guardrail}
          />
          <RoleImpactColumn
            label="Proposed access"
            role={proposedRole}
            summary={proposedRoleCopy.summary}
            guardrail={proposedRoleCopy.guardrail}
            isProposed
          />
          <details className="col-span-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 px-3 py-2 sm:hidden">
            <summary className="flex min-h-11 cursor-pointer items-center text-xs font-semibold text-[var(--text-secondary)]">
              Compare permission impact
            </summary>
            <div className="mt-2 space-y-2 text-xs leading-5 text-[var(--text-secondary)]">
              <p>
                <span className="font-semibold text-[var(--text-primary)]">
                  Current:
                </span>{" "}
                {formatRoleLabel(currentRole)} permissions and guardrails remain
                in effect until this change is applied.
              </p>
              <p>
                <span className="font-semibold text-[var(--text-primary)]">
                  Proposed:
                </span>{" "}
                {formatRoleLabel(proposedRole)} permissions take effect after
                backend policy accepts the change.
              </p>
            </div>
          </details>
        </div>
        <div className="rounded-lg border border-warning/25 bg-warning/10 p-3 text-sm leading-5 text-[var(--text-secondary)] [overflow-wrap:anywhere] sm:leading-6">
          <p className="font-semibold text-[var(--text-primary)]">
            <span className="sm:hidden">
              Backend permission checks stay authoritative.
            </span>
            <span className="hidden sm:inline">
              Backend permission checks remain authoritative after this change.
            </span>
          </p>
          <p className="mt-1 hidden sm:block">
            Existing analyses, evidence, and audit history remain scoped to{" "}
            <span className="font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {orgName}
            </span>
            .
          </p>
        </div>
        {error ? (
          <div
            role="alert"
            className="rounded-lg border border-error/25 bg-error/10 p-3 text-sm leading-6 text-error"
          >
            {error}
          </div>
        ) : null}
        <DialogFooter className="grid grid-cols-2 gap-2 sm:flex sm:space-x-0">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className={ADMIN_BUTTON_TARGET_CLASS}
            disabled={applyPending}
            onClick={onCancel}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            aria-label={`Apply role change for ${email}`}
            className={ADMIN_BUTTON_TARGET_CLASS}
            loading={applyPending}
            onClick={handleApply}
          >
            Apply role change
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function getRoleReviewCopy(role: string) {
  return (
    ROLE_REVIEW_COPY[role] ?? {
      summary:
        "Uses the role recorded by the admin API; review backend policy before applying.",
      guardrail:
        "Unknown role label. Apply only after confirming the user needs it.",
    }
  );
}

function RoleImpactColumn({
  guardrail,
  isProposed = false,
  label,
  role,
  summary,
}: {
  guardrail: string;
  isProposed?: boolean;
  label: string;
  role: string;
  summary: string;
}) {
  return (
    <div
      className={`min-w-0 rounded-md border p-2 sm:p-3 ${
        isProposed
          ? "border-brand-primary/25 bg-brand-primary/8"
          : "border-[var(--border-subtle)] bg-[var(--bg-surface)]/72"
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
        {formatRoleLabel(role)}
      </p>
      <p className="mt-2 hidden text-xs leading-5 text-[var(--text-secondary)] sm:block">
        {summary}
      </p>
      <p className="mt-2 hidden text-xs leading-5 text-[var(--text-tertiary)] sm:block">
        {guardrail}
      </p>
    </div>
  );
}
