"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ChevronDown,
  Link2,
  Scale,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RiskBadge } from "@/components/shared/risk-badge";
import { ConfidenceIndicator } from "@/components/report/confidence-indicator";
import { EvidenceCard } from "@/components/report/evidence-card";
import { AnnotatedText } from "@/components/report/annotated-text";
import { ClaimElementRow } from "@/components/patent/claim-element-row";
import { ClaimDecisionMatrix } from "@/components/report/claim-decision-matrix";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import { hasCompleteVerifiedClaimReceipt } from "@/components/report/claim-decision-matrix-model";
import { normalizeReportPatentDetail } from "@/components/report/patent-detail-normalizer";
import { ReviewerDecisionPanel } from "@/components/report/reviewer-decision-panel";
import { ClaimedUseReceiptWorkbench } from "@/components/report/claimed-use-receipt-workbench";
import type { ClaimedUseReceiptLedgerState } from "@/components/report/claimed-use-receipt-ledger";
import { cn } from "@/lib/utils";
import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";
import type {
  FTOReport,
  DoEAssessment,
  PatentHit,
  RiskLevel,
} from "@praviar/shared-types";

interface ClaimsTabProps {
  analysisId?: string;
  report: FTOReport;
  reviewerDecisions?: ReviewerDecisionListResponse | null;
  reviewerDecisionsLoading?: boolean;
  reviewerDecisionsUnavailable?: boolean;
  reviewStatus?: AnalysisReviewStatusResponse;
  token?: string | null;
  canReviewFindings?: boolean;
  canIssueClaimedUseReceipts?: boolean;
  claimedUseReceiptState?: ClaimedUseReceiptLedgerState;
  onRetryClaimedUseReceipts?: () => void;
}

type ClaimSupportEntry = NonNullable<
  NonNullable<FTOReport["claim_source_span_map"]>["entries"]
>[number];
type SourceSpanMap = NonNullable<
  NonNullable<FTOReport["claim_source_span_map"]>["spans"]
>;
type ClaimSupportStatus =
  | "supported"
  | "needs_review"
  | "unsupported"
  | "not_reported";

