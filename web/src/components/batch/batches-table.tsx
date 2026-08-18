"use client";

import { useState } from "react";
import Link from "next/link";
import {
  BarChart3,
  ChevronDown,
  CheckCircle,
  XCircle,
  Loader2,
  AlertTriangle,
  Clock,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { BatchResponse } from "@/hooks/use-batch";
import { useHydrationSafeRelativeTime } from "@/hooks/use-hydration-safe-relative-time";
import { relativeTime } from "@/components/batch/helpers";
import { cn } from "@/lib/utils";
import {
  canAccessFullReport,
  getReportAccessHrefWithQuery,
} from "@/lib/report-permissions";

interface BatchesTableProps {
  items: BatchResponse[];
  onOpenDetails: (batch: { id: string; name: string }) => void;
  onCancel: (batchId: string) => void;
  cancelPending: boolean;
  cancelBlocked?: boolean;
  currentUserRole?: string | null;
  riskRatingsRestricted?: boolean;
}

type BatchFilter = "all" | "active" | "handoff" | "attention";

const FILTERS: Array<{ id: BatchFilter; label: string }> = [
  { id: "all", label: "All batches" },
  { id: "active", label: "Active" },
  { id: "handoff", label: "Counsel handoff" },
  { id: "attention", label: "Needs attention" },
];

function BatchStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return <CheckCircle className="h-4 w-4 text-success" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-error" />;
    case "running":
      return (
        <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none text-info" />
      );
    case "partial":
      return <AlertTriangle className="h-4 w-4 text-warning" />;
    default:
      return <Clock className="h-4 w-4 text-[var(--text-tertiary)]" />;
  }
}

function getProgressPct(batch: BatchResponse) {
  return batch.total_compounds > 0
    ? Math.min(
        100,
        Math.round(
          ((batch.completed_count + batch.failed_count) /
            batch.total_compounds) *
            100,
        ),
      )
    : 0;
}

function getRiskState(batch: BatchResponse) {
  if (batch.failed_count > 0) {
    return {
      label: "Watch",
      variant: "warning" as const,
      detail: `${batch.failed_count} failed`,
    };
  }
  if (batch.status === "running" || batch.status === "pending") {
    return {
      label: "Open",
      variant: "default" as const,
      detail: "In flight",
    };
  }
  return {
    label: "Clear",
    variant: "success" as const,
    detail: "No failures",
  };
}

function getReviewState(batch: BatchResponse) {
  if (batch.failed_count > 0 || batch.status === "partial") {
    return "Counsel review";
  }
  if (batch.status === "completed") {
    return "Ready";
  }
  if (batch.status === "running") {
    return "Running";
  }
  if (batch.status === "pending") {
    return "Queued";
  }
  return "Monitor";
}

function matchesFilter(batch: BatchResponse, filter: BatchFilter) {
  if (filter === "active") {
    return ["running", "pending"].includes(batch.status);
  }
  if (filter === "handoff") {
    return ["completed", "partial"].includes(batch.status);
  }
  if (filter === "attention") {
    return (
      batch.failed_count > 0 || ["failed", "partial"].includes(batch.status)
    );
  }
  return true;
}

