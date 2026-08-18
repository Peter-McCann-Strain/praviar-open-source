"use client";

import { AnimatedCounter } from "@/components/shared/animated-counter";
import {
  StaggerContainer,
  StaggerItem,
} from "@/components/shared/stagger-container";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AdminRefreshWarning,
  AdminStatusState,
} from "@/components/admin-dashboard/helpers";
import { useAdminTasks } from "@/hooks/use-admin";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import { isAuthBoundaryError } from "@/lib/api-client";
import type { TaskInfo } from "@/hooks/use-admin";

function reportTaskQueueAccessRestriction() {
  console.error("[TasksTab] Task queue access restricted");
}

function reportTaskQueueLoadFailure() {
  console.error("[TasksTab] Failed to load task queue");
}

function TaskTable({
  taskList,
  label,
}: {
  taskList: TaskInfo[];
  label: string;
}) {
  if (taskList.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{label}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="py-4 text-center text-sm text-[var(--text-tertiary)]">
            No {label.toLowerCase()}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">
          {label} ({taskList.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div>
          <table className="w-full text-sm">
            <thead className="hidden md:table-header-group">
              <tr className="border-b border-[var(--border-subtle)]">
                <th className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]">
                  Task ID
                </th>
                <th className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]">
                  Name
                </th>
                <th className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="block divide-y divide-[var(--border-subtle)] md:table-row-group">
              {taskList.map((task: TaskInfo) => (
                <tr
                  key={task.id}
                  className="block p-4 transition-colors hover:bg-[var(--surface-subtle)] md:table-row md:p-0"
                >
                  <td className="flex items-start justify-between gap-4 py-2 font-mono text-xs tabular-nums text-[var(--text-tertiary)] md:table-cell md:max-w-[200px] md:truncate md:px-6 md:py-3">
                    <span className="type-label-sm font-sans text-[var(--text-tertiary)] md:hidden">
                      Task ID
                    </span>
                    <span className="min-w-0 break-all text-right md:block md:truncate md:text-left">
                      {task.id}
                    </span>
                  </td>
                  <td className="flex items-start justify-between gap-4 py-2 text-sm text-[var(--text-primary)] md:table-cell md:px-6 md:py-3">
                    <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                      Name
                    </span>
                    <span className="min-w-0 text-right [overflow-wrap:anywhere] md:block md:text-left">
                      {task.name}
                    </span>
                  </td>
                  <td className="flex items-center justify-between gap-4 py-2 md:table-cell md:px-6 md:py-3">
                    <span className="type-label-sm text-[var(--text-tertiary)] md:hidden">
                      Status
                    </span>
                    <span
                      className={`inline-flex max-w-full min-w-0 items-center rounded-full px-2.5 py-0.5 text-xs font-medium [overflow-wrap:anywhere] md:max-w-[12rem] md:truncate ${
                        task.status === "active"
                          ? "bg-info/15 text-info"
                          : task.status === "reserved"
                            ? "bg-warning/15 text-warning"
                            : "bg-[var(--surface-active)] text-[var(--text-secondary)]"
                      }`}
                      title={task.status}
                    >
                      {task.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function formatBackendLabel(backend: string) {
  if (backend === "cloud_tasks") return "Cloud Tasks";
  if (backend === "celery") return "Celery";
  return backend;
}

export function TasksTab() {
  const { data: tasks, isLoading, error, refetch } = useAdminTasks();
  const accessRestricted = isAuthBoundaryError(error);
  const initialLoading = isLoading && !tasks;
  const taskQueueLoadFailed = Boolean(
    !initialLoading && error && !tasks && !accessRestricted,
  );

  useErrorDiagnostic(
    !initialLoading && accessRestricted,
    error,
    reportTaskQueueAccessRestriction,
  );
  useErrorDiagnostic(taskQueueLoadFailed, error, reportTaskQueueLoadFailure);

  if (initialLoading) {
    return <AdminStatusState surface="tasks" variant="loading" />;
  }

  if (accessRestricted) {
    return (
      <AdminStatusState
        surface="tasks"
        variant="restricted"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (error && !tasks) {
    return (
      <AdminStatusState
        surface="tasks"
        variant="temporary"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (!tasks) return <AdminStatusState surface="tasks" variant="auth" />;

  const backendLabel = formatBackendLabel(tasks.backend);

  return (
    <div className="space-y-6">
      {error ? <AdminRefreshWarning label="Task queue" /> : null}
      <StaggerContainer className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <StaggerItem>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-[var(--text-secondary)]">Dispatcher</p>
              <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
                {backendLabel}
              </p>
              {tasks.detail ? (
                <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                  Dispatcher status received
                </p>
              ) : null}
            </CardContent>
          </Card>
        </StaggerItem>
        <StaggerItem>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-[var(--text-secondary)]">Running</p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                <AnimatedCounter value={tasks.active.length} />
              </p>
            </CardContent>
          </Card>
        </StaggerItem>
        <StaggerItem>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-[var(--text-secondary)]">Reserved</p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                <AnimatedCounter value={tasks.reserved.length} />
              </p>
            </CardContent>
          </Card>
        </StaggerItem>
        <StaggerItem>
          <Card>
            <CardContent className="p-5">
              <p className="text-xs text-[var(--text-secondary)]">Scheduled</p>
              <p className="type-heading-xl text-[var(--text-primary)] tabular-nums">
                <AnimatedCounter value={tasks.scheduled_count} />
              </p>
            </CardContent>
          </Card>
        </StaggerItem>
      </StaggerContainer>

      {tasks.inspectable ? (
        <>
          <TaskTable taskList={tasks.active} label="Running Tasks" />
          <TaskTable taskList={tasks.reserved} label="Reserved Tasks" />
        </>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Managed Queue</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--text-secondary)]">
              {backendLabel} is configured as the production dispatcher. Queue
              depth and retry state are managed by the cloud provider, while
              Praviar records job status on each analysis.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
