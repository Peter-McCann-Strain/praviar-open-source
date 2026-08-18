"use client";

import { useId, useState } from "react";
import {
  AlertTriangle,
  BookOpenCheck,
  CheckCircle2,
  FileCheck2,
  Fingerprint,
  Link2,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ReportReviewCheckpointProps {
  data: Record<string, unknown>;
  onApprove: () => void;
  onReject: () => void;
  isSubmitting?: boolean;
  errorMessage?: string;
}

type UnknownRecord = Record<string, unknown>;

const RISK_STYLES: Record<string, string> = {
  high: "border-error/30 bg-error/10 text-error",
  medium: "border-warning/30 bg-warning/10 text-warning",
  low: "border-brand-primary/25 bg-brand-primary/10 text-brand-primary",
  clear: "border-success/25 bg-success/10 text-success",
};

function asRecord(value: unknown): UnknownRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};
}

function asNonNegativeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0
    ? value
    : null;
}

function validIdentifier(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.trim().length > 0 &&
    Array.from(value.trim()).length <= 256 &&
    !/[\u0000-\u001f]/.test(value)
  );
}

function digestBoundCheckpointId(runId: string, digest: string): string {
  const safeRunId = runId
    .replace(/[^A-Za-z0-9._-]+/g, "_")
    .replace(/^[._-]+|[._-]+$/g, "")
    .slice(0, 64);
  return `${safeRunId || "run"}:report_review:${digest.slice(0, 16)}`;
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-[var(--border-default)] bg-[var(--surface-subtle)] p-3">
      <dt className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
        {value.toLocaleString()}
      </dd>
    </div>
  );
}

