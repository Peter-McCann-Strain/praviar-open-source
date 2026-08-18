import { useId, useMemo, useState } from "react";
import { Download, SlidersHorizontal } from "lucide-react";
import type {
  AuditLogEntry,
  AuditLogFilters,
  AuditLogListResponse,
} from "@/hooks/use-admin-analytics";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AnalyticsPanelStatus } from "@/components/admin-analytics/status-state";
import { sanitizeDiagnosticText } from "@/lib/diagnostic-redaction";

interface AuditLogTabProps {
  auditData: AuditLogListResponse | undefined;
  auditLoading: boolean;
  auditError?: unknown;
  auditFilters: AuditLogFilters;
  auditPage: number;
  onFiltersChange: (filters: AuditLogFilters) => void;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onResetPage: () => void;
  onRetry: () => void;
}

const ANALYTICS_AUDIT_DETAIL_LABELS: Record<string, string> = {
  analysis_id: "Analysis reference",
  compound_name: "Compound reference",
  credit_pack_id: "Credit pack reference",
  export_id: "Export reference",
  org_id: "Organization reference",
  report_format: "Report format",
  user_id: "User reference",
  role: "Role update",
  plan: "Plan update",
  report_id: "Report reference",
  share_token: "Share reference",
};

const AUDIT_ACTION_OPTIONS = [
  { label: "All actions", value: "" },
  { label: "Analysis created", value: "analysis.created" },
  { label: "Analysis completed", value: "analysis.completed" },
  { label: "Report shared", value: "report.shared" },
  { label: "Report export queued", value: "report.export.queued" },
  { label: "Share revoked", value: "report.share.revoked" },
  { label: "Credit pack purchased", value: "billing.credit_pack.purchased" },
  { label: "User role updated", value: "admin.user_role.updated" },
  { label: "API key created", value: "apikey.created" },
  { label: "API key revoked", value: "apikey.revoked" },
] as const;

const SENSITIVE_DETAIL_KEY_PATTERN =
  /(api.?key|authorization|bearer|cookie|password|secret|token)/i;

function summarizeAnalyticsAuditDetails(details: Record<string, unknown>) {
  const labels = Object.keys(details)
    .map((key) => ANALYTICS_AUDIT_DETAIL_LABELS[key])
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

function safeAuditDetailValue(key: string, value: unknown): unknown {
  if (SENSITIVE_DETAIL_KEY_PATTERN.test(key)) {
    return "[redacted]";
  }

  if (typeof value === "string") {
    return sanitizeDiagnosticText(value, "");
  }

  if (Array.isArray(value)) {
    return value.map((item) => safeAuditDetailValue(key, item));
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(
        ([childKey, childValue]) => [
          childKey,
          safeAuditDetailValue(childKey, childValue),
        ],
      ),
    );
  }

  return value;
}

function getSafeAuditDetails(details: Record<string, unknown>) {
  return Object.fromEntries(
    Object.entries(details).map(([key, value]) => [
      key,
      safeAuditDetailValue(key, value),
    ]),
  );
}

function formatAuditTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown timestamp";
  return date.toISOString();
}

