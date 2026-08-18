"use client";

import { AuditTab } from "@/components/report/audit-tab";
import { ClaimsTab } from "@/components/report/claims-tab";
import {
  ClaimedUseReceiptLedger,
  type ClaimedUseReceiptLedgerState,
} from "@/components/report/claimed-use-receipt-ledger";
import { ChatPanelEvidenceTab } from "@/components/report/chat-panel-evidence-tab";
import { CommentPanel } from "@/components/report/comment-panel";
import { DrawingsTab } from "@/components/report/drawings-tab";
import { InvalidityTab } from "@/components/report/invalidity-tab";
import { MetaTab } from "@/components/report/meta-tab";
import { PatentsTab } from "@/components/report/patents-tab";
import {
  PrintReport,
  type PrintReportPacketSummary,
} from "@/components/report/print-report";
import { ReasoningTab } from "@/components/report/reasoning-tab";
import { ReportMobileDisclosure } from "@/components/report/report-mobile-disclosure";
import { RegulatoryTab } from "@/components/report/regulatory-tab";
import { SummaryTab } from "@/components/report/summary-tab";
import { ErrorBoundary } from "@/components/shared/error-boundary";
import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";
import type { ReportWorkspaceSummaryResponse } from "@/hooks/use-report-workspace-summary";
import type { ReviewHandoffResponse } from "@/hooks/use-review-handoff";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";
import type { ChatWorkspaceMetadata } from "@/hooks/use-report-chat";
import type { FTOReport } from "@praviar/shared-types";
import { ReportEvidenceWorkbench } from "./report-evidence-workbench";
import {
  formatReportRiskLabel,
  getReportReference,
} from "./report-command-summary";
import {
  getWorkspaceBlockingJurisdictions,
  getWorkspaceExportReady,
  getWorkspaceOpinionSummary,
  getReportSourceHealthReadiness,
  getReviewerDecisionExportBlockers,
  isHealthySourceStatus,
  normalizeSourceHealthStatus,
} from "./report-reliance-readiness";
import { PRIMARY_TABS, getOverflowTabs } from "./tabs";
import type { ReportTabConfig, ReportTabId } from "./tabs";

interface ReportPageTabContentProps {
  analysisId: string;
  tab: ReportTabId;
  labelId?: string;
  report: FTOReport;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
  token?: string | null;
  initialEvidenceQuery?: string;
  reviewerDecisions?: ReviewerDecisionListResponse | null;
  reviewerDecisionsLoading?: boolean;
  reviewerDecisionsUnavailable?: boolean;
  workspaceSummary?: ReportWorkspaceSummaryResponse | null;
  workspaceSummaryLoading?: boolean;
  onReviewHandoffSuccess?: (response: ReviewHandoffResponse) => void;
  canManageCollaboration?: boolean;
  claimedUseReceiptState?: ClaimedUseReceiptLedgerState;
  currentUserRole?: string | null;
  onRetryClaimedUseReceipts?: () => void;
}

