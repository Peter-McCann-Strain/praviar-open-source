"use client";

import { useId, useState } from "react";
import { ScrollText } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  ADMIN_BUTTON_TARGET_CLASS,
  ADMIN_FIELD_CLASS,
  AdminPagedEmptyState,
  AdminRefreshWarning,
  AdminStatusState,
} from "@/components/admin-dashboard/helpers";
import { useAdminAuditLogs } from "@/hooks/use-admin";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import { isAuthBoundaryError } from "@/lib/api-client";
import type { AuditLogEntry } from "@/hooks/use-admin";

function reportAuditLogAccessRestriction() {
  console.error("[AuditLogsTab] Audit log access restricted");
}

function reportAuditLogLoadFailure() {
  console.error("[AuditLogsTab] Failed to load audit log");
}

const AUDIT_DETAIL_LABELS: Record<string, string> = {
  analysis_id: "Analysis reference",
  compound: "Compound reference",
  key_id: "API key reference",
  key_prefix: "API key prefix",
  max_analyses_per_month: "Monthly analysis limit",
  name: "API key name",
  new_role: "New role",
  organization_id: "Organization reference",
  org_id: "Organization reference",
  plan: "Plan update",
  free_analyses_remaining: "Free analysis balance",
  target_user_id: "Target user reference",
  user_id: "User reference",
  api_key_id: "API key reference",
};

function summarizeAuditDetails(details: AuditLogEntry["details"]): string {
  const labels = Object.keys(details)
    .map((key) => AUDIT_DETAIL_LABELS[key])
    .filter((label): label is string => Boolean(label));

  if (Object.keys(details).length === 0) {
    return "--";
  }

  if (labels.length === 0) {
    return "Additional metadata recorded";
  }

  const visibleLabels = labels.slice(0, 2);
  const suffix =
    labels.length > visibleLabels.length
      ? ` +${labels.length - visibleLabels.length}`
      : "";

  return `${visibleLabels.join(", ")} recorded${suffix}`;
}

function formatAuditTimestamp(date: string): string {
  const timestamp = new Date(date);
  if (Number.isNaN(timestamp.getTime())) {
    return "Unknown timestamp";
  }
  return `${timestamp.toISOString().replace("T", " ").replace(".000Z", "Z")} UTC`;
}

