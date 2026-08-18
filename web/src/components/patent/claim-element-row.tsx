"use client";

import { useState, type MouseEvent } from "react";
import { ChevronDown, ChevronRight, Scale, ShieldX, Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import { ConfidenceBar } from "@/components/shared/confidence-bar";
import {
  EvidenceDrilldown,
  type EvidenceCitationReportContext,
} from "@/components/report/evidence-drilldown";
import type {
  ClaimAssertionSupport,
  ClaimElement,
  DoEAssessment,
  PatentHit,
  SourceSpanReference,
} from "@praviar/shared-types";

interface ClaimElementRowProps {
  element: ClaimElement;
  doeAssessment?: DoEAssessment | null;
  patent?: PatentHit | null;
  claimNumber?: number;
  patentId?: string;
  reportCitation?: EvidenceCitationReportContext;
  sourceSpan?: SourceSpanReference | null;
  sourceSupport?: ClaimAssertionSupport | null;
}

const statusColors: Record<string, string> = {
  met: "bg-error/20 text-error border-error/30",
  not_met: "bg-success/20 text-success border-success/30",
  partially_met: "bg-warning/20 text-warning border-warning/30",
  unclear:
    "bg-[var(--surface-muted)] text-[var(--text-tertiary)] border-[var(--border-default)]",
};

const statusLabels: Record<string, string> = {
  met: "Met",
  not_met: "Not Met",
  partially_met: "Partial",
  unclear: "Unclear",
};

export function ClaimElementRow({
  element,
  doeAssessment,
  patent,
  claimNumber,
  patentId: patentIdProp,
  reportCitation,
  sourceSpan,
  sourceSupport,
}: ClaimElementRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [drilldownOpen, setDrilldownOpen] = useState(false);

  const effectiveClaimNumber = claimNumber ?? sourceSupport?.claim_number ?? 0;
  const effectivePatentId =
    patent?.patent_id ??
    patentIdProp ??
    sourceSpan?.patent_id ??
    sourceSupport?.patent_id ??
    "Report packet";
  const canShowEvidence = Boolean(
    (patent && typeof claimNumber === "number") || sourceSpan || sourceSupport,
  );
  const hasEvidenceQuote = Boolean(element.evidence?.trim());
  const sourceRecord =
    sourceSpan?.citation ??
    sourceSupport?.assertion_id ??
    patent?.patent_id ??
    "Report packet";
  const sourceSpanStatus = getSourceSpanStatus({
    hasEvidenceQuote,
    sourceSpan,
    sourceSupport,
  });
  const supportLabel = sourceSupport?.support_status
    ? formatSourceSupportStatus(sourceSupport.support_status)
    : (statusLabels[element.status] ?? element.status);
  const detailsId = `${toDomId(effectivePatentId)}-claim-${
    effectiveClaimNumber || "unknown"
  }-element-${element.element_number}-details`;
  const rowId = detailsId.replace(/-details$/, "");
  const openDrilldown = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    setDrilldownOpen(true);
  };

  return (
    <div
      id={rowId}
      className="praviar-glass-chip overflow-hidden rounded-lg"
      data-testid={`claim-element-row-${element.element_number}`}
    >
      <div className="flex flex-col sm:flex-row sm:items-stretch">
        <button
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          aria-controls={detailsId}
          aria-label={`Toggle details for ${effectivePatentId} claim ${
            effectiveClaimNumber || "unknown"
          } element ${element.element_number}: ${element.element_text}`}
          data-print-content
          className="flex-1 p-3 text-left transition-colors hover:bg-[var(--surface-muted)] sm:p-4"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
            <div className="flex min-w-0 flex-1 items-start gap-3">
              <span className="mt-0.5 w-8 flex-shrink-0 font-mono text-xs text-[var(--text-tertiary)]">
                #{element.element_number}
              </span>
              <span
                className="min-w-0 flex-1 text-sm leading-6 text-[var(--text-primary)] sm:truncate sm:leading-normal"
                data-testid={`claim-element-text-${element.element_number}`}
              >
                {element.element_text}
              </span>
            </div>
            <div className="ml-11 flex flex-wrap items-center gap-2 sm:ml-0 sm:flex-nowrap">
              <span
                className={cn(
                  "flex-shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold",
                  statusColors[element.status] ?? statusColors.unclear,
                )}
              >
                {statusLabels[element.status] ?? element.status}
              </span>
              <div className="w-24 flex-shrink-0 sm:w-20">
                <ConfidenceBar value={element.confidence} size="sm" />
              </div>
              {expanded ? (
                <ChevronDown className="h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
              ) : (
                <ChevronRight className="h-4 w-4 flex-shrink-0 text-[var(--text-tertiary)]" />
              )}
            </div>
          </div>

          <dl
            aria-label={`${effectivePatentId} claim ${
              effectiveClaimNumber || "unknown"
            } element ${element.element_number} provenance`}
            className="mt-3 ml-11 grid gap-2 text-xs sm:grid-cols-3"
          >
            <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_70%,transparent)] px-2.5 py-2">
              <dt className="type-label-sm text-[var(--text-tertiary)]">
                Support
              </dt>
              <dd className="mt-1 font-semibold text-[var(--text-primary)]">
                {supportLabel}
              </dd>
            </div>
            <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_70%,transparent)] px-2.5 py-2">
              <dt className="type-label-sm text-[var(--text-tertiary)]">
                Evidence span
              </dt>
              <dd
                className={cn(
                  "mt-1 font-semibold",
                  sourceSpanStatus.tone === "success" &&
                    "text-[var(--text-primary)]",
                  sourceSpanStatus.tone === "warning" && "text-warning",
                  sourceSpanStatus.tone === "danger" && "text-error",
                )}
              >
                {sourceSpanStatus.label}
              </dd>
            </div>
            <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--bg-surface)_70%,transparent)] px-2.5 py-2">
              <dt className="type-label-sm text-[var(--text-tertiary)]">
                Source record
              </dt>
              <dd
                className="mt-1 font-mono font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]"
                title={sourceRecord}
              >
                {sourceRecord}
              </dd>
            </div>
          </dl>

          {element.evidence ? (
            <div
              className="mt-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-subtle)] p-3 sm:hidden"
              data-testid={`claim-element-evidence-summary-${element.element_number}`}
            >
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                Evidence excerpt
              </p>
              <blockquote className="mt-1 line-clamp-2 border-l-2 border-brand-primary/30 pl-3 text-xs leading-5 text-[var(--text-secondary)]">
                {element.evidence}
              </blockquote>
            </div>
          ) : null}
        </button>
        {canShowEvidence ? (
          <button
            type="button"
            onClick={openDrilldown}
            aria-label={`View source for ${effectivePatentId} claim ${effectiveClaimNumber} element ${element.element_number}`}
            data-testid={`claim-element-evidence-btn-${element.element_number}`}
            className="flex min-h-11 w-full flex-shrink-0 items-center justify-center gap-2 border-t border-[var(--border-subtle)] px-3 text-xs font-medium text-brand-primary transition-colors hover:bg-[var(--surface-muted)] sm:w-auto sm:border-l sm:border-t-0"
          >
            <Quote className="h-3.5 w-3.5" aria-hidden="true" />
            <span>View source</span>
          </button>
        ) : null}
      </div>

      <div
        className={cn(
          "grid transition-all duration-200 ease-in-out",
          expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden" id={detailsId}>
          <div className="border-t border-[var(--border-subtle)] p-4 bg-[var(--surface-subtle)] space-y-3">
            {/* Full element text */}
            <div>
              <p className="text-xs font-semibold text-[var(--text-tertiary)] mb-1">
                Element Text
              </p>
              <p className="text-sm text-[var(--text-primary)]">
                {element.element_text}
              </p>
            </div>

            {/* Reasoning */}
            <div>
              <p className="text-xs font-semibold text-[var(--text-tertiary)] mb-1">
                Reasoning
              </p>
              <p className="text-sm text-[var(--text-primary)]">
                {element.reasoning}
              </p>
            </div>

            {/* Evidence */}
            {element.evidence && (
              <div>
                <p className="text-xs font-semibold text-[var(--text-tertiary)] mb-1">
                  Evidence
                </p>
                <blockquote className="border-l-2 border-brand-primary/30 pl-3 text-sm text-[var(--text-secondary)] italic">
                  {element.evidence}
                </blockquote>
              </div>
            )}

            {/* DoE Assessment */}
            {doeAssessment && (
              <div className="space-y-3 pt-2">
                {/* FWR Test */}
                {doeAssessment.fwr && (
                  <div className="praviar-glass-panel-soft rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-3">
                      <Scale className="h-4 w-4 text-warning" />
                      <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                        Function-Way-Result Analysis
                      </h4>
                    </div>
                    <div className="space-y-3">
                      {(
                        [
                          {
                            label: "Same Function",
                            result: doeAssessment.fwr.same_function,
                            reasoning: doeAssessment.fwr.function_reasoning,
                          },
                          {
                            label: "Same Way",
                            result: doeAssessment.fwr.same_way,
                            reasoning: doeAssessment.fwr.way_reasoning,
                          },
                          {
                            label: "Same Result",
                            result: doeAssessment.fwr.same_result,
                            reasoning: doeAssessment.fwr.result_reasoning,
                          },
                        ] as const
                      ).map((test) => (
                        <div
                          key={test.label}
                          className="praviar-glass-chip flex items-start gap-3 rounded-lg p-3"
                        >
                          <span className="mt-0.5 text-base flex-shrink-0">
                            {test.result ? "\u2713" : "\u2715"}
                          </span>
                          <div>
                            <p className="text-sm font-medium text-[var(--text-primary)]">
                              {test.label}
                            </p>
                            <p className="text-xs text-[var(--text-secondary)] mt-1">
                              {test.reasoning}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Estoppel */}
                <div className="praviar-glass-panel-soft rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <ShieldX className="h-4 w-4 text-warning" />
                    <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                      Prosecution History Estoppel
                    </h4>
                  </div>
                  <div className="space-y-2 text-sm text-[var(--text-primary)]">
                    <p>
                      <span className="text-[var(--text-tertiary)]">
                        Amendments found:
                      </span>{" "}
                      {doeAssessment.estoppel.amendments_found.length > 0
                        ? doeAssessment.estoppel.amendments_found.join(", ")
                        : "None"}
                    </p>
                    <p>
                      <span className="text-[var(--text-tertiary)]">
                        Estoppel applies:
                      </span>{" "}
                      {doeAssessment.estoppel.estoppel_applies ? "Yes" : "No"}
                    </p>
                    {doeAssessment.estoppel.surrendered_scope && (
                      <p>
                        <span className="text-[var(--text-tertiary)]">
                          Surrendered scope:
                        </span>{" "}
                        {doeAssessment.estoppel.surrendered_scope}
                      </p>
                    )}
                  </div>
                </div>

                {/* Confidence band */}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[var(--text-tertiary)]">
                    Confidence band:
                  </span>
                  <span
                    className={cn(
                      "px-2 py-0.5 text-xs font-semibold rounded-full",
                      doeAssessment.confidence_band === "HIGH"
                        ? "bg-success/20 text-success"
                        : doeAssessment.confidence_band === "MODERATE"
                          ? "bg-warning/20 text-warning"
                          : "bg-error/20 text-error",
                    )}
                  >
                    {doeAssessment.confidence_band}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      {canShowEvidence ? (
        <EvidenceDrilldown
          patent={patent ?? null}
          claimNumber={effectiveClaimNumber}
          element={element}
          reportCitation={reportCitation}
          sourceSpan={sourceSpan}
          sourceSupport={sourceSupport}
          open={drilldownOpen}
          onClose={() => setDrilldownOpen(false)}
        />
      ) : null}
    </div>
  );
}

function toDomId(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function formatSourceSupportStatus(
  status: NonNullable<ClaimAssertionSupport["support_status"]>,
) {
  return status
    .replaceAll("_", " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getSourceSpanStatus({
  hasEvidenceQuote,
  sourceSpan,
  sourceSupport,
}: {
  hasEvidenceQuote: boolean;
  sourceSpan?: SourceSpanReference | null;
  sourceSupport?: ClaimAssertionSupport | null;
}) {
  if (sourceSupport?.support_status === "unsupported") {
    return { label: "Unsupported", tone: "danger" as const };
  }
  if (sourceSpan?.span_id) {
    return { label: "Ledger span", tone: "success" as const };
  }
  if (
    sourceSupport?.support_status === "needs_review" ||
    sourceSupport?.review_required
  ) {
    return { label: "Needs review", tone: "warning" as const };
  }
  if (sourceSupport) {
    return { label: "Missing ledger span", tone: "warning" as const };
  }
  if (hasEvidenceQuote) {
    return { label: "Quoted", tone: "success" as const };
  }
  return { label: "Missing quote", tone: "warning" as const };
}
