"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { AlertsPanel } from "@/components/monitors/alerts-panel";
import { CreateMonitorForm } from "@/components/monitors/create-monitor-form";
import { MonitorsPageHeader } from "@/components/monitors/page-header";
import { MonitorSummaryCards } from "@/components/monitors/summary-cards";
import { MonitorsTable } from "@/components/monitors/monitors-table";
import { MutationRecoveryNotice } from "@/components/shared/mutation-recovery-notice";
import { WorkspaceStatusState } from "@/components/shared/workspace-status-state";
import { Button } from "@/components/ui/button";
import {
  useDeleteMonitor,
  useMonitors,
  useUpdateMonitor,
  type MonitorResponse,
  type UpdateMonitorInput,
} from "@/hooks/use-monitors";
import { useAuthToken } from "@/hooks/use-auth-token";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import { useMutationRecovery } from "@/hooks/use-mutation-recovery";
import { DEMO_MODE_ENABLED } from "@/lib/constants";
import { isAuthBoundaryError } from "@/lib/api-client";

function reportMonitorWorkspaceLoadFailure() {
  console.error("[MonitorsPage] Failed to load monitor workspace");
}

export default function MonitorsPage() {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const perPage = 20;
  const [page, setPage] = useState(1);
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "paused">(
    "all",
  );
  const [showCreate, setShowCreate] = useState(false);
  const [selectedMonitorId, setSelectedMonitorId] = useState<string | null>(
    null,
  );
  const [pendingMonitorId, setPendingMonitorId] = useState<string | null>(null);
  const createButtonRef = useRef<HTMLButtonElement>(null);
  const lastAlertButtonRef = useRef<HTMLButtonElement | null>(null);
  const { data, isLoading, isFetching, isPlaceholderData, error, refetch } =
    useMonitors(
      page,
      activeFilter === "all" ? undefined : activeFilter === "active",
      perPage,
    );
  const updateMonitor = useUpdateMonitor();
  const deleteMonitor = useDeleteMonitor();
  const updateRecovery = useMutationRecovery<UpdateMonitorInput>();
  const deleteRecovery = useMutationRecovery<string>();

  const requestedIsActive =
    activeFilter === "all" ? undefined : activeFilter === "active";
  const isAuthMissing = !DEMO_MODE_ENABLED && !token;
  const accessRestricted = isAuthBoundaryError(error);
  const isFilterRefreshing = Boolean(
    isPlaceholderData && data && data.is_active !== requestedIsActive,
  );
  const visibleMonitors = useMemo(
    () => (data && !isFilterRefreshing ? data.items : []),
    [data, isFilterRefreshing],
  );
  const responsePerPage = data?.per_page ?? perPage;
  const totalPages = Math.max(
    1,
    Math.ceil((data?.total ?? 0) / responsePerPage),
  );
  const responsePage = data?.page ?? page;
  const displayPage = Math.min(Math.max(1, responsePage), totalPages);
  const isWorkspaceUpdating = Boolean(
    (isFetching && data) || isFilterRefreshing,
  );
  const hasMutationRecovery = Boolean(
    updateRecovery.recovery || deleteRecovery.recovery,
  );
  const isMonitorActionPending = Boolean(pendingMonitorId);
  const monitorMutationsLocked =
    isMonitorActionPending || isWorkspaceUpdating || hasMutationRecovery;
  const isTableLoading = isLoading && !data;
  const isOutOfRangeEmptyPage = Boolean(
    data &&
    !isFilterRefreshing &&
    data.total > 0 &&
    visibleMonitors.length === 0,
  );
  const emptyTableCopy = getMonitorEmptyCopy(
    activeFilter,
    isFilterRefreshing,
    isOutOfRangeEmptyPage,
  );
  const selectedMonitor = useMemo(
    () =>
      visibleMonitors.find((monitor) => monitor.id === selectedMonitorId) ??
      null,
    [visibleMonitors, selectedMonitorId],
  );
  const initialWorkspaceLoading = isTableLoading && page === 1;
  const workspaceLoadFailed = Boolean(
    !isAuthMissing &&
    !accessRestricted &&
    !initialWorkspaceLoading &&
    error &&
    !data,
  );

  useErrorDiagnostic(
    workspaceLoadFailed,
    error,
    reportMonitorWorkspaceLoadFailure,
  );

  function closeCreateForm() {
    setShowCreate(false);
    window.setTimeout(() => createButtonRef.current?.focus(), 0);
  }

  function closeAlertsPanel() {
    setSelectedMonitorId(null);
    window.setTimeout(() => lastAlertButtonRef.current?.focus(), 0);
  }

  function applyMonitorUpdate(variables: UpdateMonitorInput) {
    if (pendingMonitorId) return;
    updateRecovery.clearRecovery();
    deleteRecovery.clearRecovery();
    const attempt = updateRecovery.beginAttempt();
    setPendingMonitorId(variables.monitorId);
    updateMonitor.mutate(variables, {
      onSuccess: () => updateRecovery.clearRecoveryForAttempt(attempt),
      onError: (mutationError) => {
        updateRecovery.captureFailure(mutationError, variables, attempt);
      },
      onSettled: () => setPendingMonitorId(null),
    });
  }

  function applyMonitorDelete(monitorId: string) {
    if (pendingMonitorId) return;
    updateRecovery.clearRecovery();
    deleteRecovery.clearRecovery();
    const attempt = deleteRecovery.beginAttempt();
    setPendingMonitorId(monitorId);
    if (selectedMonitorId === monitorId) {
      setSelectedMonitorId(null);
    }
    deleteMonitor.mutate(monitorId, {
      onSuccess: () => deleteRecovery.clearRecoveryForAttempt(attempt),
      onError: (mutationError) => {
        deleteRecovery.captureFailure(mutationError, monitorId, attempt);
      },
      onSettled: () => setPendingMonitorId(null),
    });
  }

  async function refreshMonitorsAfterDelete() {
    const attempt = deleteRecovery.beginAttempt();
    try {
      const result = await refetch();
      if (!result?.error && deleteRecovery.isAttemptCurrent(attempt)) {
        deleteRecovery.clearRecoveryForAttempt(attempt);
      }
    } catch {
      // Keep the recovery notice visible until authoritative state reloads.
    }
  }

  useEffect(() => {
    if (!data) return undefined;
    if (page <= totalPages) return undefined;
    const clampTimer = window.setTimeout(() => {
      setPage(totalPages);
    }, 0);
    return () => window.clearTimeout(clampTimer);
  }, [data, page, totalPages]);

  useEffect(() => {
    if (!data) return undefined;
    if (!selectedMonitorId || selectedMonitor) return undefined;
    const closeTimer = window.setTimeout(() => {
      setSelectedMonitorId(null);
    }, 0);
    return () => window.clearTimeout(closeTimer);
  }, [data, selectedMonitor, selectedMonitorId]);

  if (isAuthMissing) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
        <MonitorsPageHeader
          onCreateClick={() => setShowCreate((value) => !value)}
          createButtonRef={createButtonRef}
          actionsDisabled
        />
        <WorkspaceStatusState surface="monitors" variant="auth" />
      </div>
    );
  }

  if (accessRestricted) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
        <MonitorsPageHeader
          onCreateClick={() => setShowCreate((value) => !value)}
          createButtonRef={createButtonRef}
          actionsDisabled
        />
        <WorkspaceStatusState
          surface="monitors"
          variant="restricted"
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (initialWorkspaceLoading) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
        <MonitorsPageHeader
          onCreateClick={() => setShowCreate((value) => !value)}
          createButtonRef={createButtonRef}
          actionsDisabled
        />
        <WorkspaceStatusState surface="monitors" variant="loading" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
        <MonitorsPageHeader
          onCreateClick={() => setShowCreate((value) => !value)}
          createButtonRef={createButtonRef}
          actionsDisabled
        />
        <WorkspaceStatusState
          surface="monitors"
          variant="temporary"
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-6xl space-y-5 animate-fade-up">
        <MonitorsPageHeader
          onCreateClick={() => setShowCreate((value) => !value)}
          createButtonRef={createButtonRef}
          actionsDisabled
        />
        <WorkspaceStatusState surface="monitors" variant="auth" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
      <MonitorsPageHeader
        onCreateClick={() => setShowCreate((value) => !value)}
        createButtonRef={createButtonRef}
        actionsDisabled={monitorMutationsLocked}
      />

      {visibleMonitors.length > 0 ? (
        <MonitorSummaryCards monitors={visibleMonitors} />
      ) : null}

      <MonitorWorkspaceControls
        activeFilter={activeFilter}
        total={data.total}
        visibleCount={visibleMonitors.length}
        isUpdating={isWorkspaceUpdating}
        isFilterRefreshing={isFilterRefreshing}
        isActionPending={isMonitorActionPending || hasMutationRecovery}
        actionsDisabled={monitorMutationsLocked}
        onFilterChange={(nextFilter) => {
          if (monitorMutationsLocked) return;
          setActiveFilter(nextFilter);
          setPage(1);
          setSelectedMonitorId(null);
        }}
      />

      {showCreate ? <CreateMonitorForm onClose={closeCreateForm} /> : null}

      {updateRecovery.recovery ? (
        <MutationRecoveryNotice
          actionLabel={
            updateRecovery.recovery.variables.data.is_active === false
              ? "Reapply pause"
              : "Reapply resume"
          }
          actionPending={updateMonitor.isPending}
          dataTestId="monitor-update-recovery"
          description={
            updateRecovery.recovery.mode === "outcome-unknown"
              ? "Praviar could not confirm the saved watch posture. Reapply the exact requested state before making another monitor change."
              : "The watch posture was not saved. Retry the exact requested state or dismiss this notice before making another monitor change."
          }
          dismissLabel="Keep current posture"
          mode={updateRecovery.recovery.mode}
          onAction={() =>
            applyMonitorUpdate(updateRecovery.recovery!.variables)
          }
          onDismiss={
            updateRecovery.recovery.mode === "failed"
              ? updateRecovery.clearRecovery
              : undefined
          }
          title={
            updateRecovery.recovery.mode === "outcome-unknown"
              ? "Monitor update outcome unconfirmed"
              : "Monitor update did not complete"
          }
        />
      ) : null}

      {deleteRecovery.recovery ? (
        <MutationRecoveryNotice
          actionLabel="Refresh monitor workspace"
          actionPending={isFetching}
          dataTestId="monitor-delete-recovery"
          description={
            deleteRecovery.recovery.mode === "outcome-unknown"
              ? "Praviar could not confirm whether the monitor was deleted. Refresh authoritative monitor state before sending another delete request."
              : "The delete request was rejected. Refresh the monitor workspace before deciding whether to try again."
          }
          dismissLabel="Keep monitor"
          mode={deleteRecovery.recovery.mode}
          onAction={() => {
            void refreshMonitorsAfterDelete();
          }}
          onDismiss={
            deleteRecovery.recovery.mode === "failed"
              ? deleteRecovery.clearRecovery
              : undefined
          }
          title={
            deleteRecovery.recovery.mode === "outcome-unknown"
              ? "Monitor deletion outcome unconfirmed"
              : "Monitor was not deleted"
          }
        />
      ) : null}

      <div
        className={
          selectedMonitor
            ? "grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,26rem)] xl:items-start"
            : "space-y-3"
        }
      >
        <div className="space-y-3">
          <MonitorsTable
            monitors={visibleMonitors}
            selectedMonitorId={selectedMonitorId}
            pendingMonitorId={pendingMonitorId}
            actionsDisabled={hasMutationRecovery}
            isLoading={isTableLoading}
            isUpdating={isWorkspaceUpdating || isMonitorActionPending}
            isOutOfRangeEmptyPage={isOutOfRangeEmptyPage}
            emptyTitle={emptyTableCopy.title}
            emptyDescription={emptyTableCopy.description}
            onToggleActive={(monitor: MonitorResponse) => {
              applyMonitorUpdate({
                monitorId: monitor.id,
                data: { is_active: !monitor.is_active },
              });
            }}
            onViewAlerts={(monitor: MonitorResponse) =>
              setSelectedMonitorId((currentId) => {
                const isClosing = currentId === monitor.id;
                if (isClosing) {
                  window.setTimeout(
                    () => lastAlertButtonRef.current?.focus(),
                    0,
                  );
                  return null;
                }
                return monitor.id;
              })
            }
            onAlertButtonFocus={(element) => {
              lastAlertButtonRef.current = element;
            }}
            onDelete={(monitorId: string) => {
              applyMonitorDelete(monitorId);
            }}
          />

          {!isFilterRefreshing && data.total > responsePerPage ? (
            <MonitorPagination
              page={displayPage}
              perPage={responsePerPage}
              total={data.total}
              visibleCount={visibleMonitors.length}
              totalPages={totalPages}
              requestedPage={page}
              isUpdating={isWorkspaceUpdating}
              isNavigationDisabled={
                Boolean(isPlaceholderData) ||
                isTableLoading ||
                isOutOfRangeEmptyPage
              }
              onPrevious={() => {
                setSelectedMonitorId(null);
                setPage((current) =>
                  current > totalPages ? totalPages : Math.max(1, current - 1),
                );
              }}
              onNext={() => {
                setSelectedMonitorId(null);
                setPage((current) => Math.min(totalPages, current + 1));
              }}
            />
          ) : null}
        </div>

        {selectedMonitor ? (
          <AlertsPanel
            key={selectedMonitor.id}
            monitorId={selectedMonitor.id}
            monitorName={selectedMonitor.compound_name || "Unnamed monitor"}
            openConclusionIds={(selectedMonitor.stale_conclusions ?? []).map(
              (impact) => impact.conclusion_id,
            )}
            canReassessConclusions={principal.data?.role === "attorney"}
            className="xl:sticky xl:top-24"
            onClose={closeAlertsPanel}
          />
        ) : null}
      </div>
    </div>
  );
}