export function AuditLogsTab() {
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState<string | undefined>(
    undefined,
  );
  const actionFilterId = useId();
  const { data, isLoading, error, refetch } = useAdminAuditLogs(
    page,
    actionFilter,
  );
  const accessRestricted = isAuthBoundaryError(error);
  const initialLoading = isLoading && !data;
  const auditLogLoadFailed = Boolean(
    !initialLoading && error && !data && !accessRestricted,
  );

  useErrorDiagnostic(
    !initialLoading && accessRestricted,
    error,
    reportAuditLogAccessRestriction,
  );
  useErrorDiagnostic(auditLogLoadFailed, error, reportAuditLogLoadFailure);

  if (initialLoading) {
    return <AdminStatusState surface="audit-logs" variant="loading" />;
  }

  if (accessRestricted) {
    return (
      <AdminStatusState
        surface="audit-logs"
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
        surface="audit-logs"
        variant="temporary"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (!data) {
    return <AdminStatusState surface="audit-logs" variant="auth" />;
  }

  const totalPages = Math.ceil((data?.total ?? 0) / 20);

  return (
    <div className="space-y-4">
      {error ? <AdminRefreshWarning label="Audit log" /> : null}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
        <label
          htmlFor={actionFilterId}
          className="type-label-sm text-[var(--text-secondary)]"
        >
          Filter by action:
        </label>
        <select
          id={actionFilterId}
          value={actionFilter ?? ""}
          onChange={(e) => {
            setActionFilter(e.target.value || undefined);
            setPage(1);
          }}
          className={`${ADMIN_FIELD_CLASS} text-[var(--text-secondary)]`}
        >
          <option value="">All actions</option>
          <option value="analysis.created">Analysis created</option>
          <option value="analysis.completed">Analysis completed</option>
          <option value="user.login">User login</option>
          <option value="admin.user_role.updated">Admin role updated</option>
          <option value="apikey.created">API key created</option>
          <option value="apikey.revoked">API key revoked</option>
          <option value="report.export.queued">Report export queued</option>
          <option value="admin.organization.updated">
            Organization updated
          </option>
        </select>
      </div>

      {data.items.length === 0 ? (
        data.total > 0 ? (
          <AdminPagedEmptyState
            title="No audit events on this page"
            description="The audit trail still has matching records, but this page no longer has rows. Return to the first page to reload the active event list."
            actionLabel="Return to first page"
            onAction={() => setPage(1)}
          />
        ) : (
          <Card>
            <CardContent className="p-0">
              <EmptyState
                icon={ScrollText}
                title={
                  actionFilter
                    ? "No matching audit events"
                    : "No audit events yet"
                }
                description={
                  actionFilter
                    ? "No audit events match this action filter. Clear the filter to inspect all recorded activity."
                    : "Governed platform activity will appear here as users interact with the product."
                }
                surface="embedded"
              />
            </CardContent>
          </Card>
        )
      ) : (
        <Card>
          <CardContent className="p-0">
            <div
              aria-label="Admin audit event table"
              className="overflow-x-auto [scrollbar-gutter:stable] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
              role="region"
              tabIndex={0}
            >
              <table className="w-full text-sm md:min-w-[920px]">
                <caption className="sr-only">
                  Admin audit event table with UTC timestamps, action, actor,
                  source IP, and redacted detail summaries.
                </caption>
                <thead className="hidden md:table-header-group">
                  <tr className="border-b border-[var(--border-subtle)]">
                    <th
                      scope="col"
                      className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                    >
                      Timestamp
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                    >
                      Action
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                    >
                      User
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                    >
                      IP Address
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]"
                    >
                      Details
                    </th>
                  </tr>
                </thead>
                <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
                  {data.items.map((entry: AuditLogEntry) => (
                    <tr
                      key={entry.id}
                      className="block p-4 transition-colors hover:bg-[var(--surface-subtle)] md:table-row md:p-0"
                    >
                      <td className="flex items-start justify-between gap-4 py-2 text-xs tabular-nums text-[var(--text-tertiary)] md:table-cell md:whitespace-nowrap md:px-6 md:py-3">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Timestamp
                        </span>
                        <span className="text-right md:text-left">
                          {formatAuditTimestamp(entry.created_at)}
                        </span>
                      </td>
                      <td className="flex items-start justify-between gap-4 py-2 md:table-cell md:px-6 md:py-3">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Action
                        </span>
                        <span
                          className="inline-flex max-w-full min-w-0 items-center rounded-full bg-[var(--surface-active)] px-2.5 py-0.5 text-xs font-medium text-[var(--text-secondary)] [overflow-wrap:anywhere] md:max-w-[18rem] md:truncate"
                          title={entry.action}
                        >
                          {entry.action}
                        </span>
                      </td>
                      <td className="flex items-start justify-between gap-4 py-2 text-sm text-[var(--text-primary)] md:table-cell md:px-6 md:py-3">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          User
                        </span>
                        <span className="min-w-0 break-all text-right md:text-left">
                          {entry.user_email}
                        </span>
                      </td>
                      <td className="flex items-center justify-between gap-4 py-2 text-xs tabular-nums text-[var(--text-tertiary)] md:table-cell md:px-6 md:py-3">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          IP Address
                        </span>
                        <span>{entry.ip_address}</span>
                      </td>
                      <td className="flex items-start justify-between gap-4 py-2 text-xs text-[var(--text-tertiary)] md:table-cell md:max-w-[200px] md:truncate md:px-6 md:py-3">
                        <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                          Details
                        </span>
                        <span className="min-w-0 break-all text-right md:block md:truncate md:text-left">
                          {summarizeAuditDetails(entry.details)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {totalPages > 1 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-[var(--text-tertiary)]">
            Page {page} of {totalPages} ({data?.total ?? 0} total)
          </p>
          <div className="grid grid-cols-2 gap-2 sm:flex">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              className={ADMIN_BUTTON_TARGET_CLASS}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
              className={ADMIN_BUTTON_TARGET_CLASS}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