function csvCell(value: unknown): string {
  const text =
    typeof value === "string" ? value : JSON.stringify(value ?? "", null, 0);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function buildAuditLogCsv(entries: AuditLogEntry[], filters: AuditLogFilters) {
  const metadata = [
    ["Schema", "Praviar admin audit current page v1"],
    ["Generated At", new Date().toISOString()],
    ["Action Filter", filters.action ?? "all"],
    ["User Filter", filters.user_id ?? "all"],
    ["Start Date", filters.start_date ?? ""],
    ["End Date", filters.end_date ?? ""],
    ["Sort", filters.sort ?? "desc"],
    [],
  ];
  const header = [
    "Timestamp",
    "Action",
    "User Email",
    "User ID",
    "Organization ID",
    "Analysis ID",
    "IP Address",
    "Safe Details JSON",
  ];
  const rows = entries.map((entry) => [
    formatAuditTimestamp(entry.created_at),
    entry.action,
    entry.user_email || "system",
    entry.user_id ?? "",
    entry.org_id,
    entry.analysis_id ?? "",
    entry.ip_address || "",
    getSafeAuditDetails(entry.details),
  ]);

  return [...metadata, header, ...rows]
    .map((row) => row.map(csvCell).join(","))
    .join("\n");
}

function downloadAuditCsv(entries: AuditLogEntry[], filters: AuditLogFilters) {
  const csv = buildAuditLogCsv(entries, filters);
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `praviar-admin-audit-page-${new Date().toISOString().slice(0, 10)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function AuditLogTab({
  auditData,
  auditLoading,
  auditError,
  auditFilters,
  auditPage,
  onFiltersChange,
  onPreviousPage,
  onNextPage,
  onResetPage,
  onRetry,
}: AuditLogTabProps) {
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const actionFilterId = useId();
  const userFilterId = useId();
  const startDateFilterId = useId();
  const endDateFilterId = useId();
  const sortFilterId = useId();
  const entries = useMemo(() => auditData?.items ?? [], [auditData?.items]);
  const total = auditData?.total ?? 0;
  const selectedEntry = useMemo(
    () => entries.find((entry) => entry.id === selectedEntryId) ?? null,
    [entries, selectedEntryId],
  );

  if (auditError && !auditData) {
    return (
      <AnalyticsPanelStatus
        title="Audit telemetry unavailable"
        description="Audit events could not be loaded. Existing audit records and tenant controls are unchanged."
        onRetry={onRetry}
      />
    );
  }

  const totalPages = Math.ceil(total / (auditData?.per_page ?? 50));
  const hasPagedEmptyState = entries.length === 0 && total > 0;
  const hasActiveFilters = Boolean(
    auditFilters.action ||
    auditFilters.user_id ||
    auditFilters.start_date ||
    auditFilters.end_date ||
    auditFilters.sort === "asc",
  );

  const updateFilters = (next: AuditLogFilters) => {
    onFiltersChange(next);
    setSelectedEntryId(null);
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b border-[var(--border-subtle)]">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle aria-level={2} className="text-sm">
              Audit Log
            </CardTitle>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">
              {total} entries total. Filters apply before pagination.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 w-full gap-2 sm:w-auto"
            disabled={entries.length === 0}
            onClick={() => downloadAuditCsv(entries, auditFilters)}
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            Export current page CSV
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        <section
          aria-label="Audit log filters"
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-3"
        >
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden="true" />
            Audit filters
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_repeat(3,minmax(0,0.8fr))_auto]">
            <label
              htmlFor={actionFilterId}
              className="grid gap-1 text-xs font-medium text-[var(--text-secondary)]"
            >
              Action
              <select
                id={actionFilterId}
                aria-label="Audit action filter"
                value={auditFilters.action ?? ""}
                onChange={(event) =>
                  updateFilters({
                    ...auditFilters,
                    action: event.target.value || undefined,
                  })
                }
                className="min-h-11 rounded-md border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)]"
              >
                {AUDIT_ACTION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label
              htmlFor={userFilterId}
              className="grid gap-1 text-xs font-medium text-[var(--text-secondary)]"
            >
              User ID
              <input
                id={userFilterId}
                aria-label="Audit user filter"
                value={auditFilters.user_id ?? ""}
                onChange={(event) =>
                  updateFilters({
                    ...auditFilters,
                    user_id: event.target.value.trim() || undefined,
                  })
                }
                placeholder="usr_..."
                className="min-h-11 rounded-md border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)]"
              />
            </label>
            <label
              htmlFor={startDateFilterId}
              className="grid gap-1 text-xs font-medium text-[var(--text-secondary)]"
            >
              Start
              <input
                id={startDateFilterId}
                aria-label="Audit start date filter"
                type="date"
                value={auditFilters.start_date ?? ""}
                onChange={(event) =>
                  updateFilters({
                    ...auditFilters,
                    start_date: event.target.value || undefined,
                  })
                }
                className="min-h-11 rounded-md border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)]"
              />
            </label>
            <label
              htmlFor={endDateFilterId}
              className="grid gap-1 text-xs font-medium text-[var(--text-secondary)]"
            >
              End
              <input
                id={endDateFilterId}
                aria-label="Audit end date filter"
                type="date"
                value={auditFilters.end_date ?? ""}
                onChange={(event) =>
                  updateFilters({
                    ...auditFilters,
                    end_date: event.target.value || undefined,
                  })
                }
                className="min-h-11 rounded-md border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)]"
              />
            </label>
            <label
              htmlFor={sortFilterId}
              className="grid gap-1 text-xs font-medium text-[var(--text-secondary)]"
            >
              Sort
              <select
                id={sortFilterId}
                aria-label="Audit sort order"
                value={auditFilters.sort ?? "desc"}
                onChange={(event) =>
                  updateFilters({
                    ...auditFilters,
                    sort: event.target.value as AuditLogFilters["sort"],
                  })
                }
                className="min-h-11 rounded-md border border-[var(--border-default)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)]"
              >
                <option value="desc">Newest first</option>
                <option value="asc">Oldest first</option>
              </select>
            </label>
            <Button
              type="button"
              variant="outline"
              className="min-h-11 w-full self-end"
              disabled={!hasActiveFilters}
              onClick={() => updateFilters({})}
            >
              Clear filters
            </Button>
          </div>
        </section>

        {auditLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="skeleton-shimmer h-16 rounded-md bg-[var(--skeleton-base)] sm:h-10"
              />
            ))}
          </div>
        ) : (
          <>
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,0.34fr)]">
              <div
                aria-label="Admin analytics audit log"
                className="overflow-x-auto [scrollbar-gutter:stable] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
                role="region"
                tabIndex={0}
              >
                <table className="w-full text-sm md:min-w-[54rem]">
                  <caption className="sr-only">
                    Admin analytics audit log with timestamp, action, user, IP
                    address, safe metadata summary, and row detail controls.
                  </caption>
                  <thead className="hidden md:table-header-group">
                    <tr className="border-b border-[var(--border-default)]">
                      <th
                        scope="col"
                        className="py-2 pr-4 text-left text-xs font-medium text-[var(--text-tertiary)]"
                      >
                        Timestamp
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-2 text-left text-xs font-medium text-[var(--text-tertiary)]"
                      >
                        Action
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-2 text-left text-xs font-medium text-[var(--text-tertiary)]"
                      >
                        User
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-2 text-left text-xs font-medium text-[var(--text-tertiary)]"
                      >
                        IP
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-2 text-left text-xs font-medium text-[var(--text-tertiary)]"
                      >
                        Details
                      </th>
                      <th
                        scope="col"
                        className="py-2 pl-4 text-left text-xs font-medium text-[var(--text-tertiary)]"
                      >
                        Inspect
                      </th>
                    </tr>
                  </thead>
                  <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group md:divide-y-0">
                    {entries.map((log) => (
                      <tr
                        key={log.id}
                        className="block py-4 transition-colors hover:bg-[var(--surface-hover)] md:table-row md:border-b md:border-[var(--border-subtle)] md:py-0"
                      >
                        <td className="flex items-start justify-between gap-4 py-2 text-xs tabular-nums text-[var(--text-secondary)] md:table-cell md:whitespace-nowrap md:py-2 md:pr-4">
                          <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                            Timestamp
                          </span>
                          <span className="text-right md:text-left">
                            {formatAuditTimestamp(log.created_at)}
                          </span>
                        </td>
                        <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-4">
                          <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                            Action
                          </span>
                          <Badge variant="secondary">{log.action}</Badge>
                        </td>
                        <td className="flex items-start justify-between gap-4 py-2 text-xs text-[var(--text-secondary)] md:table-cell md:px-4">
                          <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                            User
                          </span>
                          <span className="min-w-0 break-all text-right md:text-left">
                            {log.user_email || "system"}
                          </span>
                        </td>
                        <td className="flex items-center justify-between gap-4 py-2 font-mono text-xs text-[var(--text-tertiary)] md:table-cell md:px-4">
                          <span className="type-label-sm font-sans text-[var(--text-tertiary)] md:hidden">
                            IP
                          </span>
                          <span>{log.ip_address || "--"}</span>
                        </td>
                        <td className="flex items-start justify-between gap-4 py-2 text-xs text-[var(--text-tertiary)] md:table-cell md:max-w-[200px] md:truncate md:px-4">
                          <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                            Details
                          </span>
                          <span className="min-w-0 break-all text-right md:block md:truncate md:text-left">
                            {summarizeAnalyticsAuditDetails(log.details)}
                          </span>
                        </td>
                        <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:py-2 md:pl-4">
                          <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                            Inspect
                          </span>
                          <Button
                            type="button"
                            variant="outline"
                            className="min-h-10 w-full text-xs md:w-auto"
                            aria-pressed={selectedEntryId === log.id}
                            onClick={() =>
                              setSelectedEntryId((current) =>
                                current === log.id ? null : log.id,
                              )
                            }
                          >
                            {selectedEntryId === log.id
                              ? "Hide details"
                              : "Inspect details"}
                          </Button>
                        </td>
                      </tr>
                    ))}
                    {hasPagedEmptyState ? (
                      <tr className="block md:table-row">
                        <td colSpan={6} className="block py-8 md:table-cell">
                          <div className="mx-auto flex max-w-xl flex-col items-center gap-3 text-center">
                            <p className="text-sm font-medium text-[var(--text-primary)]">
                              No audit events on this page
                            </p>
                            <p className="text-sm leading-6 text-[var(--text-secondary)]">
                              Audit events still exist for this view, but this
                              page no longer has rows. Return to the first page
                              to reload the active event list.
                            </p>
                            <Button
                              type="button"
                              variant="outline"
                              className="min-h-11 w-full sm:w-auto"
                              onClick={onResetPage}
                            >
                              Return to first page
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ) : entries.length === 0 ? (
                      <tr className="block md:table-row">
                        <td
                          colSpan={6}
                          className="block py-8 text-center text-[var(--text-tertiary)] md:table-cell"
                        >
                          No audit log entries for the selected filters.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>

              <AuditDetailPanel entry={selectedEntry} />
            </div>

            {total > (auditData?.per_page ?? 50) && (
              <div className="mt-4 flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-[var(--text-tertiary)]">
                  Page {auditPage} of {totalPages}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    disabled={auditPage <= 1}
                    onClick={onPreviousPage}
                    className="min-h-11 flex-1 sm:flex-none"
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    disabled={!auditData?.has_next}
                    onClick={onNextPage}
                    className="min-h-11 flex-1 sm:flex-none"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function AuditDetailPanel({ entry }: { entry: AuditLogEntry | null }) {
  const safeDetails = entry ? getSafeAuditDetails(entry.details) : null;
  const safeDetailsJson = safeDetails
    ? JSON.stringify(safeDetails, null, 2)
    : null;

  return (
    <aside
      aria-label="Audit event detail"
      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-4"
    >
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        Event detail
      </p>
      {entry ? (
        <div className="mt-3 space-y-3 text-sm">
          <div className="grid gap-2">
            <AuditDetailField label="Action" value={entry.action} />
            <AuditDetailField
              label="Timestamp"
              value={formatAuditTimestamp(entry.created_at)}
            />
            <AuditDetailField
              label="Actor"
              value={entry.user_email || entry.user_id || "system"}
            />
            <AuditDetailField
              label="Source IP"
              value={entry.ip_address || "Not recorded"}
            />
          </div>
          <div>
            <p className="text-xs font-medium text-[var(--text-secondary)]">
              Safe raw metadata
            </p>
            <pre className="mt-1 max-h-72 overflow-auto rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3 text-xs leading-5 text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {safeDetailsJson}
            </pre>
          </div>
        </div>
      ) : (
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
          Select an event to inspect redacted metadata without leaving the audit
          table.
        </p>
      )}
    </aside>
  );
}

function AuditDetailField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-2">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 break-words text-xs text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
