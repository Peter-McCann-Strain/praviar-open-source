"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Scale,
  ShieldCheck,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  useUpdateAnalysisReviewStatus,
  type AnalysisReviewStatusResponse,
  type AnalysisReviewStatusValue,
} from "@/hooks/use-analysis-review-status";
import { APIError } from "@/lib/api-client";
import { formatDate } from "@/lib/utils";

type MutableReviewStatus = Exclude<AnalysisReviewStatusValue, "pending">;

interface ReportReviewLifecycleControlProps {
  analysisId: string;
  status?: AnalysisReviewStatusResponse;
  statusError?: boolean;
  statusLoading?: boolean;
  onRefresh: () => Promise<unknown> | unknown;
}

const STATUS_OPTIONS: Array<{
  value: MutableReviewStatus;
  label: string;
  consequence: string;
}> = [
  {
    value: "under_review",
    label: "Under review",
    consequence:
      "Opens or resumes governed counsel review. Export remains blocked until approval and every backend readiness gate passes.",
  },
  {
    value: "changes_requested",
    label: "Changes requested",
    consequence:
      "Records that counsel requires further evidence or corrections. The analysis stays flagged and governed export remains blocked.",
  },
  {
    value: "approved",
    label: "Approved",
    consequence:
      "Records counsel approval only if finding coverage and backend readiness gates pass. Source caveats remain attached and approval is not a legal opinion.",
  },
];