export function ReportPageTabContent({
  analysisId,
  tab,
  labelId = `tab-${tab}`,
  report,
  reviewStatus,
  reviewStatusLoading,
  token = null,
  initialEvidenceQuery = "",
  reviewerDecisions,
  reviewerDecisionsLoading,
  reviewerDecisionsUnavailable,
  workspaceSummary,
  workspaceSummaryLoading,
  onReviewHandoffSuccess,
  canManageCollaboration = true,
  claimedUseReceiptState,
  currentUserRole,
  onRetryClaimedUseReceipts,
}: ReportPageTabContentProps) {
  // Reset any tab-level crash when the underlying report changes so a failure
  // captured for one analysis does not persist as a stale fallback when the
  // user navigates to a different report (the page component is reused across
  // [id] segments rather than remounted).
  const resetKeys = [report.report_id] as const;
  const printSectionLabel = getReportTabPrintLabel(tab);

  return (
    <PrintReport
      compoundName={report.compound?.name}
      date={report.generated_at}
      provenanceItems={buildPrintReportProvenance(report, printSectionLabel)}
      packetSummary={buildPrintReportPacketSummary({
        report,
        reviewStatus,
        reviewStatusLoading,
        reviewerDecisions,
        reviewerDecisionsLoading,
        sectionLabel: printSectionLabel,
        workspaceSummary,
        workspaceSummaryLoading,
      })}
      relianceItems={buildPrintReportReliance(report)}
      claimedUseReceiptState={
        canManageCollaboration ? claimedUseReceiptState : undefined
      }
      showButton={false}
      title={`Local report-section print - ${printSectionLabel}`}
    >
      {canManageCollaboration && claimedUseReceiptState && tab !== "claims" ? (
        <div className="mb-4" data-no-print>
          <ClaimedUseReceiptLedger state={claimedUseReceiptState} />
        </div>
      ) : null}
      <div
        role="tabpanel"
        id={`tabpanel-${tab}`}
        data-testid={`report-tab-${tab}`}
        aria-labelledby={labelId}
        tabIndex={0}
      >
        {tab === "overview" && (
          <ErrorBoundary title="Summary failed to load" resetKeys={resetKeys}>
            <SummaryTab report={report} />
          </ErrorBoundary>
        )}
        {tab === "patents" && (
          <ErrorBoundary
            title="Patents tab failed to load"
            resetKeys={resetKeys}
          >
            <PatentsTab
              report={report}
              analysisId={analysisId}
              canSubmitFeedback={canManageCollaboration}
            />
          </ErrorBoundary>
        )}
        {tab === "claims" && (
          <ErrorBoundary
            title="Claims tab failed to load"
            resetKeys={resetKeys}
          >
            <ClaimsTab
              analysisId={analysisId}
              report={report}
              reviewerDecisions={reviewerDecisions}
              reviewerDecisionsLoading={reviewerDecisionsLoading}
              reviewerDecisionsUnavailable={reviewerDecisionsUnavailable}
              reviewStatus={reviewStatus}
              token={token}
              canReviewFindings={canManageCollaboration}
              canIssueClaimedUseReceipts={currentUserRole === "attorney"}
              claimedUseReceiptState={claimedUseReceiptState}
              onRetryClaimedUseReceipts={onRetryClaimedUseReceipts}
            />
          </ErrorBoundary>
        )}
        {tab === "drawings" && (
          <ErrorBoundary
            title="Drawings tab failed to load"
            resetKeys={resetKeys}
          >
            <DrawingsTab report={report} />
          </ErrorBoundary>
        )}
        {tab === "evidence" && (
          <ErrorBoundary
            title="Evidence tab failed to load"
            resetKeys={resetKeys}
          >
            <div className="space-y-4">
              <ReportEvidenceWorkbench
                report={report}
                readinessInput={{
                  additionalBlockers: getReviewerDecisionExportBlockers({
                    report,
                    reviewStatus,
                    reviewerDecisions,
                    reviewerDecisionsLoading,
                  }),
                  reviewStatus,
                  reviewStatusLoading,
                  workspaceSummary: workspaceSummary ?? undefined,
                  workspaceSummaryLoading,
                }}
              />
              <ReportMobileDisclosure
                label="Search governed report evidence"
                description="Ask evidence-grounded questions and prepare a reviewer handoff."
              >
                <ChatPanelEvidenceTab
                  key={initialEvidenceQuery || "evidence-search-empty"}
                  analysisId={analysisId}
                  token={token}
                  initialQuery={initialEvidenceQuery}
                  queryInputId="report-evidence-workbench-query"
                  workspaceMeta={buildEvidenceWorkspaceMeta(workspaceSummary)}
                  suggestedQueries={buildEvidenceSuggestedQueries(
                    workspaceSummary,
                  )}
                  onReviewHandoffSuccess={onReviewHandoffSuccess}
                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]/72 p-4 shadow-[var(--shadow-xs)]"
                />
              </ReportMobileDisclosure>
            </div>
          </ErrorBoundary>
        )}
        {tab === "invalidity" && (
          <ErrorBoundary
            title="Invalidity tab failed to load"
            resetKeys={resetKeys}
          >
            <InvalidityTab report={report} />
          </ErrorBoundary>
        )}
        {tab === "regulatory" && (
          <ErrorBoundary
            title="Regulatory tab failed to load"
            resetKeys={resetKeys}
          >
            <RegulatoryTab report={report} />
          </ErrorBoundary>
        )}
        {tab === "comments" && (
          <ErrorBoundary title="Comments failed to load" resetKeys={resetKeys}>
            <CommentPanel analysisId={analysisId} />
          </ErrorBoundary>
        )}
        {tab === "audit" && (
          <ErrorBoundary title="Audit tab failed to load" resetKeys={resetKeys}>
            <AuditTab report={report} />
          </ErrorBoundary>
        )}
        {tab === "meta" && (
          <ErrorBoundary title="Meta tab failed to load" resetKeys={resetKeys}>
            <MetaTab report={report} />
          </ErrorBoundary>
        )}
        {tab === "reasoning" && (
          <ErrorBoundary
            title="Reasoning tab failed to load"
            resetKeys={resetKeys}
          >
            <ReasoningTab report={report} />
          </ErrorBoundary>
        )}
      </div>
    </PrintReport>
  );
}

