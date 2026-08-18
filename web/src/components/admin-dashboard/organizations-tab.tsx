"use client";

import { useEffect, useRef, useState } from "react";
import { Building2 } from "lucide-react";
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
  AdminPagedEmptyState,
  PLAN_OPTIONS,
  AdminRefreshWarning,
  AdminStatusState,
} from "@/components/admin-dashboard/helpers";
import { useAdminOrganizations, useUpdateOrg } from "@/hooks/use-admin";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import { isAuthBoundaryError } from "@/lib/api-client";
import type { OrgSummary } from "@/hooks/use-admin";

function reportOrganizationControlsAccessRestriction() {
  console.error("[OrganizationsTab] Organization controls access restricted");
}

function reportOrganizationsLoadFailure() {
  console.error("[OrganizationsTab] Failed to load organizations");
}

const PLAN_REVIEW_COPY: Record<string, { summary: string; guardrail: string }> =
  {
    free: {
      summary: "Introductory workspace for limited first-pass FTO screening.",
      guardrail:
        "Use when the tenant should stay on a constrained evaluation path.",
    },
    starter: {
      summary:
        "Self-serve team tier for repeat screening with a predictable monthly allowance.",
      guardrail:
        "Use for small teams that need reliable recurring report capacity.",
    },
    pro: {
      summary:
        "Full platform tier for active FTO programs and counsel handoffs.",
      guardrail:
        "Use for teams running larger search, evidence, export, and review workflows.",
    },
    enterprise: {
      summary:
        "Contracted workspace for negotiated procurement, SSO, and custom operating terms.",
      guardrail:
        "Use only when commercial terms and support expectations are confirmed.",
    },
  };

