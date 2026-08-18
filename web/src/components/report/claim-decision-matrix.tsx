"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  FileSearch2,
  Scale,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RiskBadge } from "@/components/shared/risk-badge";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";
import { motionAwareScrollBehavior } from "@/lib/motion-preferences";
import type { FTOReport } from "@praviar/shared-types";
import {
  buildClaimDecisionMatrixModel,
  filterClaimDecisionRows,
  type ClaimDecisionFilter,
  type ClaimDecisionMatrixRow,
} from "./claim-decision-matrix-model";

interface ClaimDecisionMatrixProps {
  decisionsLoading?: boolean;
  decisionsUnavailable?: boolean;
  focusedClaimNumber?: number | null;
  focusedPatentId?: string | null;
  onReviewFinding?: (assertionId: string) => void;
  report: FTOReport;
  reviewerDecisions?: ReviewerDecisionListResponse | null;
}

const FILTERS: ReadonlyArray<{ id: ClaimDecisionFilter; label: string }> = [
  { id: "needs_action", label: "Needs action" },
  { id: "all", label: "All elements" },
  { id: "met_partial", label: "Met / partial" },
  { id: "not_met", label: "Not met" },
  { id: "unclear", label: "Unclear" },
];

const LITERAL_LABELS: Record<string, string> = {
  met: "Met",
  not_met: "Not met",
  partially_met: "Partially met",
  unclear: "Unclear",
};

const DOE_LABELS: Record<ClaimDecisionMatrixRow["doeStatus"], string> = {
  equivalent: "Equivalent",
  not_equivalent: "Not equivalent",
  unclear: "Unclear",
  not_assessed: "Not assessed",
};

const TRUSTED_CLAIM_ARTIFACT_HOSTS = new Set([
  "console.cloud.google.com",
  "ops.epo.org",
  "search.patentsview.org",
]);