function buildPrintReportPacketSummary({
  report,
  reviewStatus,
  reviewStatusLoading,
  reviewerDecisions,
  reviewerDecisionsLoading,
  sectionLabel,
  workspaceSummary,
  workspaceSummaryLoading,
}: {
  report: FTOReport;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
  reviewerDecisions?: ReviewerDecisionListResponse | null;
  reviewerDecisionsLoading?: boolean;
  sectionLabel: string;
  workspaceSummary?: ReportWorkspaceSummaryResponse | null;
  workspaceSummaryLoading?: boolean;
}): PrintReportPacketSummary {
  const reportReference = getReportReference(report);
  const riskLabel = formatReportRiskLabel(report.risk_summary.overall_risk);
  const sourceEntries = report.source_health?.entries ?? [];
  const sourceHealthReadiness = getReportSourceHealthReadiness(report);
  const sourceCount =
    sourceHealthReadiness.totalCount ||
    sourceEntries.length ||
    report.search_sources_used?.length ||
    0;
  const healthySourceCount = sourceEntries.filter((entry) =>
    isHealthySourceStatus(entry.status),
  ).length;
  const sourceSummary =
    sourceHealthReadiness.totalCount > 0
      ? `${sourceHealthReadiness.okCount}/${sourceHealthReadiness.totalCount} sources healthy`
      : sourceEntries.length > 0
        ? `${healthySourceCount}/${sourceCount} sources healthy`
        : sourceCount > 0
          ? `${sourceCount} sources listed`
          : "Source scope not reported";
  const materialPatents =
    report.clearance_decision?.decision_audit?.material_patents_reviewed ??
    report.risk_summary.total_patents_analyzed ??
    report.patent_analyses?.length ??
    0;
  const exportReady = getWorkspaceExportReady(workspaceSummary ?? undefined);
  const blockingJurisdictions = getWorkspaceBlockingJurisdictions(
    workspaceSummary ?? undefined,
  );
  const workspaceSummaryText = getWorkspaceOpinionSummary(
    workspaceSummary ?? undefined,
  );
  const isReviewApproved = reviewStatus?.status === "approved";
  const reviewerDecisionBlockers = getReviewerDecisionExportBlockers({
    report,
    reviewStatus,
    reviewerDecisions,
    reviewerDecisionsLoading,
  });

  const items = [
    { label: "Artifact", value: `Local browser print: ${sectionLabel}` },
    { label: "Report", value: reportReference },
    { label: "Decision", value: riskLabel },
    {
      label: "Evidence",
      value: `${sourceSummary}; ${materialPatents.toLocaleString()} material patents`,
    },
  ];

  if (workspaceSummaryLoading || reviewStatusLoading) {
    return {
      detail:
        "Live review and export readiness checks are still loading; preserve this artifact as a review packet until checks resolve.",
      items,
      label: "Readiness checking",
      tone: "warning",
    };
  }

  if (exportReady === false || blockingJurisdictions.length > 0) {
    const jurisdictionText =
      blockingJurisdictions.length > 0
        ? ` Blocking jurisdictions: ${blockingJurisdictions.join(", ")}.`
        : "";
    return {
      detail:
        (workspaceSummaryText ||
          "Backend export readiness has not cleared for this packet.") +
        jurisdictionText,
      items,
      label: "Not cleared for export reliance",
      tone: "danger",
    };
  }

  if (!isReviewApproved) {
    return {
      detail:
        "Printed artifact preserves report caveats, but qualified counsel review is still required before downstream reliance.",
      items,
      label: "Counsel review pending",
      tone: "warning",
    };
  }

  if (exportReady !== true) {
    return {
      detail:
        "Counsel review is recorded, but backend export readiness has not yet confirmed this packet for downstream reliance.",
      items,
      label: "Export readiness incomplete",
      tone: "warning",
    };
  }

  if (reviewerDecisionBlockers.length > 0) {
    return {
      detail: reviewerDecisionBlockers
        .map((blocker) => blocker.detail)
        .join(" "),
      items,
      label:
        reviewerDecisionBlockers[0]?.label ?? "Reviewer decisions incomplete",
      tone: reviewerDecisionBlockers.some(
        (blocker) => blocker.tone === "danger",
      )
        ? "danger"
        : "warning",
    };
  }

  if (sourceHealthReadiness.hasCaveats) {
    return {
      detail: `Counsel approval and backend readiness are recorded; source caveats must remain attached to any exported artifact. ${sourceHealthReadiness.detail}`,
      items,
      label: "Exportable with source caveats",
      tone: "warning",
    };
  }

  return {
    detail:
      "Counsel approval, backend readiness, and source coverage are recorded. Use governed export for the full packet.",
    items,
    label: "Review evidence packet",
    tone: "ready",
  };
}

