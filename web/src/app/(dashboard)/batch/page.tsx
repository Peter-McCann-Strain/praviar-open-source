"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Layers,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { APIError, isAuthBoundaryError } from "@/lib/api-client";
import { logError } from "@/lib/error-logger";
import { useErrorDiagnostic } from "@/hooks/use-error-diagnostic";
import { useAuthToken } from "@/hooks/use-auth-token";
import { useMutationRecovery } from "@/hooks/use-mutation-recovery";
import { usePrincipalCapabilities } from "@/hooks/use-principal-capabilities";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { WorkspaceStatusState } from "@/components/shared/workspace-status-state";
import { MutationRecoveryNotice } from "@/components/shared/mutation-recovery-notice";
import {
  useBatches,
  useCancelBatch,
  type BatchResponse,
} from "@/hooks/use-batch";
import { BatchPageHeader } from "@/components/batch/batch-page-header";
import { CreateBatchForm } from "@/components/batch/create-batch-form";
import { BatchDetailPanel } from "@/components/batch/batch-detail-panel";
import { BatchSummaryCards } from "@/components/batch/batch-summary-cards";
import { BatchesTable } from "@/components/batch/batches-table";
import { BatchPagination } from "@/components/batch/batch-pagination";

function reportBatchWorkspaceAccessRestriction() {
  console.error("[BatchPage] Batch workspace access restricted");
}

function reportBatchWorkspaceLoadFailure(error: unknown) {
  logError(
    error instanceof APIError
      ? error
      : new Error("Batch workspace load failed"),
    { source: "BatchPage", extra: { action: "load" } },
  );
}

function BatchPortfolioRail({ items }: { items: BatchResponse[] }) {
  const totalCompounds = items.reduce(
    (sum, batch) => sum + batch.total_compounds,
    0,
  );
  const completed = items.reduce(
    (sum, batch) => sum + batch.completed_count,
    0,
  );
  const failed = items.reduce((sum, batch) => sum + batch.failed_count, 0);
  const activeRuns = items.filter((batch) =>
    ["running", "pending"].includes(batch.status),
  ).length;
  const readyRuns = items.filter((batch) =>
    ["completed", "partial"].includes(batch.status),
  ).length;
  const coveragePct =
    totalCompounds > 0
      ? Math.min(100, Math.round((completed / totalCompounds) * 100))
      : 0;

  return (
    <aside
      aria-label="Portfolio batch command rail"
      className="praviar-surface-premium overflow-hidden rounded-lg border border-[var(--card-border)]"
    >
      <div className="praviar-control-plane-header border-b border-[var(--border-subtle)] p-5">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-base font-semibold text-[var(--text-primary)]">
              Portfolio control rail
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              Batch posture, counsel handoff readiness, and failure watch stay
              visible while operators scan runs.
            </p>
          </div>
        </div>
      </div>
      <div className="grid gap-4 p-5">
        <div>
          <div className="flex items-end justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                Screened compounds
              </p>
              <p className="mt-1 text-3xl font-semibold tabular-nums text-[var(--text-primary)]">
                {completed.toLocaleString()} / {totalCompounds.toLocaleString()}
              </p>
            </div>
            <span className="rounded-full border border-brand-primary/20 bg-brand-primary/10 px-2.5 py-1 text-xs font-semibold text-brand-primary">
              {coveragePct}% complete
            </span>
          </div>
          <div
            className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--surface-active)]"
            aria-hidden="true"
          >
            <div
              className="h-full rounded-full bg-brand-primary"
              style={{ width: `${coveragePct}%` }}
            />
          </div>
        </div>

        <div className="grid gap-2">
          <RailMetric
            icon={Clock3}
            label="Active runs"
            value={activeRuns.toLocaleString()}
            detail="Running or queued"
          />
          <RailMetric
            icon={CheckCircle2}
            label="Counsel handoff"
            value={readyRuns.toLocaleString()}
            detail="Completed or partially complete"
          />
          <RailMetric
            icon={AlertTriangle}
            label="Failure watch"
            value={failed.toLocaleString()}
            detail="Needs operator review"
            tone={failed > 0 ? "warning" : "success"}
          />
        </div>
      </div>
    </aside>
  );
}