interface PatentClaimChartSummary {
  claimCount: number;
  elementCount: number;
  metCount: number;
  missingSpanCount: number;
  needsReviewCount: number;
  notMetCount: number;
  partialCount: number;
  patentId: string;
  riskLevel: RiskLevel;
  sourceAssertionCount: number;
  status: ClaimSupportStatus;
  supportedCount: number;
  title: string;
  unsupportedCount: number;
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

function findDoEAssessment(
  doeAssessments: DoEAssessment[] | undefined,
  patentId: string,
  claimNumber: number,
  elementNumber: number,
): DoEAssessment | null {
  return (
    doeAssessments?.find(
      (d) =>
        d.patent_id === patentId &&
        d.claim_number === claimNumber &&
        d.element_number === elementNumber,
    ) ?? null
  );
}

function getPatentHit(report: FTOReport, patentId: string): PatentHit | null {
  const details = report.patent_details;
  const analysis =
    report.patent_analyses.find((item) => item.patent_id === patentId) ?? null;
  if (!details?.[patentId] && !analysis) return null;
  return normalizeReportPatentDetail({
    analysis,
    patentId,
    rawDetail: details?.[patentId],
  });
}

export function ClaimsTab({
  analysisId,
  report,
  reviewerDecisions,
  reviewerDecisionsLoading,
  reviewerDecisionsUnavailable,
  reviewStatus,
  token = null,
  canReviewFindings = true,
  canIssueClaimedUseReceipts = false,
  claimedUseReceiptState = {
    data: undefined,
    error: undefined,
    isError: true,
    isLoading: false,
  },
  onRetryClaimedUseReceipts,
}: ClaimsTabProps) {
  const searchParams = useSearchParams();
  const focusedPatentId = searchParams.get("patent");
  const focusedClaimValue = searchParams.get("claim");
  const focusedClaimNumber =
    focusedClaimValue && /^\d+$/.test(focusedClaimValue)
      ? Number(focusedClaimValue)
      : null;
  const hasFocusedClaim = Boolean(focusedPatentId && focusedClaimNumber);
  const [reviewFindingRef, setReviewFindingRef] = useState<string | null>(null);
  const [narrativeOpen, setNarrativeOpen] = useState(false);
  const reportCitation = {
    reportId: report.report_id,
    generatedAt: report.generated_at,
    pipelineVersion: report.praviar_pipeline_version,
  };
  const claimChartSummary = buildClaimChartSummary(report);
  const claimSupportEntries = getCustomerVisibleClaimSupportEntries(report);
  const sourceSpans = report.claim_source_span_map?.spans ?? {};
  const summaryByPatentId = new Map(
    claimChartSummary.patents.map((summary) => [summary.patentId, summary]),
  );

  return (
    <div className="space-y-6">
      <ClaimChartReadinessPanel summary={claimChartSummary} />

      {analysisId && token ? (
        <ClaimedUseReceiptWorkbench
          analysisId={analysisId}
          canIssueReceipts={canIssueClaimedUseReceipts}
          canReviewFindings={canReviewFindings}
          onRetryLedger={onRetryClaimedUseReceipts}
          receiptState={claimedUseReceiptState}
          report={report}
          token={token}
        />
      ) : null}

      <ReportMobileDisclosure
        label={`Inspect ${claimChartSummary.elementCount.toLocaleString()} exact claim element records`}
        description="Open authority text, AI mapping, and human-review state for each element."
        testId="claim-decision-matrix-disclosure"
        initiallyOpen={hasFocusedClaim}
      >
        <ClaimDecisionMatrix
          decisionsLoading={reviewerDecisionsLoading}
          decisionsUnavailable={reviewerDecisionsUnavailable}
          focusedClaimNumber={focusedClaimNumber}
          focusedPatentId={focusedPatentId}
          onReviewFinding={
            analysisId && canReviewFindings ? setReviewFindingRef : undefined
          }
          report={report}
          reviewerDecisions={reviewerDecisions}
        />
      </ReportMobileDisclosure>

      {analysisId && canReviewFindings ? (
        <ReviewerDecisionPanel
          analysisId={analysisId}
          initialFindingRef={reviewFindingRef ?? undefined}
          onClose={() => setReviewFindingRef(null)}
          open={reviewFindingRef !== null}
          report={report}
          reviewStatus={reviewStatus}
          token={token}
        />
      ) : null}

      {(report.patent_analyses ?? []).length > 0 ? (
        <div>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 w-full justify-between px-4 py-3 text-left"
            aria-controls="full-claim-narrative"
            aria-expanded={narrativeOpen}
            onClick={() => setNarrativeOpen((current) => !current)}
          >
            <span>
              <span className="block text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                Full claim narrative
              </span>
              <span className="mt-1 block text-sm font-semibold text-[var(--text-primary)]">
                Expanded reasoning and element evidence
              </span>
            </span>
            <ChevronDown
              className={cn(
                "h-4 w-4 shrink-0 transition-transform motion-reduce:transition-none",
                narrativeOpen && "rotate-180",
              )}
              aria-hidden="true"
            />
          </Button>
        </div>
      ) : null}

      <div
        id="full-claim-narrative"
        data-print-redundant-narrative
        className={cn("space-y-6", !narrativeOpen && "hidden")}
      >
        {(report.patent_analyses ?? []).map((pa) => {
          const patent = getPatentHit(report, pa.patent_id);
          const patentSummary = summaryByPatentId.get(pa.patent_id);
          return (
            <Card key={pa.patent_id}>
              <CardHeader className="p-4 sm:p-6">
                <div className="flex min-w-0 flex-wrap items-center gap-2 sm:gap-3">
                  <RiskBadge risk={pa.risk_level} size="sm" />
                  <CardTitle className="min-w-0 text-sm font-mono">
                    {pa.patent_id}
                  </CardTitle>
                  <span className="min-w-0 flex-[1_1_100%] text-xs leading-5 text-[var(--text-secondary)] sm:flex-1 sm:truncate sm:leading-normal">
                    {pa.title}
                  </span>
                </div>
                {patentSummary ? (
                  <PatentClaimSupportStrip summary={patentSummary} />
                ) : null}
              </CardHeader>
              <CardContent className="space-y-5 p-4 pt-0 sm:space-y-6 sm:p-6 sm:pt-0">
                {(pa.claims_analyzed ?? []).map((claim) => {
                  const evidenceStatus:
                    | "met"
                    | "not_met"
                    | "partially_met"
                    | "unclear" =
                    claim.overall_status === "met" ||
                    claim.overall_status === "not_met" ||
                    claim.overall_status === "partially_met" ||
                    claim.overall_status === "unclear"
                      ? claim.overall_status
                      : "unclear";
                  const evidenceStatusLabel = statusLabels[evidenceStatus];

                  return (
                    <EvidenceCard
                      key={`${pa.patent_id}-${claim.claim_number}`}
                      summary={`Claim ${claim.claim_number}: ${evidenceStatusLabel}`}
                      status={evidenceStatus}
                      confidence={claim.overall_confidence}
                      defaultExpanded
                    >
                      <div className="space-y-3">
                        {/* Claim header */}
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="text-sm font-semibold text-[var(--text-primary)]">
                            Claim {claim.claim_number}
                          </span>
                          <Badge variant="secondary" className="text-xs">
                            {claim.claim_type}
                          </Badge>
                          {claim.transitional_phrase && (
                            <Badge variant="secondary" className="text-xs">
                              {claim.transitional_phrase}
                            </Badge>
                          )}
                          <span
                            className={cn(
                              "px-2 py-0.5 text-xs font-semibold rounded-full border",
                              statusColors[evidenceStatus],
                            )}
                          >
                            {evidenceStatusLabel}
                          </span>
                          <ConfidenceIndicator
                            value={claim.overall_confidence}
                            showBar
                            size="sm"
                          />
                        </div>

                        {/* Preamble */}
                        {claim.preamble && (
                          <p className="text-xs text-[var(--text-secondary)] italic">
                            {claim.preamble.length > 200
                              ? claim.preamble.slice(0, 200) + "..."
                              : claim.preamble}
                          </p>
                        )}

                        {/* Reasoning */}
                        {claim.reasoning && (
                          <div className="border-l-2 border-[var(--brand-primary)] pl-3 py-1">
                            <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                              <AnnotatedText text={claim.reasoning} />
                            </p>
                          </div>
                        )}

                        {/* Claim elements */}
                        <div className="space-y-2">
                          {(claim.elements ?? []).map((el) => {
                            const tupleSupports = findClaimSourceSupports(
                              claimSupportEntries,
                              pa.patent_id,
                              claim.claim_number,
                              el.element_number,
                            );
                            const sourceSupport =
                              findClaimMappingSupport(tupleSupports);
                            const sourceSpan = getVerifiedClaimSourceSpan(
                              tupleSupports,
                              sourceSpans,
                              pa.patent_id,
                              claim.claim_number,
                              el.element_number,
                            );
                            // Only attach DoE for NOT_MET or PARTIALLY_MET elements
                            const doe =
                              el.status === "not_met" ||
                              el.status === "partially_met"
                                ? findDoEAssessment(
                                    report.doe_assessments,
                                    pa.patent_id,
                                    claim.claim_number,
                                    el.element_number,
                                  )
                                : null;

                            return (
                              <ClaimElementRow
                                key={el.element_number}
                                element={el}
                                doeAssessment={doe}
                                patent={patent}
                                patentId={pa.patent_id}
                                claimNumber={claim.claim_number}
                                reportCitation={reportCitation}
                                sourceSpan={sourceSpan}
                                sourceSupport={sourceSupport}
                              />
                            );
                          })}
                        </div>
                      </div>
                    </EvidenceCard>
                  );
                })}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {(report.patent_analyses ?? []).length === 0 && (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-[var(--text-tertiary)]">
              No claim analyses available.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ClaimChartReadinessPanel({
  summary,
}: {
  summary: ReturnType<typeof buildClaimChartSummary>;
}) {
  const priorityPatents = summary.patents
    .slice()
    .sort(compareClaimChartPriority)
    .slice(0, 4);

  return (
    <section
      aria-label="Claim chart readiness"
      className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-muted)]/40 shadow-[var(--shadow-xs)]"
      data-testid="claim-chart-readiness"
    >
      <div className="grid gap-4 border-b border-[var(--border-subtle)] p-4 sm:p-5 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-start">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--text-tertiary)]">
            Claim chart readiness
          </p>
          <h2 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
            Element mapping with source-support posture
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
            A claim-chart cockpit for counsel review: element outcomes,
            source-supported assertions, missing spans, and patents needing
            reviewer attention before reliance.
          </p>
        </div>
        <Badge
          variant={summary.reviewItemCount > 0 ? "warning" : "success"}
          className="w-fit uppercase tracking-wide"
        >
          {summary.reviewItemCount > 0
            ? `${summary.reviewItemCount} claim support review item${
                summary.reviewItemCount === 1 ? "" : "s"
              }`
            : "Claim support clean"}
        </Badge>
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-2 sm:p-5 xl:grid-cols-4">
        <ClaimChartMetric
          icon={Scale}
          label="Element map"
          value={`${summary.totalElements.toLocaleString()} elements`}
          detail={`${summary.metCount.toLocaleString()} met / ${summary.partialCount.toLocaleString()} partial / ${summary.notMetCount.toLocaleString()} not met`}
          tone={
            summary.metCount > 0 || summary.partialCount > 0
              ? "warning"
              : "success"
          }
        />
        <ClaimChartMetric
          icon={ShieldCheck}
          label="Source support"
          value={
            summary.sourceAssertionCount > 0
              ? `${summary.supportedCount.toLocaleString()} supported`
              : "Ledger unavailable"
          }
          detail={
            summary.sourceAssertionCount > 0
              ? `${summary.needsReviewCount.toLocaleString()} review / ${summary.unsupportedCount.toLocaleString()} unsupported`
              : "No claim assertion source ledger was reported"
          }
          tone={
            summary.unsupportedCount > 0 || summary.needsReviewCount > 0
              ? "warning"
              : summary.sourceAssertionCount > 0
                ? "success"
                : "neutral"
          }
        />
        <ClaimChartMetric
          icon={Link2}
          label="Span ledger"
          value={
            summary.sourceAssertionCount > 0
              ? `${summary.presentSpanCount.toLocaleString()} / ${summary.referencedSpanCount.toLocaleString()} spans`
              : "Not reported"
          }
          detail={
            summary.sourceAssertionCount === 0
              ? "No claim span ledger was reported"
              : summary.missingSpanCount > 0
                ? `${summary.missingSpanCount.toLocaleString()} missing source span${
                    summary.missingSpanCount === 1 ? "" : "s"
                  }`
                : "Referenced spans are present"
          }
          tone={
            summary.sourceAssertionCount === 0
              ? "neutral"
              : summary.missingSpanCount > 0
                ? "warning"
                : "success"
          }
        />
        <ClaimChartMetric
          icon={AlertTriangle}
          label="Reviewer priority"
          value={`${summary.priorityPatentCount.toLocaleString()} patent${
            summary.priorityPatentCount === 1 ? "" : "s"
          }`}
          detail={
            summary.priorityPatentCount > 0
              ? "Need claim-source attention"
              : "No priority claim-source issues"
          }
          tone={summary.priorityPatentCount > 0 ? "warning" : "success"}
        />
      </div>

      <div className="border-t border-[var(--border-subtle)] p-4 sm:p-5">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Priority claim programs
            </p>
            <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
              Review the highest-consequence claim maps first
            </h3>
          </div>
          <p className="text-xs leading-5 text-[var(--text-secondary)]">
            Sorted by unsupported assertions, missing spans, review status, and
            risk.
          </p>
        </div>
        <div className="mt-3 grid gap-2 lg:grid-cols-2">
          {priorityPatents.length > 0 ? (
            priorityPatents.map((patent) => (
              <ClaimChartPriorityRow key={patent.patentId} summary={patent} />
            ))
          ) : (
            <p className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 p-3 text-xs text-[var(--text-secondary)]">
              No claim programs were reported for chart readiness.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function ClaimChartMetric({
  detail,
  icon: Icon,
  label,
  tone,
  value,
}: {
  detail: string;
  icon: LucideIcon;
  label: string;
  tone: "neutral" | "success" | "warning";
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/78 p-3">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
            tone === "success" &&
              "border-success/25 bg-success/10 text-success",
            tone === "warning" &&
              "border-warning/25 bg-warning/10 text-warning",
            tone === "neutral" &&
              "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-secondary)]",
          )}
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        <p className="truncate text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
          {label}
        </p>
      </div>
      <p className="mt-3 text-xl font-semibold tabular-nums text-[var(--text-primary)]">
        {value}
      </p>
      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
        {detail}
      </p>
    </div>
  );
}

function PatentClaimSupportStrip({
  summary,
}: {
  summary: PatentClaimChartSummary;
}) {
  return (
    <dl
      aria-label={`${summary.patentId} claim support summary`}
      className="mt-3 grid gap-2 text-xs sm:grid-cols-3"
    >
      <ClaimSupportDatum
        label="Claims"
        value={`${summary.claimCount.toLocaleString()} claim${
          summary.claimCount === 1 ? "" : "s"
        }`}
        detail={`${summary.elementCount.toLocaleString()} mapped elements`}
      />
      <ClaimSupportDatum
        label="Source support"
        value={formatClaimSupportStatus(summary.status)}
        detail={`${summary.supportedCount.toLocaleString()} supported / ${summary.needsReviewCount.toLocaleString()} review`}
        tone={claimSupportTone(summary.status)}
      />
      <ClaimSupportDatum
        label="Reviewer focus"
        value={
          summary.missingSpanCount > 0
            ? "Missing source spans"
            : summary.unsupportedCount > 0
              ? "Unsupported assertions"
              : summary.needsReviewCount > 0
                ? "Needs review"
                : "Ready to inspect"
        }
        detail={`${summary.missingSpanCount.toLocaleString()} missing / ${summary.unsupportedCount.toLocaleString()} unsupported`}
        tone={
          summary.missingSpanCount > 0 || summary.unsupportedCount > 0
            ? "warning"
            : "neutral"
        }
      />
    </dl>
  );
}

function ClaimSupportDatum({
  detail,
  label,
  tone = "neutral",
  value,
}: {
  detail: string;
  label: string;
  tone?: "neutral" | "success" | "warning";
  value: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/70 px-3 py-2">
      <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 break-words text-sm font-semibold text-[var(--text-primary)]",
          tone === "success" && "text-success",
          tone === "warning" && "text-warning",
        )}
      >
        {value}
      </dd>
      <dd className="mt-0.5 text-xs leading-4 text-[var(--text-secondary)]">
        {detail}
      </dd>
    </div>
  );
}

function ClaimChartPriorityRow({
  summary,
}: {
  summary: PatentClaimChartSummary;
}) {
  return (
    <div className="grid min-w-0 gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-surface)]/74 p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <RiskBadge risk={summary.riskLevel} size="sm" />
          <p className="break-words font-mono text-xs font-semibold text-[var(--text-primary)]">
            {summary.patentId}
          </p>
          <Badge
            variant={claimSupportBadgeVariant(summary.status)}
            className="text-xs uppercase"
          >
            {formatClaimSupportStatus(summary.status)}
          </Badge>
        </div>
        <p className="mt-2 line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
          {summary.title}
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center sm:w-64">
        <MiniStat label="Elements" value={summary.elementCount} />
        <MiniStat label="Review" value={summary.needsReviewCount} />
        <MiniStat label="Missing" value={summary.missingSpanCount} />
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-0 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-muted)]/54 px-2 py-2">
      <p className="text-base font-semibold tabular-nums text-[var(--text-primary)]">
        {value.toLocaleString()}
      </p>
      <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
        {label}
      </p>
    </div>
  );
}

function buildClaimChartSummary(report: FTOReport) {
  const spanMap = report.claim_source_span_map?.spans ?? {};
  const sourceEntries = getCustomerVisibleClaimSupportEntries(report);
  const patents = (report.patent_analyses ?? []).map((analysis) =>
    buildPatentClaimChartSummary(analysis, sourceEntries, spanMap),
  );
  const totals = patents.reduce(
    (acc, patent) => ({
      elementCount: acc.elementCount + patent.elementCount,
      metCount: acc.metCount + patent.metCount,
      missingSpanCount: acc.missingSpanCount + patent.missingSpanCount,
      needsReviewCount: acc.needsReviewCount + patent.needsReviewCount,
      notMetCount: acc.notMetCount + patent.notMetCount,
      partialCount: acc.partialCount + patent.partialCount,
      sourceAssertionCount:
        acc.sourceAssertionCount + patent.sourceAssertionCount,
      supportedCount: acc.supportedCount + patent.supportedCount,
      unsupportedCount: acc.unsupportedCount + patent.unsupportedCount,
    }),
    {
      elementCount: 0,
      metCount: 0,
      missingSpanCount: 0,
      needsReviewCount: 0,
      notMetCount: 0,
      partialCount: 0,
      sourceAssertionCount: 0,
      supportedCount: 0,
      unsupportedCount: 0,
    },
  );
  const referencedSpanCount = sourceEntries.reduce(
    (count, entry) => count + (entry.source_span_ids?.length ?? 0),
    0,
  );
  const presentSpanCount = sourceEntries.reduce(
    (count, entry) =>
      count +
      (entry.source_span_ids ?? []).filter((spanId) => Boolean(spanMap[spanId]))
        .length,
    0,
  );
  const priorityPatentCount = patents.filter((patent) =>
    isPriorityClaimPatent(patent),
  ).length;
  const reviewItemCount =
    totals.missingSpanCount + totals.needsReviewCount + totals.unsupportedCount;

  return {
    ...totals,
    patents,
    presentSpanCount,
    priorityPatentCount,
    referencedSpanCount,
    reviewItemCount,
    totalClaims: (report.patent_analyses ?? []).reduce(
      (total, analysis) => total + (analysis.claims_analyzed ?? []).length,
      0,
    ),
    totalElements: totals.elementCount,
  };
}

function buildPatentClaimChartSummary(
  analysis: NonNullable<FTOReport["patent_analyses"]>[number],
  sourceEntries: ClaimSupportEntry[],
  spanMap: SourceSpanMap,
): PatentClaimChartSummary {
  const claims = analysis.claims_analyzed ?? [];
  const elements = claims.flatMap((claim) => claim.elements ?? []);
  const patentSourceEntries = sourceEntries.filter(
    (entry) => entry.patent_id === analysis.patent_id,
  );
  const missingSpanCount = patentSourceEntries.filter((entry) =>
    (entry.source_span_ids ?? []).some((spanId) => !spanMap[spanId]),
  ).length;
  const supportedCount = patentSourceEntries.filter(
    (entry) => entry.support_status === "supported",
  ).length;
  const unsupportedCount = patentSourceEntries.filter(
    (entry) => entry.support_status === "unsupported",
  ).length;
  const needsReviewCount = patentSourceEntries.filter(
    (entry) =>
      entry.support_status === "needs_review" || entry.review_required === true,
  ).length;

  return {
    claimCount: claims.length,
    elementCount: elements.length,
    metCount: elements.filter((element) => element.status === "met").length,
    missingSpanCount,
    needsReviewCount,
    notMetCount: elements.filter((element) => element.status === "not_met")
      .length,
    partialCount: elements.filter(
      (element) => element.status === "partially_met",
    ).length,
    patentId: analysis.patent_id,
    riskLevel: analysis.risk_level,
    sourceAssertionCount: patentSourceEntries.length,
    status: getPatentClaimSupportStatus({
      missingSpanCount,
      needsReviewCount,
      sourceAssertionCount: patentSourceEntries.length,
      unsupportedCount,
    }),
    supportedCount,
    title: analysis.title,
    unsupportedCount,
  };
}

function getCustomerVisibleClaimSupportEntries(report: FTOReport) {
  return (report.claim_source_span_map?.entries ?? []).filter(
    (entry) => entry.customer_visible !== false,
  );
}

function findClaimSourceSupports(
  entries: ClaimSupportEntry[],
  patentId: string,
  claimNumber: number,
  elementNumber: number,
) {
  return entries.filter(
    (entry) =>
      entry.patent_id === patentId &&
      entry.claim_number === claimNumber &&
      entry.element_number === elementNumber,
  );
}

function findClaimMappingSupport(entries: ClaimSupportEntry[]) {
  return (
    entries
      .filter(
        (entry) =>
          entry.report_section === "claim_element_analysis" ||
          entry.review_required === true,
      )
      .sort((left, right) => {
        const leftPriority =
          left.review_required || left.support_status === "needs_review"
            ? 0
            : 1;
        const rightPriority =
          right.review_required || right.support_status === "needs_review"
            ? 0
            : 1;
        return (
          leftPriority - rightPriority ||
          left.assertion_id.localeCompare(right.assertion_id)
        );
      })[0] ?? null
  );
}

function getVerifiedClaimSourceSpan(
  entries: ClaimSupportEntry[],
  spans: SourceSpanMap,
  patentId: string,
  claimNumber: number,
  elementNumber: number,
) {
  const spanIds = Array.from(
    new Set(
      entries
        .filter((entry) => entry.support_status === "supported")
        .flatMap((entry) => entry.source_span_ids ?? []),
    ),
  ).sort();
  for (const spanId of spanIds) {
    const span = spans[spanId];
    if (
      span &&
      hasCompleteVerifiedClaimReceipt(span) &&
      span.patent_id === patentId &&
      span.claim_number === claimNumber &&
      span.element_number === elementNumber
    ) {
      return span;
    }
  }
  return null;
}

function getPatentClaimSupportStatus({
  missingSpanCount,
  needsReviewCount,
  sourceAssertionCount,
  unsupportedCount,
}: {
  missingSpanCount: number;
  needsReviewCount: number;
  sourceAssertionCount: number;
  unsupportedCount: number;
}): ClaimSupportStatus {
  if (unsupportedCount > 0) return "unsupported";
  if (needsReviewCount > 0 || missingSpanCount > 0) return "needs_review";
  if (sourceAssertionCount > 0) return "supported";
  return "not_reported";
}

function isPriorityClaimPatent(summary: PatentClaimChartSummary) {
  return (
    summary.status === "unsupported" ||
    summary.status === "needs_review" ||
    summary.riskLevel === "high"
  );
}

function compareClaimChartPriority(
  left: PatentClaimChartSummary,
  right: PatentClaimChartSummary,
) {
  return getClaimChartPriorityScore(right) - getClaimChartPriorityScore(left);
}

function getClaimChartPriorityScore(summary: PatentClaimChartSummary) {
  const riskScore =
    summary.riskLevel === "high" ? 4 : summary.riskLevel === "medium" ? 2 : 0;
  return (
    summary.unsupportedCount * 10 +
    summary.missingSpanCount * 8 +
    summary.needsReviewCount * 6 +
    riskScore +
    summary.metCount
  );
}

function formatClaimSupportStatus(status: ClaimSupportStatus) {
  switch (status) {
    case "supported":
      return "Supported";
    case "needs_review":
      return "Needs review";
    case "unsupported":
      return "Unsupported";
    case "not_reported":
      return "Not reported";
  }
}

function claimSupportBadgeVariant(status: ClaimSupportStatus) {
  switch (status) {
    case "supported":
      return "success";
    case "unsupported":
      return "destructive";
    case "needs_review":
      return "warning";
    case "not_reported":
      return "secondary";
  }
}

function claimSupportTone(status: ClaimSupportStatus) {
  return status === "supported"
    ? "success"
    : status === "needs_review" || status === "unsupported"
      ? "warning"
      : "neutral";
}
