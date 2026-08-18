"use client";

import { useCallback, useMemo, useState } from "react";
import { Activity, Cpu, Database, DollarSign, Download } from "lucide-react";
import { AuditLogTab } from "@/components/admin-analytics/audit-log-tab";
import { CostsTab } from "@/components/admin-analytics/costs-tab";
import {
  buildCostAnalyticsCsv,
  buildModelDonutData,
  formatCurrency,
  PERIOD_OPTIONS,
} from "@/components/admin-analytics/helpers";
import { ModelsTab } from "@/components/admin-analytics/models-tab";
import { OverviewCards } from "@/components/admin-analytics/overview-cards";
import {
  AnalyticsRefreshWarning,
  AnalyticsStatusState,
} from "@/components/admin-analytics/status-state";
import { UsageTab } from "@/components/admin-analytics/usage-tab";
import { AppSurfaceHeader } from "@/components/shared/app-surface-header";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { isAuthBoundaryError } from "@/lib/api-client";
import {
  useCostAnalytics,
  useUsageAnalytics,
  useModelUsage,
  useAuditLog,
} from "@/hooks/use-admin-analytics";
import type { AuditLogFilters } from "@/hooks/use-admin-analytics";

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<string>("month");
  const [auditPage, setAuditPage] = useState(1);
  const [auditFilters, setAuditFilters] = useState<AuditLogFilters>({});

  const costQuery = useCostAnalytics(period);
  const usageQuery = useUsageAnalytics(period);
  const modelQuery = useModelUsage(period);
  const auditQuery = useAuditLog(auditPage, auditFilters);

  const {
    data: costData,
    isLoading: costLoading,
    error: costError,
  } = costQuery;
  const {
    data: usageData,
    isLoading: usageLoading,
    error: usageError,
  } = usageQuery;
  const {
    data: modelData,
    isLoading: modelLoading,
    error: modelError,
  } = modelQuery;
  const {
    data: auditData,
    isLoading: auditLoading,
    error: auditError,
  } = auditQuery;

  const isLoading = costLoading || usageLoading || modelLoading;
  const hasAnyData = Boolean(costData || usageData || modelData || auditData);
  const hasAnyError = Boolean(
    costError || usageError || modelError || auditError,
  );
  const hasAuthBoundaryError = [
    costError,
    usageError,
    modelError,
    auditError,
  ].some(isAuthBoundaryError);

  const modelDonutData = useMemo(
    () => buildModelDonutData(modelData),
    [modelData],
  );

  const refetchAnalytics = useCallback(() => {
    void Promise.all([
      costQuery.refetch(),
      usageQuery.refetch(),
      modelQuery.refetch(),
      auditQuery.refetch(),
    ]);
  }, [auditQuery, costQuery, modelQuery, usageQuery]);

  const handleExportCsv = useCallback(() => {
    if (!costData) return;
    const csv = buildCostAnalyticsCsv(costData.daily_costs, {
      period,
      generatedAt: new Date().toISOString(),
    });
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `praviar-analytics-${period}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [costData, period]);

  const handleAuditFiltersChange = useCallback((filters: AuditLogFilters) => {
    setAuditFilters(filters);
    setAuditPage(1);
  }, []);

  if (hasAuthBoundaryError) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
        <AnalyticsStatusState variant="restricted" onRetry={refetchAnalytics} />
      </div>
    );
  }

  if (!isLoading && hasAnyError && !hasAnyData) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
        <AnalyticsStatusState variant="temporary" onRetry={refetchAnalytics} />
      </div>
    );
  }

  if (!isLoading && !hasAnyData) {
    return (
      <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
        <AnalyticsStatusState variant="access" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 animate-fade-up">
      <AppSurfaceHeader
        dataTestId="admin-analytics-app-surface-header"
        eyebrow="Praviar control plane"
        title="Cost & Usage"
        description="Track administrator-scoped LLM spend, model usage, pipeline volume, and audit events."
        metrics={[
          {
            label: "Spend",
            value: costData
              ? formatCurrency(costData.total_cost_usd)
              : "Loading",
            tone: costError ? "warning" : "default",
          },
          {
            label: "Analyses",
            value: usageData
              ? usageData.total_analyses.toLocaleString()
              : "Loading",
            tone: usageError ? "warning" : "default",
          },
          {
            label: "Models",
            value: modelData
              ? modelData.models.length.toLocaleString()
              : "Loading",
            tone: modelError ? "warning" : "default",
          },
        ]}
        actions={
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
            <div
              role="group"
              aria-label="Analytics time range"
              className="praviar-glass-panel grid grid-cols-3 gap-1 rounded-lg p-1 sm:flex sm:items-center"
            >
              {PERIOD_OPTIONS.map((opt) => (
                <button
                  type="button"
                  key={opt.value}
                  aria-pressed={period === opt.value}
                  onClick={() => setPeriod(opt.value)}
                  className={`min-h-11 rounded-md px-3 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] ${
                    period === opt.value
                      ? "praviar-glass-pill text-brand-primary"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <Button
              variant="outline"
              onClick={handleExportCsv}
              disabled={!costData}
              className="min-h-11 w-full sm:w-auto"
            >
              <Download className="h-4 w-4 mr-1.5" />
              Export costs CSV
            </Button>
          </div>
        }
      />

      {hasAnyError ? (
        <AnalyticsRefreshWarning onRetry={refetchAnalytics} />
      ) : null}

      <OverviewCards
        isLoading={isLoading}
        costData={costData}
        usageData={usageData}
        modelData={modelData}
      />

      <Tabs defaultValue="costs">
        <TabsList
          aria-label="Analytics sections"
          className="grid w-full grid-cols-2 justify-stretch overflow-visible sm:inline-flex sm:w-auto sm:justify-start sm:overflow-x-auto"
        >
          <TabsTrigger
            value="costs"
            className="min-h-11 w-full shrink-0 sm:w-auto"
          >
            <DollarSign className="h-4 w-4" />
            Costs
          </TabsTrigger>
          <TabsTrigger
            value="usage"
            className="min-h-11 w-full shrink-0 sm:w-auto"
          >
            <Activity className="h-4 w-4" />
            Usage
          </TabsTrigger>
          <TabsTrigger
            value="models"
            className="min-h-11 w-full shrink-0 sm:w-auto"
          >
            <Cpu className="h-4 w-4" />
            Models
          </TabsTrigger>
          <TabsTrigger
            value="audit"
            className="min-h-11 w-full shrink-0 sm:w-auto"
          >
            <Database className="h-4 w-4" />
            Audit Log
          </TabsTrigger>
        </TabsList>

        <TabsContent value="costs">
          <CostsTab
            costData={costData}
            costLoading={costLoading}
            costError={costError}
            onRetry={() => {
              void costQuery.refetch();
            }}
          />
        </TabsContent>

        <TabsContent value="usage">
          <UsageTab
            usageData={usageData}
            usageLoading={usageLoading}
            usageError={usageError}
            onRetry={() => {
              void usageQuery.refetch();
            }}
          />
        </TabsContent>

        <TabsContent value="models">
          <ModelsTab
            modelData={modelData}
            modelLoading={modelLoading}
            modelError={modelError}
            modelDonutData={modelDonutData}
            onRetry={() => {
              void modelQuery.refetch();
            }}
          />
        </TabsContent>

        <TabsContent value="audit">
          <AuditLogTab
            auditData={auditData}
            auditLoading={auditLoading}
            auditError={auditError}
            auditFilters={auditFilters}
            auditPage={auditPage}
            onFiltersChange={handleAuditFiltersChange}
            onPreviousPage={() => setAuditPage((p) => Math.max(1, p - 1))}
            onNextPage={() => setAuditPage((p) => p + 1)}
            onResetPage={() => setAuditPage(1)}
            onRetry={() => {
              void auditQuery.refetch();
            }}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
