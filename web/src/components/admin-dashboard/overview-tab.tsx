"use client";

import {
  Activity,
  AlertTriangle,
  Database,
  Gauge,
  ServerCog,
  ShieldCheck,
  TableProperties,
} from "lucide-react";
import { AnimatedCounter } from "@/components/shared/animated-counter";
import {
  StaggerContainer,
  StaggerItem,
} from "@/components/shared/stagger-container";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAdminHealth } from "@/hooks/use-admin";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import type { ServiceHealth } from "@/hooks/use-admin";
import { isAuthBoundaryError } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import {
  AdminRefreshWarning,
  AdminStatusState,
  ServiceStatusIcon,
} from "@/components/admin-dashboard/helpers";

function reportSystemOverviewAccessRestriction() {
  console.error("[OverviewTab] System overview access restricted");
}

function reportSystemOverviewLoadFailure() {
  console.error("[OverviewTab] Failed to load system health");
}

const HEALTHY_STATUSES = new Set(["healthy", "ok"]);
const WARNING_STATUSES = new Set(["degraded", "warning"]);
type PostureTone = "healthy" | "warning" | "critical" | "unknown";

function getServiceStatusCopy(status: string) {
  if (HEALTHY_STATUSES.has(status)) {
    return "Service responding";
  }
  if (WARNING_STATUSES.has(status)) {
    return "Service requires attention";
  }
  return "Service check failed";
}

function getPostureTone(services: ServiceHealth[]): PostureTone {
  if (services.length === 0) {
    return "unknown";
  }
  if (
    services.some(
      (svc) =>
        !HEALTHY_STATUSES.has(svc.status) && !WARNING_STATUSES.has(svc.status),
    )
  ) {
    return "critical";
  }
  if (services.some((svc) => WARNING_STATUSES.has(svc.status))) {
    return "warning";
  }
  return "healthy";
}