function RailMetric({
  icon: Icon,
  label,
  value,
  detail,
  tone = "default",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "success" | "warning";
}) {
  const iconClass =
    tone === "warning"
      ? "border-warning/20 bg-warning/10 text-warning"
      : tone === "success"
        ? "border-success/20 bg-success/10 text-success"
        : "border-brand-primary/20 bg-brand-primary/10 text-brand-primary";

  return (
    <div className="flex items-center gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 p-3">
      <span
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${iconClass}`}
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {label}
        </p>
        <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">{detail}</p>
      </div>
      <p className="text-xl font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

export default function BatchPage() {
  const token = useAuthToken();
  const principal = usePrincipalCapabilities(token);
  const [page, setPage] = useState(1);
  const { data, isLoading, isFetching, error, refetch } = useBatches(page);
  const cancelBatch = useCancelBatch();
  const cancelRecovery = useMutationRecovery<string>();
  const [showCreate, setShowCreate] = useState(false);
  const [viewDetail, setViewDetail] = useState<{
    id: string;
    name: string;
  } | null>(null);

  useEffect(() => {
    if (!showCreate) return;
    const frame = requestAnimationFrame(() => {
      document.getElementById("batch-name")?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [showCreate]);

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / 20));
  const displayPage = Math.min(page, totalPages);
  const accessRestricted = isAuthBoundaryError(error);
  const workspaceLoadFailed = Boolean(
    !isLoading && error && !data && !accessRestricted,
  );

  useErrorDiagnostic(
    !isLoading && accessRestricted,
    error,
    reportBatchWorkspaceAccessRestriction,
  );
  useErrorDiagnostic(
    workspaceLoadFailed,
    error,
    reportBatchWorkspaceLoadFailure,
  );

  const requestBatchCancellation = async (batchId: string) => {
    const attempt = cancelRecovery.beginAttempt();
    cancelRecovery.clearRecoveryForAttempt(attempt);
    try {
      await cancelBatch.mutateAsync(batchId);
      if (!cancelRecovery.clearRecoveryForAttempt(attempt)) return;
      if (viewDetail?.id === batchId) {
        setViewDetail(null);
      }
    } catch (cancelError) {
      cancelRecovery.captureFailure(cancelError, batchId, attempt);
    }
  };

  const reconcileBatchCancellation = async () => {
    const refreshed = await refetch();
    if (refreshed.error) return;
    cancelRecovery.clearRecovery();
  };

  if (isLoading) {
    return (
      <div className="space-y-5 animate-fade-up">
        <BatchPageHeader
          onToggleCreate={() => setShowCreate((current) => !current)}
          actionsDisabled
        />
        <WorkspaceStatusState surface="batch" variant="loading" />
      </div>
    );
  }

  if (accessRestricted) {
    return (
      <div className="space-y-5 animate-fade-up">
        <BatchPageHeader
          onToggleCreate={() => setShowCreate((current) => !current)}
          actionsDisabled
        />
        <WorkspaceStatusState
          surface="batch"
          variant="restricted"
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="space-y-5 animate-fade-up">
        <BatchPageHeader
          onToggleCreate={() => setShowCreate((current) => !current)}
          actionsDisabled
        />
        <WorkspaceStatusState
          surface="batch"
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
      <div className="space-y-5 animate-fade-up">
        <BatchPageHeader
          onToggleCreate={() => setShowCreate((current) => !current)}
          actionsDisabled
        />
        <WorkspaceStatusState surface="batch" variant="auth" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <BatchPageHeader
        onToggleCreate={() => setShowCreate((current) => !current)}
        createOpen={showCreate}
      />

      {cancelRecovery.recovery ? (
        <MutationRecoveryNotice
          actionLabel={
            cancelRecovery.recovery.mode === "outcome-unknown"
              ? "Refresh batch ledger"
              : "Retry cancellation"
          }
          actionPending={
            cancelRecovery.recovery.mode === "outcome-unknown"
              ? Boolean(isFetching)
              : cancelBatch.isPending
          }
          dataTestId="batch-cancel-recovery"
          description={
            cancelRecovery.recovery.mode === "outcome-unknown"
              ? "Praviar could not confirm whether the batch stopped. Refresh authoritative batch state before sending another cancellation."
              : "The cancellation was rejected. Retry the exact batch cancellation or dismiss this notice to keep the run active."
          }
          dismissLabel="Keep batch active"
          mode={cancelRecovery.recovery.mode}
          onAction={() => {
            if (cancelRecovery.recovery?.mode === "outcome-unknown") {
              void reconcileBatchCancellation();
              return;
            }
            void requestBatchCancellation(cancelRecovery.recovery!.variables);
          }}
          onDismiss={
            cancelRecovery.recovery.mode === "failed"
              ? cancelRecovery.clearRecovery
              : undefined
          }
          title={
            cancelRecovery.recovery.mode === "outcome-unknown"
              ? "Batch cancellation outcome unconfirmed"
              : "Batch was not cancelled"
          }
        />
      ) : null}

      {data && data.items.length > 0 && <BatchSummaryCards data={data} />}

      <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_25rem] 2xl:items-start">
        <div className="min-w-0 space-y-6">
          {showCreate && (
            <div id="create-batch-panel">
              <CreateBatchForm onClose={() => setShowCreate(false)} />
            </div>
          )}

          {data.items.length === 0 ? (
            <Card>
              <CardContent className="p-0">
                <EmptyState
                  icon={Layers}
                  title="No batch jobs yet"
                  description="Create a batch to analyze multiple compounds simultaneously. Each compound gets a full FTO pipeline run."
                />
              </CardContent>
            </Card>
          ) : (
            <BatchesTable
              items={data.items}
              onOpenDetails={setViewDetail}
              onCancel={(batchId) => {
                void requestBatchCancellation(batchId);
              }}
              cancelPending={cancelBatch.isPending}
              cancelBlocked={Boolean(cancelRecovery.recovery)}
              currentUserRole={principal.data?.role}
              riskRatingsRestricted={principal.data?.risk_ratings_restricted}
            />
          )}

          <BatchPagination
            page={displayPage}
            totalPages={totalPages}
            total={data.total}
            onPrevious={() =>
              setPage((current) =>
                current > totalPages ? totalPages : Math.max(1, current - 1),
              )
            }
            onNext={() =>
              setPage((current) => Math.min(totalPages, current + 1))
            }
          />
        </div>

        <div
          className={
            viewDetail
              ? "min-w-0 2xl:sticky 2xl:top-24"
              : "hidden min-w-0 2xl:sticky 2xl:top-24 2xl:block"
          }
        >
          {viewDetail ? (
            <BatchDetailPanel
              batchId={viewDetail.id}
              batchName={viewDetail.name}
              onClose={() => setViewDetail(null)}
              currentUserRole={principal.data?.role}
              riskRatingsRestricted={principal.data?.risk_ratings_restricted}
            />
          ) : (
            <BatchPortfolioRail items={data.items} />
          )}
        </div>
      </div>
    </div>
  );
}