export function OrganizationsTab() {
  const [page, setPage] = useState(1);
  const [draftChange, setDraftChange] = useState<{
    orgId: string;
    plan: string;
  } | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const { data, isLoading, error, refetch } = useAdminOrganizations(page);
  const updateOrg = useUpdateOrg();
  const accessRestricted = isAuthBoundaryError(error);
  const initialLoading = isLoading && !data;
  const organizationsLoadFailed = Boolean(
    !initialLoading && error && !data && !accessRestricted,
  );
  const adminControlsLocked = Boolean(error);

  useErrorDiagnostic(
    !initialLoading && accessRestricted,
    error,
    reportOrganizationControlsAccessRestriction,
  );
  useErrorDiagnostic(
    organizationsLoadFailed,
    error,
    reportOrganizationsLoadFailure,
  );

  const totalPages = Math.ceil((data?.total ?? 0) / 20);
  const visiblePage = totalPages >= 1 ? Math.min(page, totalPages) : page;
  const canManageOrgBilling =
    data?.capabilities?.can_manage_org_billing ?? false;
  const activeDraftChange = adminControlsLocked ? null : draftChange;
  const draftOrg =
    activeDraftChange && data
      ? (data.items.find((org) => org.id === activeDraftChange.orgId) ?? null)
      : null;
  const hasActiveDraft = Boolean(
    draftOrg && activeDraftChange && draftOrg.plan !== activeDraftChange.plan,
  );

  useEffect(() => {
    if (!adminControlsLocked) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      setDraftChange(null);
      setDraftError(null);
    });
    return () => {
      cancelled = true;
    };
  }, [adminControlsLocked]);

  if (initialLoading) {
    return <AdminStatusState surface="organizations" variant="loading" />;
  }

  if (accessRestricted) {
    return (
      <AdminStatusState
        surface="organizations"
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
        surface="organizations"
        variant="temporary"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (!data) {
    return <AdminStatusState surface="organizations" variant="auth" />;
  }

  if (data.items.length === 0) {
    if (data.total > 0) {
      return (
        <div className="space-y-4">
          {error ? <AdminRefreshWarning label="Organization controls" /> : null}
          <AdminPagedEmptyState
            title="No organizations on this page"
            description="The organization directory still has records, but this page no longer has rows. Return to the first page to reload the active tenant list."
            actionLabel="Return to first page"
            onAction={() => setPage(1)}
          />
        </div>
      );
    }

    return (
      <div className="space-y-4">
        {error ? <AdminRefreshWarning label="Organization controls" /> : null}
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={Building2}
              title="No platform organizations yet"
              description="Tenant workspaces will appear here after onboarding or invitation acceptance."
              surface="embedded"
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error ? <AdminRefreshWarning label="Organization controls" /> : null}
      <Card className="overflow-hidden">
        <CardContent className="p-0">
          <div
            aria-label="Admin organization plan table"
            className="overflow-x-auto p-3 [scrollbar-gutter:stable] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] md:p-0"
            role="region"
            tabIndex={0}
          >
            <table className="w-full min-w-0 text-sm md:min-w-[920px]">
              <caption className="sr-only">
                Admin organization plan table with usage, allowance, and
                reviewed plan-change controls.
              </caption>
              <thead className="sr-only md:not-sr-only md:table-header-group">
                <tr className="border-b border-[var(--border-subtle)]">
                  <th
                    scope="col"
                    className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Organization
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Plan
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Users
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Analyses
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Free Remaining
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]"
                  >
                    Plan governance
                  </th>
                </tr>
              </thead>
              <tbody className="block space-y-3 md:table-row-group md:divide-y md:divide-[var(--border-subtle)] md:space-y-0">
                {data.items.map((org: OrgSummary) => {
                  const proposedPlan =
                    activeDraftChange?.orgId === org.id &&
                    activeDraftChange.plan !== org.plan
                      ? activeDraftChange.plan
                      : null;
                  const isPending =
                    updateOrg.isPending &&
                    updateOrg.variables?.orgId === org.id;
                  const readOnlyReasonId = `org-plan-readonly-${org.id}`;
                  const proposedPlanId = `org-plan-proposed-${org.id}`;

                  return (
                    <tr
                      key={org.id}
                      className="block rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/55 p-3 shadow-[var(--shadow-xs)] transition-colors hover:bg-[var(--surface-subtle)] md:table-row md:border-0 md:bg-transparent md:p-0 md:shadow-none"
                    >
                      <td className="grid grid-cols-[6.75rem_minmax(0,1fr)] items-start gap-3 py-2 md:table-cell md:px-6 md:py-3">
                        <span
                          aria-hidden="true"
                          className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden"
                        >
                          Organization
                        </span>
                        <div className="min-w-0">
                          <p className="min-w-0 text-sm font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
                            {org.name}
                          </p>
                          <p className="break-all text-xs text-[var(--text-tertiary)]">
                            {org.slug}
                          </p>
                        </div>
                      </td>
                      <td className="grid grid-cols-[6.75rem_minmax(0,1fr)] items-center gap-3 py-2 md:table-cell md:px-6 md:py-3">
                        <span
                          aria-hidden="true"
                          className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden"
                        >
                          Plan
                        </span>
                        <span className="inline-flex items-center rounded-full border border-[var(--border-default)] px-2.5 py-0.5 text-xs font-medium capitalize text-[var(--text-secondary)]">
                          {org.plan}
                        </span>
                      </td>
                      <td className="grid grid-cols-[6.75rem_minmax(0,1fr)] items-center gap-3 py-2 text-sm tabular-nums text-[var(--text-primary)] md:table-cell md:px-6 md:py-3 md:text-right">
                        <span
                          aria-hidden="true"
                          className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden"
                        >
                          Users
                        </span>
                        <span>{org.user_count}</span>
                      </td>
                      <td className="grid grid-cols-[6.75rem_minmax(0,1fr)] items-center gap-3 py-2 text-sm tabular-nums text-[var(--text-primary)] md:table-cell md:px-6 md:py-3 md:text-right">
                        <span
                          aria-hidden="true"
                          className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden"
                        >
                          Analyses
                        </span>
                        <span>{org.analysis_count}</span>
                      </td>
                      <td className="grid grid-cols-[6.75rem_minmax(0,1fr)] items-center gap-3 py-2 text-sm tabular-nums text-[var(--text-primary)] md:table-cell md:px-6 md:py-3 md:text-right">
                        <span
                          aria-hidden="true"
                          className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden"
                        >
                          Free left
                        </span>
                        <span>{org.free_analyses_remaining}</span>
                      </td>
                      <td className="block pt-3 md:table-cell md:px-6 md:py-3 md:text-right">
                        <div className="grid grid-cols-[6.75rem_minmax(0,1fr)] items-start gap-3 md:block">
                          <span
                            aria-hidden="true"
                            className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden"
                          >
                            Governance
                          </span>
                          {canManageOrgBilling ? (
                            <div className="min-w-0 space-y-3">
                              <select
                                value={org.plan}
                                aria-label={`Review plan change for ${org.name}`}
                                aria-describedby={
                                  proposedPlan ? proposedPlanId : undefined
                                }
                                disabled={isPending || adminControlsLocked}
                                onChange={(e) => {
                                  if (adminControlsLocked) return;
                                  const plan = e.target.value;
                                  setDraftError(null);
                                  setDraftChange(
                                    plan === org.plan
                                      ? null
                                      : { orgId: org.id, plan },
                                  );
                                }}
                                className={`${ADMIN_FIELD_CLASS} w-full text-[var(--text-secondary)] md:w-auto`}
                              >
                                {PLAN_OPTIONS.map((plan) => (
                                  <option key={plan} value={plan}>
                                    {formatPlanLabel(plan)}
                                  </option>
                                ))}
                              </select>
                              {proposedPlan ? (
                                <p
                                  id={proposedPlanId}
                                  role="status"
                                  className="text-xs leading-5 text-warning"
                                >
                                  Proposed: {formatPlanLabel(proposedPlan)}
                                </p>
                              ) : null}
                            </div>
                          ) : (
                            <div
                              aria-describedby={readOnlyReasonId}
                              aria-label={`Plan controls for ${org.name} are read-only`}
                              className="flex w-full max-w-none flex-col items-start rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/60 px-3 py-2 text-left md:inline-flex md:max-w-60 md:items-end md:text-right"
                            >
                              <span className="text-xs font-semibold text-[var(--text-secondary)]">
                                Read-only
                              </span>
                              <span
                                id={readOnlyReasonId}
                                className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]"
                              >
                                Plan changes require platform superadmin access.
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

      {totalPages > 1 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-[var(--text-tertiary)]">
            Page {visiblePage} of {totalPages} ({data.total} total)
          </p>
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <Button
              variant="outline"
              size="sm"
              disabled={adminControlsLocked || visiblePage <= 1}
              onClick={() => setPage(Math.max(1, visiblePage - 1))}
              className={ADMIN_BUTTON_TARGET_CLASS}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={adminControlsLocked || visiblePage >= totalPages}
              onClick={() => setPage(Math.min(totalPages, visiblePage + 1))}
              className={ADMIN_BUTTON_TARGET_CLASS}
            >
              Next
            </Button>
          </div>
        </div>
      )}
      {draftOrg && activeDraftChange && hasActiveDraft ? (
        <PlanChangeReviewDialog
          orgName={draftOrg.name}
          currentPlan={draftOrg.plan}
          proposedPlan={activeDraftChange.plan}
          analysisCount={draftOrg.analysis_count}
          monthlyAllowance={draftOrg.max_analyses_per_month}
          freeAnalysesRemaining={draftOrg.free_analyses_remaining}
          isPending={
            updateOrg.isPending && updateOrg.variables?.orgId === draftOrg.id
          }
          error={draftError}
          onApply={() => {
            setDraftError(null);
            updateOrg.mutate(
              {
                orgId: draftOrg.id,
                data: { plan: activeDraftChange.plan },
              },
              {
                onSuccess: () => {
                  setDraftChange(null);
                },
                onError: () => {
                  setDraftError(
                    "Plan change was not applied. Existing organization settings are unchanged.",
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
    </div>
  );
}

function formatPlanLabel(plan: string) {
  return plan.charAt(0).toUpperCase() + plan.slice(1);
}

function PlanChangeReviewDialog({
  orgName,
  currentPlan,
  proposedPlan,
  analysisCount,
  monthlyAllowance,
  freeAnalysesRemaining,
  isPending,
  error,
  onApply,
  onCancel,
}: {
  orgName: string;
  currentPlan: string;
  proposedPlan: string;
  analysisCount: number;
  monthlyAllowance: number;
  freeAnalysesRemaining: number;
  isPending: boolean;
  error: string | null;
  onApply: () => void;
  onCancel: () => void;
}) {
  const submittedRef = useRef(false);
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const currentPlanCopy = getPlanReviewCopy(currentPlan);
  const proposedPlanCopy = getPlanReviewCopy(proposedPlan);
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
      <DialogContent>
        <DialogHeader>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-warning">
            Plan review
          </p>
          <DialogTitle>Review plan change</DialogTitle>
          <DialogDescription>
            {formatPlanLabel(currentPlan)} to {formatPlanLabel(proposedPlan)}{" "}
            for{" "}
            <span className="font-medium text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {orgName}
            </span>
            . Praviar records the applied organization update in the admin audit
            log.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/50 p-3 text-sm sm:grid-cols-2">
          <PlanImpactColumn
            label="Current plan"
            plan={currentPlan}
            summary={currentPlanCopy.summary}
            guardrail={currentPlanCopy.guardrail}
          />
          <PlanImpactColumn
            label="Proposed plan"
            plan={proposedPlan}
            summary={proposedPlanCopy.summary}
            guardrail={proposedPlanCopy.guardrail}
            isProposed
          />
        </div>
        <div className="grid gap-2 rounded-lg border border-warning/25 bg-warning/10 p-3 text-sm sm:grid-cols-3">
          <PlanFact
            label="Included Report Credits"
            value={`${monthlyAllowance.toLocaleString()} / month`}
          />
          <PlanFact
            label="Report requests used"
            value={analysisCount.toLocaleString()}
          />
          <PlanFact
            label="Included remaining"
            value={freeAnalysesRemaining.toLocaleString()}
          />
        </div>
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 p-3 text-sm leading-6 text-[var(--text-secondary)]">
          This applies the tenant plan label through the admin API. Included
          Report Credit allowance and remaining values are shown for
          verification; billing entitlement changes are reconciled by the
          subscription and Report Credit ledger.
        </div>
        {error ? (
          <div
            role="alert"
            className="rounded-lg border border-error/25 bg-error/10 p-3 text-sm leading-6 text-error"
          >
            {error}
          </div>
        ) : null}
        <DialogFooter className="gap-2 sm:space-x-0">
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
            aria-label={`Apply plan change for ${orgName}`}
            className={ADMIN_BUTTON_TARGET_CLASS}
            loading={applyPending}
            onClick={handleApply}
          >
            Apply plan change
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function getPlanReviewCopy(plan: string) {
  return (
    PLAN_REVIEW_COPY[plan] ?? {
      summary: "Uses the plan recorded by the admin API.",
      guardrail:
        "Unknown plan label. Apply only after confirming commercial terms.",
    }
  );
}

function PlanImpactColumn({
  guardrail,
  isProposed = false,
  label,
  plan,
  summary,
}: {
  guardrail: string;
  isProposed?: boolean;
  label: string;
  plan: string;
  summary: string;
}) {
  return (
    <div
      className={`min-w-0 rounded-md border p-3 ${
        isProposed
          ? "border-brand-primary/25 bg-brand-primary/8"
          : "border-[var(--border-subtle)] bg-[var(--bg-surface)]/72"
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
        {formatPlanLabel(plan)}
      </p>
      <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
        {summary}
      </p>
      <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
        {guardrail}
      </p>
    </div>
  );
}

function PlanFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 break-words text-sm font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
