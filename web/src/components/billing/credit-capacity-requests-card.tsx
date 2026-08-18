"use client";

import {
  CheckCircle2,
  Clock3,
  Inbox,
  RefreshCw,
  UserRound,
  XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  type CreditCapacityRequestItem,
  type CreditCapacityRequestStatus,
  useCreditCapacityRequests,
  useResolveCreditCapacityRequest,
} from "@/hooks/use-billing";
import { APIError } from "@/lib/api-client";
import { PROBLEM_TYPES } from "@/lib/problem-types";
import { cn } from "@/lib/utils";
import { useToastStore } from "@/stores/toast-store";

const STATUS_PRESENTATION: Record<
  CreditCapacityRequestStatus,
  {
    icon: typeof Clock3;
    label: string;
    className: string;
  }
> = {
  pending: {
    icon: Clock3,
    label: "Pending",
    className: "border-warning/25 bg-warning/10 text-warning",
  },
  fulfilled: {
    icon: CheckCircle2,
    label: "Capacity verified",
    className: "border-info/25 bg-info/10 text-info",
  },
  declined: {
    icon: XCircle,
    label: "Declined",
    className: "border-danger/25 bg-danger/10 text-danger",
  },
};

const REQUEST_FILTERS: Array<{
  label: string;
  value: "all" | CreditCapacityRequestStatus;
}> = [
  { label: "All", value: "all" },
  { label: "Pending", value: "pending" },
  { label: "Positive resolution", value: "fulfilled" },
  { label: "Declined", value: "declined" },
];

const REQUESTS_PER_PAGE = 10;

function formatRequestTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Time unavailable";
  }
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  }).format(parsed);
}

function requestReference(requestId: string): string {
  return requestId.slice(0, 8).toUpperCase();
}

function requestLabel(count: number): string {
  return `${count.toLocaleString()} Report Credit${count === 1 ? "" : "s"}`;
}