function buildPrintReportReliance(report: FTOReport) {
  const reportReference = getReportReference(report);
  const sourceEntries = report.source_health?.entries ?? [];
  const sourceCount =
    sourceEntries.length || report.search_sources_used?.length || 0;
  const materialPatents =
    report.clearance_decision?.decision_audit?.material_patents_reviewed ??
    report.risk_summary.total_patents_analyzed ??
    report.patent_analyses?.length ??
    0;
  const evidenceQuality = report.clearance_decision?.evidence_quality;
  const evidenceQualityPercent = formatEvidenceQualityPercent(evidenceQuality);
  const modelRoleCount = Object.keys(report.llm_models_used ?? {}).length;
  const riskLabel = formatReportRiskLabel(report.risk_summary.overall_risk);
  const sourceLabel =
    sourceCount > 0
      ? `${sourceCount.toLocaleString()} source${sourceCount === 1 ? "" : "s"} in scope`
      : "Source scope not reported";
  const evidenceLabel =
    evidenceQualityPercent !== null
      ? `${evidenceQualityPercent}% decision-evidence score; ${materialPatents.toLocaleString()} material patents`
      : `${materialPatents.toLocaleString()} material patents; decision-evidence score not reported`;

  return [
    {
      label: "Report record",
      value: reportReference,
    },
    {
      label: "Evidence basis",
      value: `${evidenceLabel}. ${sourceLabel}.`,
    },
    {
      label: "AI governance",
      value:
        modelRoleCount > 0
          ? `${modelRoleCount} model roles recorded; cited evidence remains reviewable.`
          : "Model role record not reported; review evidence before reliance.",
    },
    {
      label: "Review gate",
      value: `${riskLabel}; qualified counsel sign-off required before action.`,
    },
  ];
}