function formatAdminCount(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

export function OverviewTab() {
  const { data: health, isLoading, error, refetch } = useAdminHealth();
  const accessRestricted = isAuthBoundaryError(error);
  const initialLoading = isLoading && !health;
  const systemOverviewLoadFailed = Boolean(
    !initialLoading && error && !health && !accessRestricted,
  );

  useErrorDiagnostic(
    !initialLoading && accessRestricted,
    error,
    reportSystemOverviewAccessRestriction,
  );
  useErrorDiagnostic(
    systemOverviewLoadFailed,
    error,
    reportSystemOverviewLoadFailure,
  );

  if (initialLoading) {
    return <AdminStatusState surface="overview" variant="loading" />;
  }

  if (accessRestricted) {
    return (
      <AdminStatusState
        surface="overview"
        variant="restricted"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (error && !health) {
    return (
      <AdminStatusState
        surface="overview"
        variant="temporary"
        onRetry={() => {
          void refetch();
        }}
      />
    );
  }

  if (!health) return <AdminStatusState surface="overview" variant="auth" />;

  const serviceTotal = health.services.length;
  const healthyServices = health.services.filter((svc) =>
    HEALTHY_STATUSES.has(svc.status),
  ).length;
  const attentionServices = Math.max(serviceTotal - healthyServices, 0);
  const postureTone = getPostureTone(health.services);
  const postureLabel =
    postureTone === "critical"
      ? "Incident review"
      : postureTone === "unknown"
        ? "Coverage unknown"
        : postureTone === "warning"
          ? "Attention needed"
          : "Operational";
  const postureDescription =
    serviceTotal === 0
      ? "No service checks are configured in the current admin health feed."
      : attentionServices > 0
        ? `${attentionServices} ${attentionServices === 1 ? "check needs" : "checks need"} triage across ${serviceTotal} monitored ${serviceTotal === 1 ? "service" : "services"}.`
        : `All ${serviceTotal} monitored ${serviceTotal === 1 ? "service is" : "services are"} responding.`;
  const tableEntries = Object.entries(health.table_counts).sort(
    ([, a], [, b]) => b - a,
  );
  const tableTotal = tableEntries.reduce(
    (total, [, count]) => total + count,
    0,
  );
  const primaryTable = tableEntries[0];
  const topTables = tableEntries.slice(0, 4);
  const tableLabel = tableEntries.length === 1 ? "data table" : "data tables";
  const healthCopy =
    serviceTotal === 0
      ? "No service checks configured"
      : `${healthyServices} of ${serviceTotal} healthy`;
  const attentionCopy =
    serviceTotal === 0
      ? "Coverage unknown"
      : `${attentionServices} ${
          attentionServices === 1 ? "attention check" : "attention checks"
        }`;
  const postureToneClass =
    postureTone === "healthy"
      ? "border-success/25 bg-success/10 text-success"
      : postureTone === "warning" || postureTone === "unknown"
        ? "border-warning/25 bg-warning/10 text-warning"
        : "border-error/25 bg-error/10 text-error";

  return (
    <div className="space-y-6">
      {error ? <AdminRefreshWarning label="System overview" /> : null}

      <section
        aria-labelledby="admin-overview-posture-title"
        className="praviar-operational-field relative overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-sm)]"
        data-testid="admin-overview-control-field"
      >
        <div
          className="absolute inset-0 bg-gradient-to-r from-[var(--surface-card)] via-[var(--surface-card)]/95 to-[var(--surface-card)]/70"
          aria-hidden="true"
        />
        <div className="relative grid min-w-0 gap-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(19rem,0.76fr)] lg:p-7">
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <span
                className={cn(
                  "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border",
                  postureToneClass,
                )}
              >
                {postureTone === "healthy" ? (
                  <ShieldCheck className="h-5 w-5" aria-hidden="true" />
                ) : postureTone === "warning" || postureTone === "unknown" ? (
                  <AlertTriangle className="h-5 w-5" aria-hidden="true" />
                ) : (
                  <Gauge className="h-5 w-5" aria-hidden="true" />
                )}
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
                  Admin control plane
                </p>
                <h2
                  id="admin-overview-posture-title"
                  className="mt-1 break-words type-heading-xl text-[var(--text-primary)] [overflow-wrap:anywhere]"
                >
                  Operations posture
                </h2>
              </div>
              <span
                className={cn(
                  "ml-0 inline-flex min-h-8 items-center rounded-full border px-3 text-xs font-semibold sm:ml-auto",
                  postureToneClass,
                )}
              >
                {postureLabel}
              </span>
            </div>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-[var(--text-secondary)]">
              {postureDescription} Data inventory is reconciled across{" "}
              {tableEntries.length} {tableLabel} with{" "}
              {formatAdminCount(tableTotal)} tracked{" "}
              {tableTotal === 1 ? "record" : "records"}.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <span className="praviar-glass-chip rounded-lg px-3 py-2 text-xs font-medium text-[var(--text-secondary)]">
                {healthCopy}
              </span>
              <span className="praviar-glass-chip rounded-lg px-3 py-2 text-xs font-medium text-[var(--text-secondary)]">
                {attentionCopy}
              </span>
              <span className="praviar-glass-chip rounded-lg px-3 py-2 text-xs font-medium text-[var(--text-secondary)]">
                {formatAdminCount(tableTotal)} records tracked
              </span>
            </div>
          </div>

          <div className="grid min-w-0 grid-cols-2 gap-3">
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)]/75 p-3 shadow-[var(--shadow-xs)]">
              <Activity
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              <p className="mt-3 text-xs text-[var(--text-tertiary)]">
                Service checks
              </p>
              <p className="mt-1 text-lg font-semibold text-[var(--text-primary)] tabular-nums">
                {serviceTotal === 0
                  ? "0"
                  : `${healthyServices}/${serviceTotal}`}
              </p>
            </div>
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)]/75 p-3 shadow-[var(--shadow-xs)]">
              <AlertTriangle
                className={cn(
                  "h-4 w-4",
                  serviceTotal === 0 || attentionServices > 0
                    ? "text-warning"
                    : "text-success",
                )}
                aria-hidden="true"
              />
              <p className="mt-3 text-xs text-[var(--text-tertiary)]">
                Attention
              </p>
              <p className="mt-1 text-lg font-semibold text-[var(--text-primary)] tabular-nums">
                {serviceTotal === 0 ? "—" : attentionServices}
              </p>
            </div>
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)]/75 p-3 shadow-[var(--shadow-xs)]">
              <TableProperties
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              <p className="mt-3 text-xs text-[var(--text-tertiary)]">
                Data inventory
              </p>
              <p className="mt-1 text-lg font-semibold text-[var(--text-primary)] tabular-nums">
                {tableEntries.length}
              </p>
            </div>
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)]/75 p-3 shadow-[var(--shadow-xs)]">
              <Database
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              <p className="mt-3 text-xs text-[var(--text-tertiary)]">
                Records tracked
              </p>
              <p className="mt-1 text-lg font-semibold text-[var(--text-primary)] tabular-nums">
                {formatAdminCount(tableTotal)}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section aria-labelledby="admin-service-grid-title" className="space-y-3">
        <div className="flex min-w-0 flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h3
              id="admin-service-grid-title"
              className="type-heading-md text-[var(--text-primary)]"
            >
              Service checks
            </h3>
            <p className="mt-1 text-sm text-[var(--text-tertiary)]">
              {healthCopy} across the current admin health feed.
            </p>
          </div>
          <span className="inline-flex min-h-8 items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 text-xs font-medium text-[var(--text-secondary)]">
            <ServerCog className="h-3.5 w-3.5" aria-hidden="true" />
            {serviceTotal} monitored
          </span>
        </div>
        <StaggerContainer className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {serviceTotal === 0 ? (
            <StaggerItem>
              <Card className="h-full border-warning/20 bg-warning/5">
                <CardContent className="p-5">
                  <div className="flex min-w-0 items-start gap-3">
                    <AlertTriangle
                      className="mt-0.5 h-4 w-4 shrink-0 text-warning"
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        No service checks configured
                      </p>
                      <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
                        Admin health coverage is unknown until the backend
                        reports at least one service check.
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </StaggerItem>
          ) : null}
          {health.services.map((svc: ServiceHealth) => (
            <StaggerItem key={svc.name}>
              <Card className="h-full">
                <CardContent className="p-5">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="mt-0.5 shrink-0">
                      <ServiceStatusIcon status={svc.status} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="break-words text-sm font-semibold capitalize text-[var(--text-primary)] [overflow-wrap:anywhere]">
                        {svc.name}
                      </p>
                      <p className="mt-1 line-clamp-2 text-xs leading-5 text-[var(--text-tertiary)]">
                        {getServiceStatusCopy(svc.status)}
                      </p>
                    </div>
                    <span
                      className={cn(
                        "max-w-[9rem] shrink-0 truncate rounded-full px-2 py-0.5 text-xs font-medium",
                        HEALTHY_STATUSES.has(svc.status)
                          ? "bg-success/15 text-success"
                          : WARNING_STATUSES.has(svc.status)
                            ? "bg-warning/15 text-warning"
                            : "bg-error/15 text-error",
                      )}
                      title={svc.status}
                    >
                      {svc.status}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </StaggerItem>
          ))}
        </StaggerContainer>
      </section>

      <Card className="overflow-hidden">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Database
              className="h-4 w-4 text-brand-primary"
              aria-hidden="true"
            />
            Data inventory
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/65 p-4">
              <p className="text-xs font-medium text-[var(--text-tertiary)]">
                Records tracked
              </p>
              <p className="mt-2 type-heading-xl text-[var(--text-primary)] tabular-nums">
                <AnimatedCounter value={tableTotal} />
              </p>
            </div>
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/65 p-4">
              <p className="text-xs font-medium text-[var(--text-tertiary)]">
                Data tables
              </p>
              <p className="mt-2 type-heading-xl text-[var(--text-primary)] tabular-nums">
                <AnimatedCounter value={tableEntries.length} />
              </p>
            </div>
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/65 p-4">
              <p className="text-xs font-medium text-[var(--text-tertiary)]">
                Largest table
              </p>
              <p className="mt-2 break-words text-sm font-semibold capitalize text-[var(--text-primary)] [overflow-wrap:anywhere]">
                {primaryTable ? primaryTable[0].replace(/_/g, " ") : "None"}
              </p>
              <p className="mt-1 text-xs text-[var(--text-tertiary)] tabular-nums">
                {primaryTable
                  ? `${formatAdminCount(primaryTable[1])} records`
                  : "No records"}
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {topTables.map(([table, count]) => (
              <div key={table} className="flex min-w-0 flex-col">
                <span className="break-words text-xs capitalize text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                  {table.replace(/_/g, " ")}
                </span>
                <span className="type-heading-lg text-[var(--text-primary)] tabular-nums">
                  <AnimatedCounter value={count} />
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