export function CreditCapacityRequestsCard({
  token,
  canResolve,
}: {
  token: string | null;
  canResolve: boolean;
}) {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<
    "all" | CreditCapacityRequestStatus
  >("all");
  const requests = useCreditCapacityRequests(token, {
    page,
    perPage: REQUESTS_PER_PAGE,
    status: statusFilter === "all" ? undefined : statusFilter,
  });
  const pendingRequests = useCreditCapacityRequests(token, {
    page: 1,
    perPage: 1,
    status: "pending",
  });
  const resolveRequest = useResolveCreditCapacityRequest(token);
  const addToast = useToastStore((state) => state.addToast);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [activeResolution, setActiveResolution] = useState<{
    requestId: string;
    status: "fulfilled" | "declined";
  } | null>(null);
  const [pendingDecision, setPendingDecision] = useState<{
    item: CreditCapacityRequestItem;
    status: "fulfilled" | "declined";
  } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const items = requests.data?.items ?? [];
  const pendingCount = pendingRequests.data?.total;
  const total = requests.data?.total ?? 0;
  const totalPages = Math.max(Math.ceil(total / REQUESTS_PER_PAGE), 1);
  const pageOutOfRange = Boolean(requests.data && page > totalPages);
  const effectivePage = Math.min(page, totalPages);
  const pageStart =
    total === 0 ? 0 : (effectivePage - 1) * REQUESTS_PER_PAGE + 1;
  const pageEnd = Math.min(effectivePage * REQUESTS_PER_PAGE, total);
  const activeFilterLabel =
    REQUEST_FILTERS.find((filter) => filter.value === statusFilter)?.label ??
    "Selected";

  useEffect(() => {
    if (!requests.data || page <= totalPages) {
      return undefined;
    }

    const clampTimer = window.setTimeout(() => {
      setPage((current) => Math.min(current, totalPages));
    }, 0);

    return () => window.clearTimeout(clampTimer);
  }, [page, requests.data, totalPages]);

  const handleResolve = async (
    item: CreditCapacityRequestItem,
    status: "fulfilled" | "declined",
  ) => {
    setActionError(null);
    setActiveResolution({ requestId: item.id, status });
    try {
      const resolution = await resolveRequest.mutateAsync({
        requestId: item.id,
        status,
        note: notes[item.id],
      });
      setNotes((current) => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
      if (resolution.resolution_outcome === "already_resolved") {
        addToast(
          status === "fulfilled"
            ? `Request ${requestReference(item.id)} already had a positive resolution. History was refreshed; no duplicate notification was sent.`
            : `Request ${requestReference(item.id)} was already declined. History was refreshed; no duplicate notification was sent.`,
          "info",
        );
      } else {
        addToast(
          status === "fulfilled"
            ? `Current shared capacity verified for request ${requestReference(item.id)}. The requester was notified that capacity is not reserved.`
            : `Request ${requestReference(item.id)} declined. The requester was notified.`,
          "success",
        );
      }
      setPendingDecision(null);
    } catch (error) {
      const problemType =
        error instanceof APIError ? error.telemetry.typeUri : undefined;
      if (problemType === PROBLEM_TYPES.capacityRequestAlreadyResolved) {
        const message = `Another administrator already resolved request ${requestReference(item.id)}. History is refreshing to show the authoritative decision.`;
        setActionError(null);
        setPendingDecision(null);
        addToast(message, "info");
        void Promise.all([requests.refetch(), pendingRequests.refetch()]);
        return;
      }
      const message =
        problemType === PROBLEM_TYPES.insufficientCapacity &&
        status === "fulfilled"
          ? `Current shared capacity no longer covers ${requestLabel(item.requested_reports)}. Add capacity, or decline it and ask the requester to submit a smaller request.`
          : `Request ${requestReference(item.id)} was not changed. Refresh the request list and retry.`;
      setActionError(message);
      addToast(message, "error");
    } finally {
      setActiveResolution(null);
    }
  };

  return (
    <>
      <section
        aria-labelledby="credit-capacity-requests-title"
        className="praviar-surface-premium overflow-hidden rounded-xl"
        data-testid="credit-capacity-requests-card"
      >
        <div className="flex flex-col gap-4 border-b border-[var(--border-subtle)] px-5 py-5 sm:flex-row sm:items-start sm:justify-between sm:px-6">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-primary/10 text-brand-primary">
              <Inbox className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
                Capacity workflow
              </p>
              <h2
                id="credit-capacity-requests-title"
                className="mt-1 text-xl font-semibold text-[var(--text-primary)]"
              >
                Report Credit requests
              </h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                {canResolve
                  ? "Review workspace requests, record a decision, and keep the requester informed without leaving billing."
                  : "Track the durable status and reference for requests you sent to workspace administrators."}
              </p>
            </div>
          </div>
          {pendingCount !== undefined ? (
            <div className="shrink-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-3 py-2 text-right">
              <p className="text-xs text-[var(--text-tertiary)]">Pending</p>
              <p className="text-lg font-semibold text-[var(--text-primary)]">
                {pendingCount.toLocaleString()}
              </p>
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-2 border-b border-[var(--border-subtle)] px-5 py-3 sm:px-6">
          {REQUEST_FILTERS.map((filter) => {
            const active = statusFilter === filter.value;
            return (
              <button
                key={filter.value}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  setStatusFilter(filter.value);
                  setPage(1);
                }}
                className={cn(
                  "min-h-11 min-w-11 rounded-full border px-3 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary/70",
                  active
                    ? "border-brand-primary/30 bg-brand-primary/10 text-brand-primary"
                    : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]",
                )}
              >
                {filter.label}
              </button>
            );
          })}
        </div>

        {requests.isLoading ? (
          <div className="flex items-center gap-3 px-5 py-8 text-sm text-[var(--text-secondary)] sm:px-6">
            <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
            Loading authoritative request history…
          </div>
        ) : requests.error ? (
          <div className="px-5 py-6 sm:px-6">
            <div className="rounded-lg border border-warning/25 bg-warning/10 p-4">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Request history unavailable
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                No request status was inferred from stale data. Retry the
                organization-scoped billing history.
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-4 min-h-11"
                onClick={() => {
                  void requests.refetch();
                }}
              >
                Retry request history
              </Button>
            </div>
          </div>
        ) : pageOutOfRange ? (
          <div
            role="status"
            className="flex items-center gap-3 px-5 py-8 text-sm text-[var(--text-secondary)] sm:px-6"
          >
            <RefreshCw
              className="h-4 w-4 animate-spin motion-reduce:animate-none"
              aria-hidden="true"
            />
            Returning to the last available request page…
          </div>
        ) : items.length === 0 ? (
          <div className="px-5 py-8 sm:px-6">
            <div className="rounded-lg border border-dashed border-[var(--border-default)] bg-[var(--surface-muted)] px-5 py-6 text-center">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {statusFilter === "all"
                  ? "No Report Credit requests yet"
                  : `No ${activeFilterLabel.toLowerCase()} requests`}
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                {statusFilter !== "all"
                  ? "No requests match this filter. Choose All to review other request states."
                  : canResolve
                    ? "New workspace requests will appear here with a durable reference and resolution controls."
                    : "When launch capacity is unavailable, a request sent from the analysis workflow will appear here."}
              </p>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-[var(--border-subtle)]">
            {items.map((item) => {
              const presentation =
                item.status === "fulfilled" &&
                item.fulfillment_credit_ledger_id !== null
                  ? {
                      icon: CheckCircle2,
                      label: "Credits added",
                      className: "border-success/25 bg-success/10 text-success",
                    }
                  : STATUS_PRESENTATION[item.status];
              const StatusIcon = presentation.icon;
              const isPending = item.status === "pending";
              return (
                <article
                  key={item.id}
                  className="grid gap-4 px-5 py-5 sm:px-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={cn(
                          "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold",
                          presentation.className,
                        )}
                      >
                        <StatusIcon
                          className="h-3.5 w-3.5"
                          aria-hidden="true"
                        />
                        {presentation.label}
                      </span>
                      <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-2.5 py-1 font-mono text-xs text-[var(--text-secondary)]">
                        Ref {requestReference(item.id)}
                      </span>
                    </div>
                    <p className="mt-3 text-base font-semibold text-[var(--text-primary)]">
                      {requestLabel(item.requested_reports)}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs leading-5 text-[var(--text-tertiary)]">
                      <span>
                        Requested {formatRequestTime(item.requested_at)} UTC
                      </span>
                      <span>
                        {item.notified_admins.toLocaleString()} administrator
                        {item.notified_admins === 1 ? "" : "s"} notified
                      </span>
                    </div>
                    {canResolve ? (
                      <div className="mt-3 flex min-w-0 items-start gap-2 text-sm text-[var(--text-secondary)]">
                        <UserRound
                          className="mt-0.5 h-4 w-4 shrink-0 text-[var(--text-tertiary)]"
                          aria-hidden="true"
                        />
                        <p className="min-w-0 break-words">
                          <span className="font-medium text-[var(--text-primary)]">
                            {item.requester_name}
                          </span>
                        </p>
                      </div>
                    ) : null}
                    {item.resolution_note ? (
                      <p className="mt-3 rounded-lg bg-[var(--surface-muted)] px-3 py-2 text-sm leading-6 text-[var(--text-secondary)]">
                        {item.resolution_note}
                      </p>
                    ) : null}
                    {item.resolved_at ? (
                      <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                        Resolved {formatRequestTime(item.resolved_at)} UTC by a
                        workspace billing administrator.
                      </p>
                    ) : null}
                    {item.fulfillment_credit_ledger_id ? (
                      <p className="mt-2 text-xs leading-5 text-success">
                        Fulfilled automatically from a confirmed Report Credit
                        ledger purchase.
                      </p>
                    ) : null}
                    {item.status === "fulfilled" &&
                    item.fulfillment_credit_ledger_id === null ? (
                      <p className="mt-2 text-xs leading-5 text-info">
                        An administrator verified shared capacity at resolution
                        time. No credits are reserved; billing checks again when
                        an analysis starts.
                      </p>
                    ) : null}
                  </div>

                  {canResolve && isPending ? (
                    <div className="w-full space-y-3 lg:w-80">
                      <label
                        htmlFor={`credit-request-note-${item.id}`}
                        className="block text-xs font-semibold text-[var(--text-secondary)]"
                      >
                        Resolution note{" "}
                        <span className="font-normal text-[var(--text-tertiary)]">
                          (required to decline)
                        </span>
                      </label>
                      <Textarea
                        id={`credit-request-note-${item.id}`}
                        value={notes[item.id] ?? ""}
                        maxLength={1000}
                        rows={4}
                        aria-describedby={`credit-request-note-help-${item.id} credit-request-note-count-${item.id}`}
                        className="min-h-28 resize-y"
                        placeholder="Context for the requester"
                        onChange={(event) => {
                          setNotes((current) => ({
                            ...current,
                            [item.id]: event.target.value,
                          }));
                        }}
                      />
                      <div className="flex items-start justify-between gap-3 text-xs leading-5 text-[var(--text-tertiary)]">
                        <p id={`credit-request-note-help-${item.id}`}>
                          Add enough context for the requester to understand the
                          decision.
                        </p>
                        <span
                          id={`credit-request-note-count-${item.id}`}
                          className="shrink-0 tabular-nums"
                        >
                          {(notes[item.id]?.length ?? 0).toLocaleString()}/1,000
                        </span>
                      </div>
                      <p className="text-xs leading-5 text-[var(--text-tertiary)]">
                        Praviar verifies current shared workspace capacity. This
                        does not reserve credits; every launch checks capacity
                        again.
                      </p>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <Button
                          type="button"
                          size="sm"
                          className="min-h-11"
                          disabled={Boolean(activeResolution)}
                          onClick={() => {
                            setActionError(null);
                            setPendingDecision({
                              item,
                              status: "fulfilled",
                            });
                          }}
                        >
                          Verify capacity
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="min-h-11"
                          disabled={
                            Boolean(activeResolution) ||
                            (notes[item.id]?.trim().length ?? 0) < 4
                          }
                          aria-describedby={`credit-request-note-${item.id}`}
                          onClick={() => {
                            setActionError(null);
                            setPendingDecision({
                              item,
                              status: "declined",
                            });
                          }}
                        >
                          Decline
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}

        {requests.data && total > 0 ? (
          <div className="flex flex-col gap-3 border-t border-[var(--border-subtle)] px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p className="text-xs text-[var(--text-tertiary)]">
              Showing {pageStart.toLocaleString()}–{pageEnd.toLocaleString()} of{" "}
              {total.toLocaleString()}{" "}
              {statusFilter === "all"
                ? ""
                : `${activeFilterLabel.toLowerCase()} `}{" "}
              request{total === 1 ? "" : "s"}
            </p>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="min-h-11"
                disabled={page <= 1}
                onClick={() => {
                  setPage((current) => Math.max(current - 1, 1));
                }}
              >
                Previous
              </Button>
              <span className="min-w-16 text-center text-xs text-[var(--text-secondary)]">
                {effectivePage} / {totalPages}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="min-h-11"
                disabled={page >= totalPages}
                onClick={() => {
                  setPage((current) => Math.min(current + 1, totalPages));
                }}
              >
                Next
              </Button>
            </div>
          </div>
        ) : null}

        {actionError ? (
          <div
            role="alert"
            className="border-t border-danger/20 bg-danger/10 px-5 py-3 text-sm text-danger sm:px-6"
          >
            {actionError}
          </div>
        ) : null}
      </section>

      <Dialog
        open={pendingDecision !== null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !resolveRequest.isPending) {
            setPendingDecision(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {pendingDecision?.status === "declined"
                ? "Decline Report Credit request?"
                : "Verify current capacity?"}
            </DialogTitle>
            <DialogDescription className="leading-6">
              {pendingDecision?.status === "declined"
                ? `Request ${pendingDecision ? requestReference(pendingDecision.item.id) : ""} will be declined and the requester will receive the resolution note.`
                : `Praviar will check current shared workspace capacity for request ${pendingDecision ? requestReference(pendingDecision.item.id) : ""}. This does not reserve credits; every launch rechecks capacity.`}
            </DialogDescription>
          </DialogHeader>
          {pendingDecision ? (
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)] px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]">
              <p className="font-semibold text-[var(--text-primary)]">
                {requestLabel(pendingDecision.item.requested_reports)}
              </p>
              <p className="mt-1">
                {notes[pendingDecision.item.id]?.trim() ||
                  "No optional verification note supplied."}
              </p>
            </div>
          ) : null}
          {actionError ? (
            <div
              role="alert"
              className="rounded-lg border border-danger/25 bg-danger/10 px-4 py-3 text-sm leading-6 text-danger"
            >
              {actionError}
            </div>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={resolveRequest.isPending}
              onClick={() => {
                setPendingDecision(null);
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant={
                pendingDecision?.status === "declined"
                  ? "destructive"
                  : "default"
              }
              loading={resolveRequest.isPending}
              disabled={!pendingDecision}
              onClick={() => {
                if (pendingDecision) {
                  void handleResolve(
                    pendingDecision.item,
                    pendingDecision.status,
                  );
                }
              }}
            >
              {pendingDecision?.status === "declined"
                ? "Confirm decline"
                : "Verify current capacity"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