function getMonitorEmptyCopy(
  filter: "all" | "active" | "paused",
  isFilterRefreshing = false,
  isOutOfRangeEmptyPage = false,
): {
  title: string;
  description: string;
} {
  if (isFilterRefreshing) {
    return {
      title: "Refreshing monitor view",
      description:
        "Praviar is loading the selected watch posture. Previous rows are hidden so stale monitor data is not shown under the wrong filter.",
    };
  }

  if (isOutOfRangeEmptyPage) {
    return {
      title: "Refreshing monitor page",
      description:
        "The requested monitor result window is empty while Praviar returns the workspace to a valid page.",
    };
  }

  if (filter === "active") {
    return {
      title: "No active monitors",
      description:
        "No active watches match this view. Switch filters or resume a paused monitor to restore scheduled monitoring.",
    };
  }

  if (filter === "paused") {
    return {
      title: "No paused monitors",
      description:
        "No paused watches match this view. Switch filters to review active monitors currently checking for patent changes.",
    };
  }

  return {
    title: "No monitors yet",
    description:
      "Create a monitor to track patent landscape changes. New watches start with a first-run pending state, and no clearance should be inferred until the first run completes.",
  };
}

function MonitorWorkspaceControls({
  activeFilter,
  total,
  visibleCount,
  isUpdating,
  isFilterRefreshing,
  isActionPending = false,
  actionsDisabled = false,
  onFilterChange,
}: {
  activeFilter: "all" | "active" | "paused";
  total: number;
  visibleCount: number;
  isUpdating: boolean;
  isFilterRefreshing: boolean;
  isActionPending?: boolean;
  actionsDisabled?: boolean;
  onFilterChange: (filter: "all" | "active" | "paused") => void;
}) {
  const filters: Array<{
    value: "all" | "active" | "paused";
    label: string;
  }> = [
    { value: "all", label: "All watches" },
    { value: "active", label: "Active" },
    { value: "paused", label: "Paused" },
  ];

  return (
    <section
      aria-label="Monitor workspace controls"
      className="praviar-surface-premium rounded-lg border border-[var(--card-border)] p-3 sm:p-4"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
            Watch posture filter
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {isActionPending
              ? "Applying a watch update before changing filters."
              : isFilterRefreshing
                ? "Refreshing the selected watch posture before showing matching monitors."
                : `Showing ${visibleCount.toLocaleString()} of ${total.toLocaleString()} matching monitors${isUpdating ? " while the workspace refreshes" : ""}.`}
          </p>
        </div>
        <div
          className="flex flex-wrap gap-2"
          role="group"
          aria-label="Filter monitors by active state"
        >
          {filters.map((filter) => (
            <Button
              key={filter.value}
              type="button"
              variant={activeFilter === filter.value ? "secondary" : "outline"}
              size="sm"
              className="min-h-11"
              disabled={actionsDisabled}
              aria-pressed={activeFilter === filter.value}
              onClick={() => onFilterChange(filter.value)}
            >
              {filter.label}
            </Button>
          ))}
        </div>
      </div>
    </section>
  );
}