function buildPrintReportProvenance(report: FTOReport, sectionLabel: string) {
  const reportReference = getReportReference(report);
  const sourceEntries = report.source_health?.entries ?? [];
  const sourceCount =
    sourceEntries.length || report.search_sources_used?.length || 0;
  const successfulSources = sourceEntries.filter((entry) =>
    isHealthySourceStatus(entry.status),
  ).length;
  const failedSources = sourceEntries.filter(
    (entry) => normalizeSourceHealthStatus(entry.status) === "failed",
  ).length;
  const totalPatentsFound = report.total_patents_found ?? 0;
  const triagedPatents = report.patents_after_triage ?? 0;
  const materialPatents =
    report.clearance_decision?.decision_audit?.material_patents_reviewed ??
    report.risk_summary.total_patents_analyzed ??
    report.patent_analyses?.length ??
    0;
  const evidenceQuality = report.clearance_decision?.evidence_quality;
  const evidenceQualityPercent = formatEvidenceQualityPercent(evidenceQuality);
  const modelRoleCount = Object.keys(report.llm_models_used ?? {}).length;
  const riskLabel = formatReportRiskLabel(report.risk_summary.overall_risk);

  return [
    {
      label: "Print scope",
      value: `Local browser print: ${sectionLabel}`,
      detail:
        "Ungoverned local work product containing only the active report section; use governed export for the complete branded artifact.",
    },
    {
      label: "Report record",
      value: reportReference,
      detail: report.praviar_pipeline_version
        ? `Pipeline ${report.praviar_pipeline_version}`
        : "Pipeline version not reported",
    },
    {
      label: "Source audit",
      value:
        sourceEntries.length > 0
          ? `${successfulSources}/${sourceCount} sources successful`
          : sourceCount > 0
            ? `${sourceCount} sources listed`
            : "Source scope not reported",
      detail:
        sourceEntries.length > 0
          ? `${failedSources} failed; ${triagedPatents.toLocaleString()} triaged from ${totalPatentsFound.toLocaleString()} found`
          : "Verify source coverage before relying on the screening posture",
    },
    {
      label: "AI model record",
      value:
        modelRoleCount > 0
          ? `${modelRoleCount} model roles recorded`
          : "Model record not reported",
      detail: "AI-assisted decision support; counsel judgment remains separate",
    },
    {
      label: "Review posture",
      value: riskLabel,
      detail:
        evidenceQualityPercent !== null
          ? `${evidenceQualityPercent}% decision-evidence score across ${materialPatents.toLocaleString()} material patents; source health is reported separately`
          : `${materialPatents.toLocaleString()} material patents; decision-evidence score not reported`,
    },
  ];
}

function getReportTabPrintLabel(tab: ReportTabId): string {
  const tabConfig = ALL_REPORT_TABS.find((candidate) => candidate.id === tab);
  return tabConfig?.label ?? "Report";
}

function buildEvidenceWorkspaceMeta(
  workspaceSummary?: ReportWorkspaceSummaryResponse | null,
): ChatWorkspaceMetadata | null {
  if (!workspaceSummary) return null;

  const evidenceScope = workspaceSummary.evidence_scope;
  const sourceCount = evidenceScope?.sources_considered?.length ?? 0;
  const jurisdictionCount = workspaceSummary.target_jurisdictions?.length ?? 0;
  const toolAccess = evidenceScope?.external_live_retrieval
    ? ["external_evidence_expand"]
    : [];

  if (evidenceScope?.comment_routing_available) {
    toolAccess.push("review_handoff");
  }

  return {
    trust_mode: workspaceSummary.trust_mode,
    mode_label: formatTrustModeLabel(workspaceSummary.trust_mode),
    capability_label: evidenceScope?.hybrid_evidence_ready
      ? "Hybrid evidence review"
      : "Report-grounded evidence review",
    scope_label:
      jurisdictionCount > 0
        ? `${jurisdictionCount} jurisdiction${jurisdictionCount === 1 ? "" : "s"} in scope`
        : "Report scope",
    source_coverage:
      sourceCount > 0
        ? `${sourceCount} source${sourceCount === 1 ? "" : "s"} considered`
        : "Report-grounded evidence",
    evidence_mode: evidenceScope?.external_live_retrieval
      ? "Hybrid governed evidence"
      : "Report-grounded evidence",
    tool_access: toolAccess,
  };
}

function buildEvidenceSuggestedQueries(
  workspaceSummary?: ReportWorkspaceSummaryResponse | null,
): string[] {
  return (workspaceSummary?.suggested_evidence_queries ?? [])
    .map((item) => item.query?.trim())
    .filter((query): query is string => Boolean(query));
}

function formatTrustModeLabel(value?: string): string {
  const normalized = String(value ?? "")
    .trim()
    .replaceAll("_", " ");
  if (!normalized) return "Report workspace";
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

const ALL_REPORT_TABS: ReportTabConfig[] = [
  ...PRIMARY_TABS,
  ...getOverflowTabs(true),
];

function formatEvidenceQualityPercent(
  value: number | undefined,
): number | null {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return null;
  }

  return Math.round(value <= 1 ? value * 100 : value);
}