export function BatchesTable({
  items,
  onOpenDetails,
  onCancel,
  cancelPending,
  cancelBlocked = false,
  currentUserRole,
  riskRatingsRestricted,
}: BatchesTableProps) {
  const [cancelReviewBatch, setCancelReviewBatch] =
    useState<BatchResponse | null>(null);
  const [cancelingId, setCancelingId] = useState<string | null>(null);
  const [filter, setFilter] = useState<BatchFilter>("all");
  const [query, setQuery] = useState("");
  const formatRelativeTime = useHydrationSafeRelativeTime(relativeTime);

  const normalizedQuery = query.trim().toLowerCase();
  const filteredItems = items.filter((batch) => {
    const matchesStatus = matchesFilter(batch, filter);
    const matchesSearch =
      normalizedQuery.length === 0 ||
      [batch.name, batch.id, batch.status]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery);

    return matchesStatus && matchesSearch;
  });

  const handleConfirmCancel = () => {
    if (cancelPending) return;
    if (!cancelReviewBatch) return;
    setCancelingId(cancelReviewBatch.id);
    onCancel(cancelReviewBatch.id);
    setCancelReviewBatch(null);
  };
  const fullReportAllowed = canAccessFullReport(
    currentUserRole,
    riskRatingsRestricted,
  );

  return (
    <>
      <Card className="overflow-hidden">
        <CardContent className="p-0">
          <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 p-4">
            <div className="flex flex-col gap-4 min-[1440px]:flex-row min-[1440px]:items-center min-[1440px]:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-brand-primary/20 bg-brand-primary/10 text-brand-primary">
                    <BarChart3 className="h-4 w-4" aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-[var(--text-primary)]">
                      Portfolio runs
                    </h2>
                    <p className="text-xs text-[var(--text-tertiary)]">
                      {filteredItems.length.toLocaleString()} of{" "}
                      {items.length.toLocaleString()} visible after filters.
                    </p>
                  </div>
                </div>
              </div>
              <div className="grid min-w-0 gap-3 min-[1440px]:w-full min-[1440px]:max-w-[40rem] min-[1440px]:grid-cols-[minmax(0,1fr)_auto]">
                <label className="relative block min-w-0">
                  <span className="sr-only">Search batch runs</span>
                  <Search
                    className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-tertiary)]"
                    aria-hidden="true"
                  />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search batches..."
                    className="h-11 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] shadow-[var(--shadow-xs)] outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                  />
                </label>
                <div
                  className="-mx-1 flex min-w-0 flex-nowrap gap-2 overflow-x-auto px-1 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0"
                  aria-label="Batch status filters"
                >
                  {FILTERS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      aria-pressed={filter === item.id}
                      className={cn(
                        "min-h-11 max-w-full shrink-0 whitespace-nowrap rounded-lg border px-3 text-xs font-semibold leading-5 transition-colors",
                        filter === item.id
                          ? "border-brand-primary/35 bg-brand-primary/10 text-brand-primary"
                          : "border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]",
                      )}
                      onClick={() => setFilter(item.id)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
          <div
            className="overflow-hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] min-[1440px]:overflow-x-auto"
            role="region"
            tabIndex={0}
            aria-label="Portfolio batch table horizontal scroll area"
          >
            <table className="w-full text-sm min-[1440px]:min-w-[960px]">
              <thead className="hidden min-[1440px]:table-header-group">
                <tr className="border-b border-[var(--border-subtle)]">
                  <th className="px-6 py-3 text-left type-label-sm font-medium text-[var(--text-tertiary)]">
                    Batch
                  </th>
                  <th className="px-6 py-3 text-center type-label-sm font-medium text-[var(--text-tertiary)]">
                    Status
                  </th>
                  <th className="px-6 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]">
                    Progress
                  </th>
                  <th className="px-6 py-3 text-center type-label-sm font-medium text-[var(--text-tertiary)]">
                    Risk
                  </th>
                  <th className="px-6 py-3 text-center type-label-sm font-medium text-[var(--text-tertiary)]">
                    Review state
                  </th>
                  <th className="px-6 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]">
                    Updated
                  </th>
                  <th className="px-6 py-3 text-right type-label-sm font-medium text-[var(--text-tertiary)]">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="block divide-y divide-[var(--border-subtle)] min-[1440px]:table-row-group">
                {filteredItems.map((batch: BatchResponse) => {
                  const progressPct = getProgressPct(batch);
                  const riskState = getRiskState(batch);
                  const reviewState = getReviewState(batch);

                  return (
                    <tr
                      key={batch.id}
                      className="block min-w-0 p-4 transition-colors odd:bg-[color-mix(in_srgb,var(--brand-soft-mint)_14%,transparent)] hover:bg-[var(--surface-subtle)] min-[1440px]:table-row min-[1440px]:p-0"
                    >
                      <td className="flex min-w-0 items-start justify-between gap-4 py-2 min-[1440px]:table-cell min-[1440px]:px-6 min-[1440px]:py-3">
                        <span className="type-label-sm text-[var(--text-tertiary)] min-[1440px]:hidden">
                          Batch
                        </span>
                        <div className="min-w-0 text-right min-[1440px]:text-left">
                          <p className="max-w-full break-words text-sm font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                            {batch.name}
                          </p>
                          <p className="mt-1 hidden max-w-full break-all font-mono text-xs text-[var(--text-tertiary)] min-[1440px]:block">
                            {batch.id}
                          </p>
                        </div>
                      </td>
                      <td className="flex min-w-0 items-center justify-between gap-4 py-2 min-[1440px]:table-cell min-[1440px]:px-6 min-[1440px]:py-3 min-[1440px]:text-center">
                        <span className="type-label-sm text-[var(--text-tertiary)] min-[1440px]:hidden">
                          Status
                        </span>
                        <div className="flex items-center justify-end gap-1.5 min-[1440px]:justify-center">
                          <BatchStatusIcon status={batch.status} />
                          <span className="text-xs font-medium capitalize text-[var(--text-secondary)]">
                            {batch.status}
                          </span>
                        </div>
                      </td>
                      <td className="block min-w-0 py-2 min-[1440px]:table-cell min-[1440px]:px-6 min-[1440px]:py-3 min-[1440px]:text-right">
                        <div className="mb-2 flex items-center justify-between gap-4 min-[1440px]:hidden">
                          <span className="type-label-sm text-[var(--text-tertiary)]">
                            Progress
                          </span>
                        </div>
                        <div className="flex min-w-0 items-center justify-end gap-2">
                          <div className="h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-[var(--surface-active)]">
                            <div
                              className="h-full rounded-full bg-brand-primary transition-all duration-500"
                              style={{ width: `${progressPct}%` }}
                            />
                          </div>
                          <span className="w-24 shrink-0 text-right text-xs tabular-nums text-[var(--text-tertiary)]">
                            {progressPct}% · {batch.completed_count}/
                            {batch.total_compounds}
                            {batch.failed_count > 0 ? (
                              <span className="text-error">
                                {" "}
                                ({batch.failed_count}F)
                              </span>
                            ) : null}
                          </span>
                        </div>
                      </td>
                      <td className="flex min-w-0 items-center justify-between gap-4 py-2 min-[1440px]:table-cell min-[1440px]:px-6 min-[1440px]:py-3 min-[1440px]:text-center">
                        <span className="type-label-sm text-[var(--text-tertiary)] min-[1440px]:hidden">
                          Risk
                        </span>
                        <Badge variant={riskState.variant}>
                          {riskState.label}
                        </Badge>
                      </td>
                      <td className="flex min-w-0 items-center justify-between gap-4 py-2 min-[1440px]:table-cell min-[1440px]:px-6 min-[1440px]:py-3 min-[1440px]:text-center">
                        <span className="type-label-sm text-[var(--text-tertiary)] min-[1440px]:hidden">
                          Review state
                        </span>
                        <span className="inline-flex min-w-0 items-center justify-end gap-2 break-words text-xs font-medium text-[var(--text-secondary)] [overflow-wrap:anywhere] min-[1440px]:justify-center">
                          <ShieldCheck
                            className="h-3.5 w-3.5 text-brand-primary"
                            aria-hidden="true"
                          />
                          {reviewState}
                        </span>
                      </td>
                      <td className="flex min-w-0 items-center justify-between gap-4 py-2 text-xs tabular-nums text-[var(--text-tertiary)] min-[1440px]:table-cell min-[1440px]:px-6 min-[1440px]:py-3 min-[1440px]:text-right">
                        <span className="type-label-sm text-[var(--text-tertiary)] min-[1440px]:hidden">
                          Updated
                        </span>
                        <span>
                          {batch.id.startsWith("batch_demo_")
                            ? "Synthetic fixture"
                            : formatRelativeTime(batch.updated_at)}
                        </span>
                      </td>
                      <td className="block min-w-0 py-3 min-[1440px]:table-cell min-[1440px]:px-6 min-[1440px]:py-3 min-[1440px]:text-right">
                        <div className="grid grid-cols-1 gap-2 sm:flex sm:flex-wrap sm:justify-end">
                          {batch.analysis_ids[0] ? (
                            <Button
                              asChild
                              variant="ghost"
                              size="sm"
                              className="min-h-11 w-full sm:w-auto"
                            >
                              <Link
                                href={getReportAccessHrefWithQuery(
                                  batch.analysis_ids[0],
                                  currentUserRole,
                                  riskRatingsRestricted,
                                  {
                                    audience: "diligence",
                                    ai_context: "review_questions",
                                    tab: "claims",
                                  },
                                )}
                              >
                                {fullReportAllowed
                                  ? "Open report"
                                  : "Open summary"}
                              </Link>
                            </Button>
                          ) : null}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="min-h-11 w-full gap-1 sm:w-auto"
                            onClick={() =>
                              onOpenDetails({ id: batch.id, name: batch.name })
                            }
                          >
                            <ChevronDown className="h-3.5 w-3.5" />
                            Details
                          </Button>
                          {batch.status === "running" ||
                          batch.status === "pending" ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              loading={
                                cancelPending && cancelingId === batch.id
                              }
                              className="min-h-11 w-full text-[var(--text-tertiary)] hover:text-error sm:w-auto"
                              disabled={cancelPending || cancelBlocked}
                              onClick={() => setCancelReviewBatch(batch)}
                              aria-label={`Review cancellation impact for ${batch.name}`}
                            >
                              Cancel
                            </Button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {filteredItems.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-6 py-12 text-center text-sm text-[var(--text-secondary)]"
                    >
                      No batch runs match this view.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={cancelReviewBatch !== null}
        onOpenChange={(open) => {
          if (cancelPending) return;
          if (!open) setCancelReviewBatch(null);
        }}
      >
        <DialogContent className="max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-xl gap-3 p-4 sm:max-h-[calc(100dvh-2rem)] sm:w-full sm:gap-4 sm:p-6">
          <DialogHeader>
            <div className="flex items-start gap-3 pr-8 text-left">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-error/20 bg-error/10 text-error">
                <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <DialogTitle>Cancel batch run?</DialogTitle>
                <DialogDescription className="mt-2 leading-5 sm:leading-6">
                  <span className="sm:hidden">
                    Completed results stay visible. Queued or running work may
                    stop.
                  </span>
                  <span className="hidden sm:inline">
                    Review the operational impact before stopping this portfolio
                    run. Completed analysis packets stay visible in the batch
                    ledger; queued or running work may stop before all compounds
                    finish.
                  </span>
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          {cancelReviewBatch ? (
            <div className="space-y-3 sm:space-y-4">
              <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/60 p-3 sm:p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                  Batch under review
                </p>
                <p className="mt-2 max-w-full break-words text-base font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">
                  {cancelReviewBatch.name}
                </p>
                <p className="mt-1 max-w-full break-all font-mono text-xs text-[var(--text-tertiary)]">
                  {cancelReviewBatch.id}
                </p>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <CancelImpactMetric
                  label="Total compounds"
                  mobileLabel="Total"
                  value={cancelReviewBatch.total_compounds.toLocaleString()}
                />
                <CancelImpactMetric
                  label="Finished"
                  value={cancelReviewBatch.completed_count.toLocaleString()}
                />
                <CancelImpactMetric
                  label="Failures"
                  value={cancelReviewBatch.failed_count.toLocaleString()}
                  tone={
                    cancelReviewBatch.failed_count > 0 ? "warning" : "default"
                  }
                />
              </div>

              <div
                role="note"
                className="rounded-lg border border-warning/20 bg-warning/10 px-3 py-2 text-sm leading-5 text-[var(--text-secondary)] sm:px-4 sm:py-3 sm:leading-6"
              >
                <span className="sm:hidden">
                  Cancel only duplicate, incorrect, or superseded runs.
                </span>
                <span className="hidden sm:inline">
                  This action should be used for duplicate, incorrect, or
                  superseded portfolio runs. Start a new batch if the diligence
                  scope changes after cancellation.
                </span>
              </div>
            </div>
          ) : null}

          <DialogFooter className="gap-2 sm:gap-2">
            <Button
              type="button"
              variant="ghost"
              className="min-h-11"
              onClick={() => setCancelReviewBatch(null)}
              disabled={cancelPending}
            >
              Keep running
            </Button>
            <Button
              type="button"
              variant="destructive"
              className="min-h-11"
              loading={cancelPending}
              onClick={handleConfirmCancel}
            >
              Confirm cancellation
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function CancelImpactMetric({
  label,
  mobileLabel,
  value,
  tone = "default",
}: {
  label: string;
  mobileLabel?: string;
  value: string;
  tone?: "default" | "warning";
}) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-lg border bg-[var(--bg-surface)]/72 px-2 py-2 sm:px-3 sm:py-3",
        tone === "warning"
          ? "border-warning/20 text-warning"
          : "border-[var(--border-subtle)] text-[var(--text-primary)]",
      )}
    >
      <p className="break-words text-xs font-semibold uppercase leading-3 tracking-[0.08em] text-[var(--text-tertiary)] sm:text-xs sm:tracking-[0.12em]">
        {mobileLabel ? (
          <>
            <span className="sm:hidden">{mobileLabel}</span>
            <span className="hidden sm:inline">{label}</span>
          </>
        ) : (
          label
        )}
      </p>
      <p className="mt-1 text-base font-semibold tabular-nums sm:text-lg">
        {value}
      </p>
    </div>
  );
}