export function ReportReviewLifecycleControl({
  analysisId,
  status,
  statusError = false,
  statusLoading = false,
  onRefresh,
}: ReportReviewLifecycleControlProps) {
  const updateStatus = useUpdateAnalysisReviewStatus(analysisId);
  const [selectedStatusOverride, setSelectedStatusOverride] =
    useState<MutableReviewStatus | null>(null);
  const [note, setNote] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [refreshWarning, setRefreshWarning] = useState<string | null>(null);
  const selectedStatus =
    selectedStatusOverride ?? getMutableStatus(status?.status);

  const refreshStatus = async () => {
    setRefreshWarning(null);
    try {
      await onRefresh();
    } catch {
      setRefreshWarning(
        "The authoritative review status could not be refreshed. Keep export approval unconfirmed and retry.",
      );
    }
  };

  const submitStatus = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const auditNote = note.trim();
    if (!auditNote || updateStatus.isPending) return;

    if (updateStatus.error) updateStatus.reset();
    setSuccessMessage(null);
    setRefreshWarning(null);

    try {
      const updated = await updateStatus.mutateAsync({
        status: selectedStatus,
        note: auditNote,
      });
      setNote("");
      setSelectedStatusOverride(null);
      setSuccessMessage(
        `${formatStatusLabel(updated.status)} recorded in the governed review ledger.`,
      );

      try {
        await onRefresh();
      } catch {
        setRefreshWarning(
          "The decision was saved, but the live status refresh did not complete. Refresh the authoritative status before exporting.",
        );
      }
    } catch {
      // The mutation exposes a sanitized, status-aware error below.
    }
  };

  if (statusLoading && !status) {
    return (
      <section
        aria-label="Governed counsel review lifecycle"
        className="rounded-lg border border-[var(--border-emphasis)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-sm)] sm:p-5"
        data-no-print
      >
        <div className="flex items-center gap-3" role="status">
          <RefreshCw
            className="h-4 w-4 animate-spin text-brand-primary motion-reduce:animate-none"
            aria-hidden="true"
          />
          <div>
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              Loading authoritative review status
            </p>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              Legal lifecycle controls remain closed until the persisted record
              is confirmed.
            </p>
          </div>
        </div>
      </section>
    );
  }

  if (statusError || !status) {
    return (
      <section
        aria-labelledby="report-review-lifecycle-unavailable-title"
        className="rounded-lg border border-error/30 bg-error/5 p-4 shadow-[var(--shadow-sm)] sm:p-5"
        data-no-print
      >
        <div className="flex items-start gap-3">
          <AlertTriangle
            className="mt-0.5 h-5 w-5 flex-none text-error"
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1">
            <h2
              id="report-review-lifecycle-unavailable-title"
              className="text-sm font-semibold text-[var(--text-primary)]"
            >
              Governed review status unavailable
            </h2>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              No legal lifecycle change can be recorded while the authoritative
              status is unavailable. Export approval must remain unconfirmed.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => void refreshStatus()}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
              Retry status
            </Button>
            {refreshWarning ? (
              <p className="mt-3 text-xs leading-5 text-error" role="alert">
                {refreshWarning}
              </p>
            ) : null}
          </div>
        </div>
      </section>
    );
  }

  const currentOption = STATUS_OPTIONS.find(
    (option) => option.value === selectedStatus,
  );
  const mutationError = getMutationErrorMessage(updateStatus.error);
  const reviewer =
    status.reviewer_name?.trim() || status.reviewer_email?.trim() || null;

  return (
    <section
      aria-labelledby="report-review-lifecycle-title"
      className="overflow-hidden rounded-lg border border-[var(--border-emphasis)] bg-[var(--bg-surface)] shadow-[var(--shadow-sm)]"
      data-no-print
      data-testid="report-review-lifecycle-control"
    >
      <div className="border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/45 p-4 sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span className="rounded-lg border border-brand-primary/20 bg-brand-primary/10 p-2 text-brand-primary">
              <Scale className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
                Authoritative legal lifecycle
              </p>
              <h2
                id="report-review-lifecycle-title"
                className="mt-1 text-lg font-semibold text-[var(--text-primary)]"
              >
                Counsel review decision
              </h2>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
                This report-level decision governs export eligibility. Finding
                decisions remain in the claim and patent review ledger.
              </p>
            </div>
          </div>
          <Badge variant={getStatusBadgeVariant(status.status)}>
            {formatStatusLabel(status.status)}
          </Badge>
        </div>

        <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-3">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3">
            <dt className="text-[var(--text-tertiary)]">Finding coverage</dt>
            <dd className="mt-1 font-semibold text-[var(--text-primary)]">
              {status.findings_reviewed.toLocaleString()} /{" "}
              {status.findings_total.toLocaleString()} reviewed
            </dd>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3">
            <dt className="text-[var(--text-tertiary)]">Recorded by</dt>
            <dd className="mt-1 truncate font-semibold text-[var(--text-primary)]">
              {reviewer ?? "No final reviewer recorded"}
            </dd>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3">
            <dt className="text-[var(--text-tertiary)]">Last updated</dt>
            <dd className="mt-1 font-semibold text-[var(--text-primary)]">
              {formatDate(status.updated_at)}
            </dd>
          </div>
        </dl>
      </div>

      <form
        className="space-y-4 p-4 sm:p-5"
        onSubmit={submitStatus}
        aria-busy={updateStatus.isPending}
        aria-labelledby="report-review-lifecycle-title"
      >
        <fieldset disabled={updateStatus.isPending}>
          <legend className="text-sm font-semibold text-[var(--text-primary)]">
            Record the report lifecycle state
          </legend>
          <div className="mt-3 grid gap-2 lg:grid-cols-3">
            {STATUS_OPTIONS.map((option) => {
              const selected = selectedStatus === option.value;
              return (
                <label
                  key={option.value}
                  className={`cursor-pointer rounded-lg border p-3 transition-colors ${
                    selected
                      ? "border-brand-primary/50 bg-brand-primary/10"
                      : "border-[var(--border-subtle)] bg-[var(--surface-muted)]/25 hover:border-[var(--border-emphasis)]"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="report-review-status"
                      value={option.value}
                      checked={selected}
                      onChange={() => {
                        if (updateStatus.error) updateStatus.reset();
                        setSelectedStatusOverride(option.value);
                        setSuccessMessage(null);
                        setRefreshWarning(null);
                      }}
                      className="h-4 w-4 accent-[var(--brand-primary)]"
                    />
                    <span className="text-sm font-semibold text-[var(--text-primary)]">
                      {option.label}
                    </span>
                  </span>
                  <span className="mt-2 block text-xs leading-5 text-[var(--text-secondary)]">
                    {option.consequence}
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <div>
          <label
            htmlFor="report-review-lifecycle-note"
            className="text-sm font-semibold text-[var(--text-primary)]"
          >
            Audit note
          </label>
          <p
            id="report-review-lifecycle-note-help"
            className="mt-1 text-xs leading-5 text-[var(--text-secondary)]"
          >
            State the evidence reviewed, unresolved caveats, and why this
            transition is appropriate. The note is persisted with the reviewer
            identity.
          </p>
          <Textarea
            id="report-review-lifecycle-note"
            aria-describedby="report-review-lifecycle-note-help"
            className="mt-2 min-h-24"
            maxLength={4000}
            value={note}
            onChange={(event) => {
              if (updateStatus.error) updateStatus.reset();
              setNote(event.target.value);
              setSuccessMessage(null);
              setRefreshWarning(null);
            }}
            placeholder="Example: Reviewed all material claim mappings; source caveats remain attached to the packet."
            disabled={updateStatus.isPending}
          />
          <p className="mt-1 text-right text-xs tabular-nums text-[var(--text-tertiary)]">
            {note.length.toLocaleString()} / 4,000
          </p>
        </div>

        {currentOption ? (
          <div
            className="rounded-md border border-warning/25 bg-warning/10 p-3 text-xs leading-5 text-[var(--text-secondary)]"
            role="note"
          >
            <span className="font-semibold text-warning">
              Consequence before saving:
            </span>{" "}
            {currentOption.consequence}
          </div>
        ) : null}

        {mutationError ? (
          <p
            className="rounded-md border border-error/25 bg-error/5 p-3 text-xs leading-5 text-error"
            role="alert"
          >
            {mutationError}
          </p>
        ) : null}
        {successMessage ? (
          <p
            className="flex items-start gap-2 rounded-md border border-success/25 bg-success/5 p-3 text-xs leading-5 text-success"
            role="status"
            aria-live="polite"
          >
            <CheckCircle2
              className="mt-0.5 h-4 w-4 flex-none"
              aria-hidden="true"
            />
            {successMessage}
          </p>
        ) : null}
        {refreshWarning ? (
          <p
            className="rounded-md border border-warning/25 bg-warning/10 p-3 text-xs leading-5 text-warning"
            role="alert"
          >
            {refreshWarning}
          </p>
        ) : null}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="min-h-11"
            onClick={() => void refreshStatus()}
            disabled={updateStatus.isPending}
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Refresh status
          </Button>
          <Button
            type="submit"
            className="min-h-11"
            loading={updateStatus.isPending}
            disabled={!note.trim()}
          >
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            {updateStatus.isPending
              ? "Recording decision"
              : `Record ${formatStatusLabel(selectedStatus).toLowerCase()}`}
          </Button>
        </div>
      </form>
    </section>
  );
}

function getMutableStatus(
  status: AnalysisReviewStatusValue | null | undefined,
): MutableReviewStatus {
  return status === "approved" || status === "changes_requested"
    ? status
    : "under_review";
}

function formatStatusLabel(
  status: AnalysisReviewStatusValue | null | undefined,
): string {
  if (!status) return "Status unavailable";
  return status
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function getStatusBadgeVariant(
  status: AnalysisReviewStatusValue,
): "secondary" | "warning" | "success" | "destructive" {
  if (status === "approved") return "success";
  if (status === "changes_requested") return "destructive";
  if (status === "under_review") return "warning";
  return "secondary";
}

function getMutationErrorMessage(error: unknown): string | null {
  if (!error) return null;
  if (error instanceof APIError) {
    if (error.status === 403) {
      return "Your legal-review authority changed before the decision was saved. Refresh workspace permissions; no lifecycle change was recorded.";
    }
    if (error.status === 409) {
      return "The lifecycle decision was not recorded because one or more governed readiness gates still fail. Review finding coverage and export blockers, then retry.";
    }
  }
  return "The lifecycle decision could not be recorded. The previous authoritative status remains in force; refresh and retry.";
}