function MonitorPagination({
  page,
  perPage,
  total,
  visibleCount,
  totalPages,
  requestedPage,
  isUpdating = false,
  isNavigationDisabled = false,
  onPrevious,
  onNext,
}: {
  page: number;
  perPage: number;
  total: number;
  visibleCount: number;
  totalPages: number;
  requestedPage?: number;
  isUpdating?: boolean;
  isNavigationDisabled?: boolean;
  onPrevious: () => void;
  onNext: () => void;
}) {
  const hasVisibleRange = total > 0 && visibleCount > 0;
  const rangeStart = hasVisibleRange ? (page - 1) * perPage + 1 : 0;
  const rangeEnd = hasVisibleRange
    ? Math.min(total, rangeStart + visibleCount - 1)
    : 0;
  const resultsLabel = hasVisibleRange
    ? `Showing ${rangeStart}-${rangeEnd} of ${total.toLocaleString()} monitors`
    : total > 0
      ? `Showing 0 of ${total.toLocaleString()} monitors`
      : "Showing 0 monitors";
  const updateLabel =
    isUpdating && requestedPage && requestedPage !== page
      ? `Updating page ${requestedPage}`
      : isUpdating
        ? "Refreshing monitors"
        : null;

  return (
    <div className="flex flex-col gap-3 text-sm text-[var(--text-secondary)] sm:flex-row sm:items-center sm:justify-between">
      <p className="sr-only" role="status" aria-live="polite">
        {updateLabel ? `${resultsLabel}. ${updateLabel}.` : resultsLabel}
      </p>
      <span className="flex flex-wrap items-center gap-2">
        <span className="tabular-nums">{resultsLabel}</span>
        {updateLabel ? (
          <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2 py-0.5 text-xs font-medium uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            {updateLabel}
          </span>
        ) : null}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1 || isNavigationDisabled}
          aria-label="Previous monitors page"
          title="Previous monitors page"
          onClick={onPrevious}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        <span className="text-xs tabular-nums text-[var(--text-tertiary)]">
          Page {page} of {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= totalPages || isNavigationDisabled}
          aria-label="Next monitors page"
          title="Next monitors page"
          onClick={onNext}
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