export function ReportReviewCheckpoint({
  data,
  onApprove,
  onReject,
  isSubmitting = false,
  errorMessage,
}: ReportReviewCheckpointProps) {
  const attestationId = useId();
  const [attested, setAttested] = useState(false);
  const ledger = asRecord(data.claim_ledger);
  const runId = typeof data.run_id === "string" ? data.run_id.trim() : "";
  const reportId =
    typeof data.report_id === "string" ? data.report_id.trim() : "";
  const checkpointId =
    typeof data.checkpoint_id === "string" ? data.checkpoint_id : "";
  const summary =
    typeof data.executive_summary_excerpt === "string"
      ? data.executive_summary_excerpt.trim()
      : "";
  const risk = typeof data.overall_risk === "string" ? data.overall_risk : "";
  const digest =
    typeof data.review_payload_sha256 === "string"
      ? data.review_payload_sha256
      : "";
  const patentCount = asNonNegativeInteger(data.patent_count);
  const failureCount = asNonNegativeInteger(data.analysis_failure_count);
  const assertionCount = asNonNegativeInteger(ledger.assertion_count);
  const sourceSpanCount = asNonNegativeInteger(ledger.source_span_count);
  const needsReviewCount = asNonNegativeInteger(ledger.needs_review_count);
  const unsupportedCount = asNonNegativeInteger(ledger.unsupported_count);
  const promptHashCount = asNonNegativeInteger(data.prompt_hash_count);
  const attestationKeyIds = Array.isArray(ledger.attestation_key_ids)
    ? ledger.attestation_key_ids.filter(
        (value): value is string =>
          typeof value === "string" && value.length > 0,
      )
    : [];
  const contextValid =
    data.schema_version === "report-review/v1" &&
    validIdentifier(data.run_id) &&
    validIdentifier(data.report_id) &&
    runId.length > 0 &&
    reportId.length > 0 &&
    ["high", "medium", "low", "clear"].includes(risk) &&
    summary.length > 0 &&
    Array.from(summary).length <= 1_200 &&
    typeof data.executive_summary_truncated === "boolean" &&
    /^[a-f0-9]{64}$/.test(digest) &&
    checkpointId === digestBoundCheckpointId(runId, digest) &&
    patentCount !== null &&
    failureCount !== null &&
    assertionCount !== null &&
    sourceSpanCount !== null &&
    needsReviewCount !== null &&
    unsupportedCount === 0 &&
    promptHashCount !== null &&
    promptHashCount > 0 &&
    attestationKeyIds.length === new Set(attestationKeyIds).size;

  return (
    <Card
      className="overflow-hidden border-brand-primary/25 bg-[var(--surface-card)] shadow-[var(--shadow-lg)]"
      data-testid="report-review-checkpoint"
    >
      <CardHeader className="space-y-3 border-b border-[var(--border-subtle)] bg-[var(--surface-glass)] p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-primary/10 text-brand-primary">
            <FileCheck2 className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-primary">
              Integrity-bound report gate
            </p>
            <CardTitle className="mt-1 text-base text-[var(--text-primary)] sm:text-lg">
              Review the bounded report draft
            </CardTitle>
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)] sm:text-sm">
              Final output remains blocked until a reviewer checks this summary
              and its claim-to-source ledger fingerprint.
            </p>
          </div>
          {risk ? (
            <span
              className={cn(
                "shrink-0 rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.1em]",
                RISK_STYLES[risk] ?? RISK_STYLES.medium,
              )}
            >
              {risk} risk
            </span>
          ) : null}
        </div>
        {digest ? (
          <div className="flex min-w-0 items-center gap-2 rounded-md border border-[var(--border-default)] bg-[var(--surface-subtle)] px-3 py-2 text-xs text-[var(--text-secondary)]">
            <Fingerprint
              className="h-4 w-4 shrink-0 text-brand-primary"
              aria-hidden="true"
            />
            <span className="shrink-0 font-semibold">Review payload</span>
            <code className="truncate font-mono" title={digest}>
              SHA-256 {digest.slice(0, 16)}…{digest.slice(-8)}
            </code>
          </div>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-4 p-4 sm:p-5">
        {!contextValid ? (
          <div
            className="flex items-start gap-2 rounded-lg border border-error/30 bg-error/[0.05] p-3 text-xs leading-5 text-error"
            role="alert"
          >
            <ShieldAlert
              className="mt-0.5 h-4 w-4 shrink-0"
              aria-hidden="true"
            />
            The review payload is incomplete or failed integrity validation.
            Approval is unavailable; reject this checkpoint and investigate the
            run.
          </div>
        ) : null}

        {summary ? (
          <section aria-labelledby="report-draft-summary-title">
            <div className="mb-2 flex items-center gap-2">
              <BookOpenCheck
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              <h3
                id="report-draft-summary-title"
                className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]"
              >
                Executive summary excerpt
              </h3>
            </div>
            <blockquote className="max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg border border-[var(--border-default)] bg-[var(--surface-subtle)] p-3 text-sm leading-6 text-[var(--text-primary)]">
              {summary}
            </blockquote>
            {data.executive_summary_truncated === true ? (
              <p className="mt-2 flex items-start gap-1.5 text-xs leading-5 text-warning">
                <AlertTriangle
                  className="mt-0.5 h-3.5 w-3.5 shrink-0"
                  aria-hidden="true"
                />
                The checkpoint intentionally shows a bounded excerpt. The
                fingerprint still binds the complete draft ledger and prompt
                provenance.
              </p>
            ) : null}
          </section>
        ) : null}

        {assertionCount !== null &&
        sourceSpanCount !== null &&
        needsReviewCount !== null &&
        patentCount !== null ? (
          <section aria-labelledby="claim-ledger-title">
            <div className="mb-2 flex items-center gap-2">
              <Link2
                className="h-4 w-4 text-brand-primary"
                aria-hidden="true"
              />
              <h3
                id="claim-ledger-title"
                className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]"
              >
                Claim-to-source ledger
              </h3>
            </div>
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Metric label="Patents" value={patentCount} />
              <Metric label="Assertions" value={assertionCount} />
              <Metric label="Source spans" value={sourceSpanCount} />
              <Metric label="Needs review" value={needsReviewCount} />
            </dl>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--text-tertiary)]">
              <span>{promptHashCount ?? 0} prompt hashes bound</span>
              <span>{attestationKeyIds.length} evidence key IDs bound</span>
              <span>{failureCount ?? 0} analysis failures disclosed</span>
            </div>
          </section>
        ) : null}

        <label
          htmlFor={attestationId}
          className={cn(
            "flex min-h-11 items-start gap-3 rounded-lg border p-3 focus-within:ring-2 focus-within:ring-brand-primary/70 focus-within:ring-offset-2 focus-within:ring-offset-[var(--bg-base)]",
            contextValid
              ? "cursor-pointer border-brand-primary/25 bg-brand-primary/[0.05]"
              : "cursor-not-allowed border-[var(--border-default)] bg-[var(--surface-muted)] opacity-70",
          )}
        >
          <input
            id={attestationId}
            type="checkbox"
            checked={attested}
            onChange={(event) => setAttested(event.target.checked)}
            disabled={!contextValid || isSubmitting}
            className="mt-0.5 h-4 w-4 shrink-0 accent-brand-primary focus-visible:outline-none"
          />
          <span className="text-xs leading-5 text-[var(--text-primary)]">
            I reviewed the visible draft summary, risk, disclosed failures, and
            claim-to-source ledger counts bound to this SHA-256 payload.
          </span>
        </label>

        <div className="grid gap-2 min-[420px]:grid-cols-2">
          <Button
            onClick={onApprove}
            className="min-h-11 w-full gap-2"
            disabled={isSubmitting || !attested || !contextValid}
          >
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            Approve bound report
          </Button>
          <Button
            variant="outline"
            onClick={onReject}
            className="min-h-11 w-full gap-2 border-error/30 text-error hover:bg-error/5"
            disabled={isSubmitting}
          >
            <XCircle className="h-4 w-4" aria-hidden="true" />
            Reject report
          </Button>
        </div>
        {errorMessage ? (
          <p className="text-xs text-error" role="alert">
            {errorMessage}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
