"use client";

import { useState } from "react";
import {
  AlertTriangle,
  BellDot,
  Clock,
  Eye,
  EyeOff,
  FileSearch,
  Play,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/shared/empty-state";
import type { MonitorResponse } from "@/hooks/use-monitors";
import {
  formatMonitorDateTime,
  formatRunMode,
  formatScheduleLabel,
  getMonitorPosture,
  relativeTime,
} from "@/components/monitors/helpers";
import { cn } from "@/lib/utils";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";

interface MonitorsTableRunOptions {
  forceFullRefresh?: boolean;
}

interface MonitorsTableProps {
  monitors: MonitorResponse[];
  selectedMonitorId?: string | null;
  pendingMonitorId?: string | null;
  actionsDisabled?: boolean;
  isLoading?: boolean;
  isUpdating?: boolean;
  isOutOfRangeEmptyPage?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  onToggleActive: (monitor: MonitorResponse) => void;
  onViewAlerts: (monitor: MonitorResponse) => void;
  onAlertButtonFocus?: (element: HTMLButtonElement) => void;
  onRun?: (monitor: MonitorResponse, options?: MonitorsTableRunOptions) => void;
  onDelete: (monitorId: string) => void;
}

export function MonitorsTable({
  monitors,
  selectedMonitorId = null,
  pendingMonitorId = null,
  actionsDisabled = false,
  isLoading = false,
  isUpdating = false,
  isOutOfRangeEmptyPage = false,
  emptyTitle = "No monitors yet",
  emptyDescription = "Create a monitor to track patent landscape changes. New watches start with a first-run pending state, and no clearance should be inferred until the first run completes.",
  onToggleActive,
  onViewAlerts,
  onAlertButtonFocus,
  onRun,
  onDelete,
}: MonitorsTableProps) {
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const hasPendingMonitorAction = Boolean(pendingMonitorId);
  const controlsLocked =
    actionsDisabled || hasPendingMonitorAction || isUpdating;
  const confirmDeleteMonitor =
    monitors.find((monitor) => monitor.id === confirmDelete) ?? null;

  if (monitors.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={isOutOfRangeEmptyPage ? RefreshCw : Clock}
            title={emptyTitle}
            description={emptyDescription}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card className="overflow-hidden">
        <div className="flex flex-col gap-2 border-b border-[var(--border-subtle)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              Monitoring watches
            </h2>
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              Compound watch posture, strategy cadence, jurisdiction scope, and
              latest patent-count movement.
            </p>
          </div>
          {hasPendingMonitorAction || isUpdating ? (
            <span
              className="w-fit rounded-md border border-brand-primary/20 bg-brand-primary/10 px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-brand-primary"
              role="status"
              aria-live="polite"
            >
              {hasPendingMonitorAction
                ? "Applying watch update"
                : "Updating watches"}
            </span>
          ) : null}
        </div>
        <CardContent
          aria-label="Monitoring watches horizontal scroll area"
          className="overflow-hidden p-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] md:overflow-x-auto md:p-0"
          role="region"
          tabIndex={0}
        >
          <table
            className="w-full min-w-0 text-sm md:min-w-[980px]"
            aria-busy={isLoading || isUpdating ? "true" : undefined}
          >
            <caption className="sr-only">
              Patent monitoring watches with posture, schedule, jurisdiction
              scope, last run health, patent counts, and row actions.
            </caption>
            <thead className="sr-only md:not-sr-only md:sticky md:top-0 md:z-10 md:table-header-group">
              <tr className="praviar-glass-strip border-b border-[var(--border-default)]">
                <th
                  scope="col"
                  className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
                >
                  Monitor
                </th>
                <th
                  scope="col"
                  className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
                >
                  Posture
                </th>
                <th
                  scope="col"
                  className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
                >
                  Strategy
                </th>
                <th
                  scope="col"
                  className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
                >
                  Last run
                </th>
                <th
                  scope="col"
                  className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
                >
                  Tracked patents
                </th>
                <th
                  scope="col"
                  className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]"
                >
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="block space-y-3 md:table-row-group md:divide-y md:divide-[var(--border-subtle)] md:space-y-0">
              {monitors.map((monitor) => {
                const name = monitor.compound_name || "Unnamed monitor";
                const posture = getMonitorPosture(monitor);
                const isSelected = selectedMonitorId === monitor.id;
                const rowControlsLocked = controlsLocked;
                const jurisdictions =
                  monitor.target_jurisdictions.filter(Boolean);
                const visibleJurisdictions = jurisdictions.slice(0, 3);
                const extraJurisdictions = Math.max(
                  0,
                  jurisdictions.length - visibleJurisdictions.length,
                );
                return (
                  <tr
                    key={monitor.id}
                    className={cn(
                      "block rounded-lg border border-l-[3px] p-3 shadow-[var(--shadow-xs)] transition-colors md:table-row md:border-x-0 md:border-b-0 md:border-r-0 md:p-0 md:shadow-none",
                      isSelected
                        ? "border-l-brand-primary bg-brand-primary/5 md:bg-brand-primary/5"
                        : "border-l-brand-primary/30 bg-[var(--surface-muted)]/60 hover:bg-[var(--surface-subtle)] md:bg-transparent",
                    )}
                  >
                    <td className="block pb-3 md:table-cell md:px-4 md:py-3">
                      <div className="min-w-0">
                        <p
                          className="max-w-full break-words text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]"
                          title={name}
                        >
                          {name}
                        </p>
                        <p
                          className="mt-1 max-w-full break-all font-mono text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere] md:max-w-[220px] md:overflow-hidden md:text-ellipsis md:whitespace-nowrap"
                          title={
                            monitor.compound_smiles || "SMILES not indexed"
                          }
                        >
                          {monitor.compound_smiles || "SMILES not indexed"}
                        </p>
                        {monitor.last_run_summary ? (
                          <p className="mt-2 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
                            {monitor.last_run_summary}
                          </p>
                        ) : null}
                      </div>
                    </td>
                    <td className="grid grid-cols-[7rem_1fr] items-start gap-3 py-2 md:table-cell md:px-4 md:py-3">
                      <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden">
                        Posture
                      </span>
                      <span className="block">
                        <StatusPill label={posture.label} tone={posture.tone} />
                        <span className="mt-1 block text-xs leading-5 text-[var(--text-tertiary)]">
                          {posture.detail}
                        </span>
                      </span>
                    </td>
                    <td className="grid grid-cols-[7rem_1fr] items-start gap-3 py-2 md:table-cell md:px-4 md:py-3">
                      <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden">
                        Strategy
                      </span>
                      <span className="block min-w-0">
                        <span className="inline-flex items-center gap-1 text-sm font-medium text-[var(--text-secondary)]">
                          <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                          {formatScheduleLabel(monitor.schedule)}
                        </span>
                        <span className="mt-1 block text-xs text-[var(--text-tertiary)]">
                          {formatRunMode(monitor.last_run_mode)}
                        </span>
                        <span className="mt-2 flex flex-wrap gap-1.5">
                          {visibleJurisdictions.length > 0 ? (
                            visibleJurisdictions.map((jurisdiction) => (
                              <span
                                key={jurisdiction}
                                className="max-w-full break-all rounded-md border border-brand-primary/20 bg-brand-primary/10 px-2 py-0.5 font-mono text-xs font-semibold text-[var(--brand-primary-dim)] [overflow-wrap:anywhere]"
                                title={jurisdiction}
                              >
                                {jurisdiction}
                              </span>
                            ))
                          ) : (
                            <span className="text-xs text-[var(--text-tertiary)]">
                              Jurisdiction scope not indexed
                            </span>
                          )}
                          {extraJurisdictions > 0 ? (
                            <span className="rounded-md border border-brand-primary/20 bg-brand-primary/10 px-2 py-0.5 text-xs font-semibold text-[var(--brand-primary-dim)]">
                              +{extraJurisdictions}
                            </span>
                          ) : null}
                        </span>
                      </span>
                    </td>
                    <td className="grid grid-cols-[7rem_1fr] items-start gap-3 py-2 md:table-cell md:px-4 md:py-3">
                      <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden">
                        Last run
                      </span>
                      <span>
                        <span className="block text-sm font-medium tabular-nums text-[var(--text-secondary)]">
                          {monitor.last_run_at
                            ? formatRelativeTime(monitor.last_run_at)
                            : "Never"}
                        </span>
                        <span className="mt-1 block text-xs leading-5 text-[var(--text-tertiary)]">
                          {formatMonitorDateTime(monitor.last_run_at)}
                        </span>
                      </span>
                    </td>
                    <td className="grid grid-cols-[7rem_1fr] items-center gap-3 py-2 text-sm tabular-nums text-[var(--text-primary)] md:table-cell md:px-4 md:py-3 md:text-right">
                      <span className="text-xs font-medium uppercase text-[var(--text-tertiary)] md:hidden">
                        Tracked patents
                      </span>
                      <span>{monitor.last_patent_count.toLocaleString()}</span>
                    </td>
                    <td className="block pt-3 md:table-cell md:px-4 md:py-3 md:text-right">
                      <div className="flex flex-wrap items-center justify-end gap-1.5">
                        <Button
                          variant={isSelected ? "secondary" : "ghost"}
                          size="sm"
                          className="min-h-11 gap-1.5"
                          aria-expanded={isSelected}
                          aria-label={`View alerts for ${name}`}
                          onFocus={(event) =>
                            onAlertButtonFocus?.(event.currentTarget)
                          }
                          onClick={(event) => {
                            onAlertButtonFocus?.(event.currentTarget);
                            onViewAlerts(monitor);
                          }}
                        >
                          <BellDot className="h-3.5 w-3.5" aria-hidden="true" />
                          Alerts
                        </Button>
                        {onRun ? (
                          <>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-11 w-11"
                              disabled={rowControlsLocked}
                              onClick={() => onRun(monitor)}
                              title={`Run low-cost diff monitor for ${name}`}
                              aria-label={`Run low-cost diff monitor for ${name}`}
                            >
                              <Play className="h-4 w-4" aria-hidden="true" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-11 w-11"
                              disabled={rowControlsLocked}
                              onClick={() =>
                                onRun(monitor, { forceFullRefresh: true })
                              }
                              title={`Force bounded full refresh for ${name}`}
                              aria-label={`Force bounded full refresh for ${name}`}
                            >
                              <RefreshCw
                                className="h-4 w-4"
                                aria-hidden="true"
                              />
                            </Button>
                          </>
                        ) : null}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-11 w-11"
                          disabled={rowControlsLocked}
                          onClick={() => onToggleActive(monitor)}
                          title={
                            monitor.is_active
                              ? `Pause monitor for ${name}`
                              : `Activate monitor for ${name}`
                          }
                          aria-label={
                            monitor.is_active
                              ? `Pause monitor for ${name}`
                              : `Activate monitor for ${name}`
                          }
                        >
                          {monitor.is_active ? (
                            <EyeOff className="h-4 w-4" aria-hidden="true" />
                          ) : (
                            <Eye className="h-4 w-4" aria-hidden="true" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-11 w-11"
                          disabled={rowControlsLocked}
                          onClick={() => setConfirmDelete(monitor.id)}
                          title={`Delete monitor for ${name}`}
                          aria-label={`Delete monitor for ${name}`}
                        >
                          <Trash2
                            className="h-4 w-4 text-error"
                            aria-hidden="true"
                          />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Dialog
        open={confirmDeleteMonitor !== null}
        onOpenChange={(open) => {
          if (!open && !controlsLocked) setConfirmDelete(null);
        }}
      >
        <DialogContent className="max-w-lg gap-3 p-4 sm:gap-4 sm:p-6">
          <DialogHeader className="space-y-3 text-left">
            <div className="flex items-start gap-2 pr-8">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-error/20 bg-error/10 text-error sm:h-10 sm:w-10">
                <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              </span>
              <DialogTitle className="min-w-0 text-base leading-6 sm:text-lg">
                Delete monitor and stop scheduled checks?
              </DialogTitle>
            </div>
            <DialogDescription className="break-words leading-6 [overflow-wrap:anywhere]">
              {confirmDeleteMonitor?.compound_name || "This monitor"} will stop
              future monitoring runs. Existing reports remain unchanged;
              retained audit records stay available according to workspace
              policy.
            </DialogDescription>
          </DialogHeader>

          {confirmDeleteMonitor ? (
            <div className="space-y-3">
              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/60 p-3 sm:p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                  Monitor under review
                </p>
                <p className="mt-2 break-words text-base font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {confirmDeleteMonitor.compound_name || "Unnamed monitor"}
                </p>
                <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  {formatScheduleLabel(confirmDeleteMonitor.schedule)} ·{" "}
                  {confirmDeleteMonitor.last_patent_count.toLocaleString()}{" "}
                  tracked patents
                </p>
              </div>
              <div
                role="note"
                className="rounded-lg border border-warning/20 bg-warning/10 px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]"
              >
                Delete obsolete or duplicate watches only. Pause this watch if
                monitoring may resume.
              </div>
            </div>
          ) : null}

          <div className="grid grid-cols-2 gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="min-h-11"
              disabled={controlsLocked}
              aria-label={`Cancel delete monitor for ${
                confirmDeleteMonitor?.compound_name || "monitor"
              }`}
              onClick={() => setConfirmDelete(null)}
            >
              Keep monitor
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              className="min-h-11"
              disabled={controlsLocked || !confirmDeleteMonitor}
              aria-label={`Confirm delete monitor for ${
                confirmDeleteMonitor?.compound_name || "monitor"
              }`}
              onClick={() => {
                if (!confirmDeleteMonitor) return;
                onDelete(confirmDeleteMonitor.id);
                setConfirmDelete(null);
              }}
            >
              Delete monitor
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function StatusPill({
  label,
  tone,
}: {
  label: string;
  tone: ReturnType<typeof getMonitorPosture>["tone"];
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold",
        tone === "healthy" && "border-success/25 bg-success/10 text-success",
        tone === "warning" && "border-warning/25 bg-warning/10 text-warning",
        tone === "error" && "border-error/25 bg-error/10 text-error",
        tone === "running" && "border-info/25 bg-info/10 text-info",
        tone === "paused" &&
          "border-[var(--border-default)] bg-[var(--surface-active)] text-[var(--text-tertiary)]",
      )}
    >
      <FileSearch className="h-3.5 w-3.5" aria-hidden="true" />
      {label}
    </span>
  );
}