function formatDate(value: string | null) {
  if (!value) return "Not reported";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("en", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(date);
}

function getSourceLabel(row: ClaimDecisionMatrixRow) {
  if (row.verifiedSpans.length === 0) {
    return "Verified claim-text span not available";
  }
  return `${row.verifiedSpans.length} complete provenance receipt${row.verifiedSpans.length === 1 ? "" : "s"}`;
}

function getMappingLabel(row: ClaimDecisionMatrixRow) {
  switch (row.mappingSupport) {
    case "supported":
      return "Mapping supported";
    case "needs_review":
      return "Mapping needs review";
    case "unsupported":
      return "Mapping unsupported";
    default:
      return "Mapping support not reported";
  }
}

function getReviewVariant(row: ClaimDecisionMatrixRow) {
  if (row.reviewSummary.state === "conflict") return "destructive" as const;
  if (["accepted", "edited"].includes(row.reviewSummary.state)) {
    return "success" as const;
  }
  if (row.reviewSummary.state === "rejected") return "destructive" as const;
  if (["pending", "unknown"].includes(row.reviewSummary.state)) {
    return "warning" as const;
  }
  return "secondary" as const;
}

function getHumanReviewLabel(row: ClaimDecisionMatrixRow) {
  const { reviewCount, state } = row.reviewSummary;
  if (["accepted", "edited", "rejected"].includes(state)) {
    return `AI mapping reviewed — ${state} by ${reviewCount} reviewer${reviewCount === 1 ? "" : "s"}`;
  }
  return row.reviewSummary.label;
}

function getSafeArtifactHref(value: string | undefined) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" &&
      TRUSTED_CLAIM_ARTIFACT_HOSTS.has(url.hostname)
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

function VerifiedClaimSource({
  row,
  span,
}: {
  row: ClaimDecisionMatrixRow;
  span: ClaimDecisionMatrixRow["verifiedSpans"][number];
}) {
  const artifactHref = getSafeArtifactHref(span.source_artifact_locator);

  return (
    <article
      className="rounded-md border border-brand-primary/20 bg-[var(--bg-surface)] p-3"
      data-testid={`claim-exact-source-${span.span_id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-primary">
            Exact source fact
          </p>
          <p className="mt-1 font-mono text-xs text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
            {span.citation ||
              `${row.patentId} · claim ${row.claimNumber} · element ${row.elementNumber}`}
          </p>
        </div>
        <Badge variant="success">Receipt verified</Badge>
      </div>

      <blockquote className="mt-3 border-l-2 border-brand-primary/50 pl-3 text-sm leading-6 text-[var(--text-primary)]">
        {span.excerpt || "Verified span excerpt not included."}
      </blockquote>

      <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
        <div>
          <dt className="text-[var(--text-tertiary)]">Authority source</dt>
          <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
            {span.source_name}
          </dd>
        </div>
        <div>
          <dt className="text-[var(--text-tertiary)]">Retrieved</dt>
          <dd className="mt-0.5 text-[var(--text-primary)]">
            {formatDate(span.source_retrieved_at ?? null)}
          </dd>
        </div>
      </dl>

      {artifactHref ? (
        <Button
          asChild
          size="sm"
          variant="outline"
          className="mt-3 min-h-11 w-full"
        >
          <a
            href={artifactHref}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={`claim-exact-source-link-${span.span_id}`}
          >
            Open exact source
          </a>
        </Button>
      ) : (
        <p className="mt-3 rounded-md border border-warning/25 bg-warning/10 p-2 text-xs leading-5 text-warning">
          Exact-source link is unavailable; rely on this receipt only after
          resolving the governed artifact location.
        </p>
      )}

      <details className="mt-2 text-xs">
        <summary className="min-h-11 cursor-pointer py-3 font-semibold text-[var(--text-secondary)]">
          Inspect provenance receipt
        </summary>
        <dl className="space-y-2 border-t border-[var(--border-subtle)] pt-3 text-xs">
          <div>
            <dt className="text-[var(--text-tertiary)]">Source document</dt>
            <dd className="mt-0.5 font-mono text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {span.source_document_id}
            </dd>
          </div>
          <div>
            <dt className="text-[var(--text-tertiary)]">Collector</dt>
            <dd className="mt-0.5 text-[var(--text-primary)]">
              {span.collector_identity} · {span.collector_version}
            </dd>
          </div>
          <div className="break-all font-mono text-xs text-[var(--text-tertiary)]">
            <dt>Source SHA-256</dt>
            <dd>{span.source_text_sha256}</dd>
          </div>
          <div className="break-all font-mono text-xs text-[var(--text-tertiary)]">
            <dt>Cassette SHA-256</dt>
            <dd>{span.provenance_cassette_sha256}</dd>
          </div>
        </dl>
      </details>
    </article>
  );
}

export function ClaimDecisionMatrix({
  decisionsLoading = false,
  decisionsUnavailable = false,
  focusedClaimNumber,
  focusedPatentId,
  onReviewFinding,
  report,
  reviewerDecisions,
}: ClaimDecisionMatrixProps) {
  const matrixRef = useRef<HTMLElement>(null);
  const model = useMemo(
    () =>
      buildClaimDecisionMatrixModel({
        decisionsLoading,
        decisionsUnavailable,
        report,
        reviewerDecisions,
      }),
    [decisionsLoading, decisionsUnavailable, report, reviewerDecisions],
  );
  const [filter, setFilter] = useState<ClaimDecisionFilter>(() =>
    model.needsActionCount > 0 ? "needs_action" : "all",
  );
  const hasFocusedClaim = Boolean(
    focusedPatentId && focusedClaimNumber != null,
  );
  const activeFilter =
    hasFocusedClaim ||
    (filter === "needs_action" && model.needsActionCount === 0)
      ? "all"
      : filter;
  const rows = useMemo(
    () => filterClaimDecisionRows(model.rows, activeFilter),
    [activeFilter, model.rows],
  );
  const familyCount = useMemo(
    () =>
      new Set(model.rows.map((row) => row.familyId ?? `patent:${row.patentId}`))
        .size,
    [model.rows],
  );
  const claimCount = useMemo(
    () =>
      new Set(
        model.rows.map((row) => `${row.patentId}:claim-${row.claimNumber}`),
      ).size,
    [model.rows],
  );

  useEffect(() => {
    if (!focusedPatentId || focusedClaimNumber == null) return;
    const frame = window.requestAnimationFrame(() => {
      const target = Array.from(
        matrixRef.current?.querySelectorAll<HTMLElement>(
          "[data-claim-coordinate]",
        ) ?? [],
      ).find(
        (row) =>
          row.dataset.patentId === focusedPatentId &&
          row.dataset.claimNumber === String(focusedClaimNumber),
      );
      if (!target) return;
      const disclosure = target.querySelector<HTMLDetailsElement>("details");
      if (disclosure) disclosure.open = true;
      target.focus({ preventScroll: true });
      target.scrollIntoView({
        behavior: motionAwareScrollBehavior(),
        block: "center",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [focusedClaimNumber, focusedPatentId]);

  if (model.total === 0) return null;

  return (
    <section
      ref={matrixRef}
      aria-labelledby="claim-evidence-review-title"
      className="overflow-hidden rounded-lg border border-[var(--border-emphasis)] bg-[var(--bg-surface)] shadow-[var(--shadow-sm)]"
      data-testid="claim-decision-matrix"
    >
      <header className="border-b border-[var(--border-subtle)] bg-[var(--surface-muted)]/45 p-4 sm:p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-primary">
              Claim evidence review queue
            </p>
            <h2
              id="claim-evidence-review-title"
              className="mt-1 text-xl font-semibold text-[var(--text-primary)]"
            >
              Family × claim source-review matrix
            </h2>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
              Each exact family, patent, claim, and element coordinate keeps
              authority text, AI-assisted inference, and the human decision in
              separate synchronized columns.
            </p>
            <p className="mt-2 text-xs font-medium leading-5 text-brand-primary">
              Synthetic research preview; not a legal clearance opinion.
            </p>
          </div>
          <dl
            className="grid grid-cols-2 gap-2 sm:grid-cols-4"
            aria-label="Claim review queue summary"
          >
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 text-center">
              <dt className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                Families
              </dt>
              <dd className="mt-1 text-lg font-semibold tabular-nums">
                {familyCount}
              </dd>
            </div>
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 text-center">
              <dt className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                Claims
              </dt>
              <dd className="mt-1 text-lg font-semibold tabular-nums">
                {claimCount}
              </dd>
            </div>
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 text-center">
              <dt className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                Elements
              </dt>
              <dd className="mt-1 text-lg font-semibold tabular-nums">
                {model.total}
              </dd>
            </div>
            <div className="rounded-md border border-warning/25 bg-warning/10 p-3 text-center">
              <dt className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                Action
              </dt>
              <dd className="mt-1 tabular-nums">
                <span className="block text-lg font-semibold">
                  {model.needsActionCount}
                </span>
                <span className="block text-xs text-[var(--text-tertiary)]">
                  {model.conflictCount} conflict
                  {model.conflictCount === 1 ? "" : "s"}
                </span>
              </dd>
            </div>
          </dl>
        </div>

        <div
          className="mt-4 flex flex-wrap gap-2"
          role="group"
          aria-label="Filter claim elements"
        >
          {FILTERS.map((option) => (
            <Button
              key={option.id}
              type="button"
              size="sm"
              variant={activeFilter === option.id ? "default" : "outline"}
              className="min-h-11"
              aria-pressed={activeFilter === option.id}
              disabled={
                option.id === "needs_action" && model.needsActionCount === 0
              }
              onClick={() => setFilter(option.id)}
            >
              {option.label}
              {option.id === "needs_action"
                ? ` (${model.needsActionCount})`
                : ""}
            </Button>
          ))}
        </div>
      </header>

      <p
        className="border-b border-[var(--border-subtle)] px-4 py-3 text-xs leading-5 text-[var(--text-secondary)] sm:px-5"
        role="status"
        aria-live="polite"
      >
        Showing {rows.length.toLocaleString()} of {model.total.toLocaleString()}{" "}
        exact element records. Missing verified claim-text receipts, review
        conflicts, and pending review sort first.
        <span className="mt-1 block xl:hidden">
          Mobile focus mode shows one exact element at a time; use the desktop
          matrix when cross-family comparison is required.
        </span>
      </p>

      {rows.length === 0 ? (
        <div className="p-8 text-center">
          <CheckCircle2
            className="mx-auto h-6 w-6 text-success"
            aria-hidden="true"
          />
          <p className="mt-2 font-semibold text-[var(--text-primary)]">
            No elements match this filter
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Choose another view to inspect the complete claim record.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-[var(--border-subtle)]">
          {rows.map((row) => (
            <li
              key={row.id}
              aria-labelledby={`claim-review-label-${row.id}`}
              data-claim-coordinate={row.id}
              data-claim-number={row.claimNumber}
              data-patent-id={row.patentId}
              data-testid={`claim-decision-row-${row.id}`}
              tabIndex={-1}
              className={
                row.patentId === focusedPatentId &&
                row.claimNumber === focusedClaimNumber
                  ? "p-0 outline-none ring-2 ring-inset ring-brand-primary/70"
                  : "p-0 outline-none"
              }
            >
              <details
                className="group"
                open={
                  row.needsAction ||
                  (row.patentId === focusedPatentId &&
                    row.claimNumber === focusedClaimNumber) ||
                  undefined
                }
              >
                <summary className="flex min-h-11 cursor-pointer list-none items-start justify-between gap-3 p-4 marker:content-none sm:p-5 [&::-webkit-details-marker]:hidden">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <RiskBadge risk={row.riskLevel} size="sm" />
                      <Badge
                        variant="secondary"
                        className="max-w-full whitespace-normal break-all"
                      >
                        Family {row.familyId || "not reported"}
                      </Badge>
                      <span className="font-mono text-xs font-semibold text-[var(--text-primary)]">
                        {row.patentId}
                      </span>
                      <Badge variant="secondary">
                        Claim {row.claimNumber} · Element {row.elementNumber}
                      </Badge>
                    </div>
                    <p
                      id={`claim-review-label-${row.id}`}
                      className="mt-2 text-sm font-semibold leading-6 text-[var(--text-primary)]"
                    >
                      {row.elementText}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)] [overflow-wrap:anywhere]">
                      {row.patentTitle}
                    </p>
                  </div>
                  <ChevronDown
                    className="mt-1 h-4 w-4 shrink-0 text-brand-primary transition-transform group-open:rotate-180"
                    aria-hidden="true"
                  />
                </summary>

                <div
                  className="grid gap-4 px-4 pb-4 sm:px-5 sm:pb-5 xl:grid-cols-3"
                  data-print-claim-layers
                >
                  <section
                    aria-label={`Source fact for ${row.patentId}, claim ${row.claimNumber}, element ${row.elementNumber}`}
                    className="min-w-0 rounded-md border border-brand-primary/20 bg-[var(--surface-muted)]/35 p-3"
                  >
                    <div className="hidden" data-print-claim-coordinate-header>
                      <p className="font-mono text-[8pt] font-semibold text-[var(--text-primary)]">
                        {row.patentId} · Claim {row.claimNumber} · Element{" "}
                        {row.elementNumber}
                      </p>
                      <p className="mt-1 text-[8pt] leading-4 text-[var(--text-secondary)]">
                        {row.elementText}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <FileSearch2
                        className="h-4 w-4 text-brand-primary"
                        aria-hidden="true"
                      />
                      <h3
                        id={`claim-source-fact-${row.id}`}
                        className="text-xs font-semibold uppercase tracking-wide text-[var(--text-primary)]"
                      >
                        1 · Source fact
                      </h3>
                    </div>
                    <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
                      {getSourceLabel(row)}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                      Authority wording only. This does not establish product
                      mapping, infringement, validity, or clearance.
                    </p>
                    {row.verifiedSpans.length > 0 ? (
                      <div className="mt-3 space-y-3">
                        {row.verifiedSpans.map((span) => (
                          <VerifiedClaimSource
                            key={span.span_id}
                            row={row}
                            span={span}
                          />
                        ))}
                      </div>
                    ) : (
                      <p className="mt-3 flex items-start gap-2 rounded-md border border-warning/25 bg-warning/10 p-3 text-xs leading-5 text-warning">
                        <AlertTriangle
                          className="mt-0.5 h-4 w-4 shrink-0"
                          aria-hidden="true"
                        />
                        Verified authority text is missing. Do not substitute
                        structural or reasoning spans as source proof.
                      </p>
                    )}
                    {row.contextSpans.length > 0 ? (
                      <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                        {row.contextSpans.length} analytical context span
                        {row.contextSpans.length === 1 ? "" : "s"} retained
                        separately and excluded from authority proof.
                      </p>
                    ) : null}
                  </section>

                  <section
                    aria-label={`AI-assisted inference for ${row.patentId}, claim ${row.claimNumber}, element ${row.elementNumber}`}
                    className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3"
                  >
                    <h3
                      id={`claim-ai-inference-${row.id}`}
                      className="text-xs font-semibold uppercase tracking-wide text-[var(--text-primary)]"
                    >
                      2 · AI-assisted inference
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                      Generated analysis for review; never authority text or a
                      human legal decision.
                    </p>
                    <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3">
                      <div>
                        <dt className="text-[var(--text-tertiary)]">Literal</dt>
                        <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
                          {LITERAL_LABELS[row.literalStatus] ??
                            row.literalStatus}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[var(--text-tertiary)]">
                          Doctrine of equivalents
                        </dt>
                        <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
                          {DOE_LABELS[row.doeStatus]}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[var(--text-tertiary)]">
                          Mapping ledger
                        </dt>
                        <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
                          {getMappingLabel(row)}
                        </dd>
                      </div>
                    </dl>
                    <div
                      className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 p-3"
                      role="group"
                      aria-label={`Feature evidence map for claim ${row.claimNumber} element ${row.elementNumber}`}
                    >
                      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--text-primary)]">
                        Feature evidence map
                      </p>
                      <dl className="mt-2 grid gap-2 text-xs sm:grid-cols-2">
                        <div>
                          <dt className="text-[var(--text-tertiary)]">
                            Claim language
                          </dt>
                          <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
                            {row.verifiedSpans.length > 0
                              ? "Authority text captured"
                              : "Authority text missing"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-[var(--text-tertiary)]">
                            Product evidence
                          </dt>
                          <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
                            {row.mappingEvidence
                              ? "Product evidence cited"
                              : "Product evidence missing"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-[var(--text-tertiary)]">
                            Mapping ledger
                          </dt>
                          <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
                            {getMappingLabel(row)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-[var(--text-tertiary)]">
                            Reviewer decision
                          </dt>
                          <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
                            {row.reviewSummary.label}
                          </dd>
                        </div>
                      </dl>
                    </div>
                    <details className="mt-2 text-xs">
                      <summary className="min-h-11 cursor-pointer py-3 font-semibold text-brand-primary">
                        Inspect AI mapping rationale and product evidence
                      </summary>
                      <div className="space-y-2 border-t border-[var(--border-subtle)] pt-2 text-[var(--text-secondary)]">
                        <div>
                          <p className="font-semibold text-[var(--text-primary)]">
                            Mapping rationale
                          </p>
                          <p className="mt-1 leading-5">
                            {row.mappingReasoning ||
                              "No mapping rationale was reported; reviewer action is required."}
                          </p>
                        </div>
                        <div>
                          <p className="font-semibold text-[var(--text-primary)]">
                            Product evidence reported by analysis
                          </p>
                          <p className="mt-1 leading-5">
                            {row.mappingEvidence ||
                              "No product-evidence text was reported."}
                          </p>
                        </div>
                        {row.doeReasoning ? (
                          <div>
                            <p className="font-semibold text-[var(--text-primary)]">
                              Doctrine-of-equivalents rationale
                            </p>
                            <p className="mt-1 leading-5">{row.doeReasoning}</p>
                          </div>
                        ) : null}
                      </div>
                    </details>
                  </section>

                  <section
                    aria-label={`Human decision for ${row.patentId}, claim ${row.claimNumber}, element ${row.elementNumber}`}
                    className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3"
                  >
                    <div className="flex items-center gap-2">
                      <Scale
                        className="h-4 w-4 text-brand-primary"
                        aria-hidden="true"
                      />
                      <h3
                        id={`claim-human-decision-${row.id}`}
                        className="text-xs font-semibold uppercase tracking-wide text-[var(--text-primary)]"
                      >
                        3 · Human decision
                      </h3>
                    </div>
                    <div className="mt-3">
                      <Badge variant={getReviewVariant(row)}>
                        {getHumanReviewLabel(row)}
                      </Badge>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                      The decision ledger records reviewer disposition
                      separately from the report&apos;s AI-assisted mapping.
                    </p>
                    <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <dt className="text-[var(--text-tertiary)]">
                          Jurisdiction
                        </dt>
                        <dd className="mt-0.5 font-semibold">
                          {row.jurisdiction || "Not reported"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[var(--text-tertiary)]">
                          Status in report snapshot
                        </dt>
                        <dd className="mt-0.5 font-semibold">
                          {row.legalStatus || "Not reported"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[var(--text-tertiary)]">
                          Reported expiry date
                        </dt>
                        <dd className="mt-0.5 font-semibold">
                          {formatDate(row.expiryDate)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[var(--text-tertiary)]">Family</dt>
                        <dd className="mt-0.5 font-mono font-semibold [overflow-wrap:anywhere]">
                          {row.familyId || "Not reported"}
                        </dd>
                      </div>
                    </dl>
                    <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                      Snapshot {formatDate(report.generated_at)}. Status
                      provenance and expiry basis are not included in this view;
                      verify the issuing authority register before reliance.
                    </p>
                    <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
                      {row.reviewTargetAssertionId && onReviewFinding ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="min-h-11 w-full"
                          aria-label={`Review claim ${row.claimNumber} element ${row.elementNumber} for ${row.patentId}`}
                          onClick={() => {
                            if (row.reviewTargetAssertionId) {
                              onReviewFinding(row.reviewTargetAssertionId);
                            }
                          }}
                        >
                          Review finding
                        </Button>
                      ) : (
                        <p className="text-xs leading-5 text-[var(--text-tertiary)]">
                          No editable review target is available for this exact
                          claim element.
                        </p>
                      )}
                    </div>
                  </section>
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
