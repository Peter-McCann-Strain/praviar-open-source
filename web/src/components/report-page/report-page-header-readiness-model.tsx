import {
  AlertTriangle,
  DatabaseZap,
  FileCheck2,
  FileLock2,
  Globe2,
  LockKeyhole,
  Share2,
  UserCheck,
  Users,
} from "lucide-react";
import { getReviewLedgerSummary } from "@/components/report/review-ledger-summary";
import {
  getEvidenceQualityMeta,
  type ReportEvidenceFactItem,
} from "@/components/report-page/report-page-header-evidence";
import type {
  ReadinessTone,
  RelianceDecisionQueueItem,
  RelianceReadinessBlocker,
  RelianceReadinessMetric,
  RelianceReadinessModel,
  ReportReviewHandoffDraft,
} from "@/components/report-page/report-page-header-readiness";
import {
  getKnownExportReadinessBlockers,
  getRelianceExportAction,
  getRelianceLifecycleState,
  getReviewerDecisionExportBlockers,
  getReportSourceHealthReadiness,
  getWorkspaceBlockingJurisdictions,
  getWorkspaceExportReady,
  getWorkspaceOpinionSummary,
  type RelianceLifecycleState,
} from "@/components/report-page/report-reliance-readiness";
import type { ReportChatLaunchContext } from "@/components/report/chat-launch-context";
import {
  formatReportRiskLabel,
  getReportReference,
} from "@/components/report-page/report-command-summary";
import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";
import type { ReportWorkspaceSummaryResponse } from "@/hooks/use-report-workspace-summary";
import type { ReviewerDecisionListResponse } from "@/hooks/use-reviewer-decisions";
import type { FTOReport } from "@praviar/shared-types";

export function formatShareViewCount(value: number): string {
  return `${value.toLocaleString()} ${value === 1 ? "view" : "views"}`;
}

type SourceHealthReadiness = ReturnType<typeof getReportSourceHealthReadiness>;
type ExportGateBlocker = ReturnType<
  typeof getKnownExportReadinessBlockers
>[number];

function getExportReadinessLabel({
  blockerCount,
  exportReady,
  hasCaveats,
  hasDangerBlocker,
}: {
  blockerCount: number;
  exportReady: boolean | null;
  hasCaveats: boolean;
  hasDangerBlocker: boolean;
}): string {
  if (hasDangerBlocker) return "Blocked";
  if (blockerCount > 0) return "Requires confirmation";
  if (exportReady === true) return hasCaveats ? "Ready with caveats" : "Ready";
  return exportReady === false ? "Blocked" : "Requires confirmation";
}

function getExportContextValue({
  blockerCount,
  exportReady,
  hasCaveats,
  hasDangerBlocker,
}: {
  blockerCount: number;
  exportReady: boolean | null;
  hasCaveats: boolean;
  hasDangerBlocker: boolean;
}): "blocked" | "caveat" | "ready" | "verify" {
  if (hasDangerBlocker || exportReady === false) return "blocked";
  if (blockerCount > 0) return "verify";
  if (exportReady !== true) return "verify";
  return hasCaveats ? "caveat" : "ready";
}

function buildReadinessBlockers({
  combinedExportGateBlockerCount,
  exportReady,
  isReviewApproved,
  panelExportGateBlockers,
  reviewerProgressLabel,
  reviewStatus,
  sourceHealthReadiness,
}: {
  combinedExportGateBlockerCount: number;
  exportReady: boolean | null;
  isReviewApproved: boolean;
  panelExportGateBlockers: ExportGateBlocker[];
  reviewerProgressLabel: string;
  reviewStatus?: AnalysisReviewStatusResponse;
  sourceHealthReadiness: SourceHealthReadiness;
}): RelianceReadinessBlocker[] {
  const blockers: RelianceReadinessBlocker[] = [];

  if (isReviewApproved) {
    blockers.push({
      icon: <UserCheck className="h-4 w-4" />,
      label: "Counsel review recorded",
      detail:
        "Reviewer approval is recorded; legal context still travels with the packet.",
      tone: "success",
    });
  } else if (reviewStatus) {
    blockers.push({
      icon: <UserCheck className="h-4 w-4" />,
      label: "Counsel review required",
      detail: `${reviewerProgressLabel}.`,
      tone: "danger",
    });
  } else {
    blockers.push({
      icon: <UserCheck className="h-4 w-4" />,
      label: "Counsel review required",
      detail: "Reviewer judgment remains separate from AI screening.",
      tone: "warning",
    });
  }

  if (panelExportGateBlockers.length > 0) {
    blockers.push(
      ...panelExportGateBlockers.map((blocker) => ({
        icon: <LockKeyhole className="h-4 w-4" />,
        label: blocker.label,
        detail: blocker.detail,
        tone: blocker.tone,
      })),
    );
  } else if (combinedExportGateBlockerCount === 0 && exportReady === true) {
    blockers.push({
      icon: <FileCheck2 className="h-4 w-4" />,
      label: "Export review ready",
      detail: sourceHealthReadiness.hasCaveats
        ? "Backend readiness indicates export can proceed with attached source caveats."
        : "Backend readiness indicates export can proceed.",
      tone: "success",
    });
  } else {
    blockers.push({
      icon: <LockKeyhole className="h-4 w-4" />,
      label: "Export readiness unknown",
      detail: "Open export to confirm backend readiness before relying on it.",
      tone: "warning",
    });
  }

  blockers.push(
    sourceHealthReadiness.hasCaveats
      ? {
          icon: <AlertTriangle className="h-4 w-4" />,
          label: "Share caveats",
          detail: sourceHealthReadiness.detail,
          tone: sourceHealthReadiness.tone,
        }
      : {
          icon: <Share2 className="h-4 w-4" />,
          label: "Share caveats",
          detail: "Shared views remain read-only screening artifacts.",
          tone: "warning",
        },
  );

  return blockers;
}

function getReadinessStatus({
  blockers,
  evidenceQualityTone,
  exportReady,
  hasSourceCaveats,
  isReviewApproved,
}: {
  blockers: RelianceReadinessBlocker[];
  evidenceQualityTone: ReportEvidenceFactItem["tone"];
  exportReady: boolean | null;
  hasSourceCaveats: boolean;
  isReviewApproved: boolean;
}): { label: string; tone: ReadinessTone } {
  if (
    exportReady === false ||
    blockers.some((blocker) => blocker.tone === "danger")
  ) {
    return { label: "Not ready for reliance", tone: "danger" };
  }
  if (isReviewApproved && hasSourceCaveats) {
    return { label: "Counsel-approved with caveats", tone: "warning" };
  }
  if (isReviewApproved) {
    return { label: "Counsel review recorded", tone: "success" };
  }
  return {
    label: "Counsel review required",
    tone: evidenceQualityTone === "warning" ? "warning" : "neutral",
  };
}

function buildReadinessAiContext({
  blockers,
  compoundName,
  decisionQueue,
  exportContextValue,
  lifecycleState,
  reportReference,
  reviewerPct,
  sourceHealthReadiness,
  targetJurisdictions,
}: {
  blockers: RelianceReadinessBlocker[];
  compoundName: string;
  decisionQueue: RelianceDecisionQueueItem[];
  exportContextValue: string;
  lifecycleState: RelianceLifecycleState;
  reportReference: string;
  reviewerPct: number | null;
  sourceHealthReadiness: SourceHealthReadiness;
  targetJurisdictions: string[];
}): ReportChatLaunchContext {
  return {
    actionLabel: "Check reliance gaps",
    description:
      "Opened from the report readiness console with blockers, source audit, jurisdiction, and review state attached.",
    intent: "report",
    metadata: [
      { label: "Report", value: reportReference },
      { label: "Compound", value: compoundName },
      { label: "Reliance state", value: lifecycleState.label },
      { label: "Reliance owner", value: lifecycleState.owner },
      { label: "Export", value: exportContextValue },
      {
        label: "Review",
        value:
          reviewerPct !== null
            ? `${reviewerPct.toLocaleString()}% complete`
            : "not approved",
      },
      {
        label: "Readiness blockers",
        value: formatReadinessBlockersForAi(blockers),
      },
      {
        label: "Decision queue",
        value: formatDecisionQueueForAi(decisionQueue),
      },
      { label: "Source audit", value: sourceHealthReadiness.value },
      {
        label: "Jurisdictions",
        value: targetJurisdictions.length
          ? targetJurisdictions.join(", ")
          : "not reported",
      },
    ],
    prompt: `Critique the reliance readiness for ${compoundName}. Start with export readiness, counsel review status, source-health caveats, material blockers, jurisdiction scope, and unresolved uncertainty. Return prioritized gaps and next actions for counsel handoff, using only this generated report packet. Do not present the critique as independent verification.`,
    title: `${compoundName} reliance gaps`,
  };
}

function buildReadinessMetrics({
  blockingJurisdictionCount,
  evidenceScope,
  reviewerPct,
  reviewerProgressLabel,
  reviewStatus,
  sourceCoverage,
  sourceHealthReadiness,
  targetJurisdictions,
  uncertaintyCount,
}: {
  blockingJurisdictionCount: number;
  evidenceScope: ReportWorkspaceSummaryResponse["evidence_scope"] | undefined;
  reviewerPct: number | null;
  reviewerProgressLabel: string;
  reviewStatus?: AnalysisReviewStatusResponse;
  sourceCoverage: number | null;
  sourceHealthReadiness: SourceHealthReadiness;
  targetJurisdictions: string[];
  uncertaintyCount: number;
}): RelianceReadinessMetric[] {
  return [
    {
      icon: <FileLock2 className="h-4 w-4" />,
      label: "Evidence scope",
      value: evidenceScope?.external_live_retrieval
        ? "Hybrid evidence"
        : "Report evidence",
      detail: evidenceScope?.governed_note || "Report-grounded evidence only.",
      tone: evidenceScope?.external_live_retrieval ? "warning" : "neutral",
    },
    {
      icon: <DatabaseZap className="h-4 w-4" />,
      label: "Source coverage",
      value: sourceCoverage == null ? "Not reported" : `${sourceCoverage}%`,
      detail:
        sourceCoverage == null
          ? "Source health not reported."
          : sourceHealthReadiness.detail,
      tone: sourceCoverage == null ? "warning" : sourceHealthReadiness.tone,
    },
    {
      icon: <Globe2 className="h-4 w-4" />,
      label: "Jurisdictions",
      value:
        targetJurisdictions.length > 0
          ? `${targetJurisdictions.length} in scope`
          : "Report scope",
      detail:
        targetJurisdictions.length > 0
          ? targetJurisdictions.slice(0, 6).join(", ")
          : "No target jurisdictions reported.",
      tone: blockingJurisdictionCount > 0 ? "warning" : "neutral",
    },
    {
      icon: <Users className="h-4 w-4" />,
      label: "Reviewer progress",
      value: reviewerPct == null ? "Not started" : `${reviewerPct}%`,
      detail:
        reviewStatus != null
          ? `${reviewerProgressLabel}.`
          : `${uncertaintyCount.toLocaleString()} uncertainty ${uncertaintyCount === 1 ? "item" : "items"} tracked.`,
      tone:
        reviewStatus?.status === "approved"
          ? "success"
          : reviewerPct != null && reviewerPct > 0
            ? "warning"
            : "neutral",
    },
  ];
}

export function getRelianceReadinessModel({
  analysisId,
  report,
  shareActive,
  shareRecipientBound,
  reviewStatus,
  reviewStatusLoading,
  reviewerDecisions,
  reviewerDecisionsLoading,
  workspaceSummary,
  workspaceSummaryLoading,
}: {
  analysisId: string;
  report: FTOReport;
  shareActive?: boolean;
  shareRecipientBound?: boolean;
  reviewerDecisions?: ReviewerDecisionListResponse | null;
  reviewerDecisionsLoading?: boolean;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
  workspaceSummary?: ReportWorkspaceSummaryResponse;
  workspaceSummaryLoading?: boolean;
}): RelianceReadinessModel {
  const sourceHealthReadiness = getReportSourceHealthReadiness(report);
  const evidenceQuality = getEvidenceQualityMeta(
    report.clearance_decision?.evidence_quality,
  );
  const exportReady = getWorkspaceExportReady(workspaceSummary);
  const blockingJurisdictions =
    getWorkspaceBlockingJurisdictions(workspaceSummary);
  const exportGateBlockers = getKnownExportReadinessBlockers({
    reviewStatus,
    reviewStatusLoading,
    workspaceSummary,
    workspaceSummaryLoading,
  });
  const reviewerDecisionBlockers = getReviewerDecisionExportBlockers({
    report,
    reviewStatus,
    reviewerDecisions,
    reviewerDecisionsLoading,
  });
  const combinedExportGateBlockers = [
    ...exportGateBlockers,
    ...reviewerDecisionBlockers,
  ];
  const panelExportGateBlockers = combinedExportGateBlockers.filter(
    (blocker) =>
      !(
        blocker.label === "Counsel review required" &&
        reviewStatus != null &&
        reviewStatus.status !== "approved"
      ),
  );
  const targetJurisdictions = getWorkspaceJurisdictions(
    workspaceSummary,
    report,
  );
  const uncertaintyCount = workspaceSummary?.uncertainty_register?.length ?? 0;
  const evidenceScope = workspaceSummary?.evidence_scope;
  const reviewLedger = getReviewLedgerSummary({
    reviewStatus,
    loading: reviewStatusLoading,
    uncertaintyCount,
  });
  const compoundName = report.compound?.name ?? "this compound";
  const reportReference = getReportReference(report);
  const sourceCoverage =
    sourceHealthReadiness.totalCount > 0
      ? Math.round(
          (sourceHealthReadiness.okCount / sourceHealthReadiness.totalCount) *
            100,
        )
      : null;
  const reviewerPct =
    typeof reviewStatus?.completion_pct === "number"
      ? Math.round(reviewStatus.completion_pct)
      : null;
  const riskLabel = formatReportRiskLabel(report.risk_summary.overall_risk);
  const hasDangerExportGateBlocker = combinedExportGateBlockers.some(
    (blocker) => blocker.tone === "danger",
  );
  const exportReadinessLabel = getExportReadinessLabel({
    blockerCount: combinedExportGateBlockers.length,
    exportReady,
    hasCaveats: sourceHealthReadiness.hasCaveats,
    hasDangerBlocker: hasDangerExportGateBlocker,
  });
  const exportContextValue = getExportContextValue({
    blockerCount: combinedExportGateBlockers.length,
    exportReady,
    hasCaveats: sourceHealthReadiness.hasCaveats,
    hasDangerBlocker: hasDangerExportGateBlocker,
  });
  const exportAction = getRelianceExportAction({
    additionalBlockers: reviewerDecisionBlockers,
    report,
    reviewStatus,
    reviewStatusLoading,
    workspaceSummary,
    workspaceSummaryLoading,
  });
  const reviewerProgressLabel =
    reviewLedger.detailLabel ??
    `${uncertaintyCount.toLocaleString()} uncertainty ${
      uncertaintyCount === 1 ? "item" : "items"
    } tracked`;
  const evidenceScopeLabel = evidenceScope?.external_live_retrieval
    ? "Hybrid evidence"
    : "Report evidence";
  const isReviewApproved = reviewStatus?.status === "approved";
  const lifecycleState = getRelianceLifecycleState({
    additionalBlockers: reviewerDecisionBlockers,
    report,
    shareActive,
    shareRecipientBound,
    reviewStatus,
    reviewStatusLoading,
    workspaceSummary,
    workspaceSummaryLoading,
  });
  const blockers = buildReadinessBlockers({
    combinedExportGateBlockerCount: combinedExportGateBlockers.length,
    exportReady,
    isReviewApproved,
    panelExportGateBlockers,
    reviewerProgressLabel,
    reviewStatus,
    sourceHealthReadiness,
  });

  const headline =
    exportReady === false
      ? (getWorkspaceOpinionSummary(workspaceSummary) ??
        "Resolve blockers below before export or downstream reliance.")
      : "Track blockers, evidence scope, and counsel handoff before downstream reliance.";
  const readinessStatus = getReadinessStatus({
    blockers,
    evidenceQualityTone: evidenceQuality.tone,
    exportReady,
    hasSourceCaveats: sourceHealthReadiness.hasCaveats,
    isReviewApproved,
  });
  const decisionQueue = buildRelianceDecisionQueue({
    blockers,
    exportReady,
    lifecycleState,
    reviewApproved: isReviewApproved,
    reviewerProgressLabel,
    sourceHealthReadiness,
  });
  const handoffDraft = buildRelianceHandoffDraft({
    analysisId,
    blockingJurisdictions,
    blockers,
    decisionQueue,
    compoundName,
    evidenceScopeLabel,
    evidenceScopeNote:
      evidenceScope?.governed_note || "Report-grounded evidence only.",
    exportReadinessLabel,
    headline,
    lifecycleState,
    reportReference,
    reviewerProgressLabel,
    riskLabel,
    sourceAudit: `${sourceHealthReadiness.value} - ${sourceHealthReadiness.detail}`,
    statusLabel: readinessStatus.label,
    uncertaintyCount,
  });

  return {
    aiContext: buildReadinessAiContext({
      blockers,
      compoundName,
      decisionQueue,
      exportContextValue,
      lifecycleState,
      reportReference,
      reviewerPct,
      sourceHealthReadiness,
      targetJurisdictions,
    }),
    blockers,
    decisionQueue,
    exportAction,
    handoffDraft,
    headline,
    lifecycleState,
    metrics: buildReadinessMetrics({
      blockingJurisdictionCount: blockingJurisdictions.length,
      evidenceScope,
      reviewerPct,
      reviewerProgressLabel,
      reviewStatus,
      sourceCoverage,
      sourceHealthReadiness,
      targetJurisdictions,
      uncertaintyCount,
    }),
    statusLabel: readinessStatus.label,
    statusTone: readinessStatus.tone,
  };
}

function buildRelianceHandoffDraft({
  analysisId,
  blockingJurisdictions,
  blockers,
  decisionQueue,
  compoundName,
  evidenceScopeLabel,
  evidenceScopeNote,
  exportReadinessLabel,
  headline,
  lifecycleState,
  reportReference,
  reviewerProgressLabel,
  riskLabel,
  sourceAudit,
  statusLabel,
  uncertaintyCount,
}: {
  analysisId: string;
  blockingJurisdictions: string[];
  blockers: RelianceReadinessBlocker[];
  decisionQueue: RelianceDecisionQueueItem[];
  compoundName: string;
  evidenceScopeLabel: string;
  evidenceScopeNote: string;
  exportReadinessLabel: string;
  headline: string;
  lifecycleState: RelianceLifecycleState;
  reportReference: string;
  reviewerProgressLabel: string;
  riskLabel: string;
  sourceAudit: string;
  statusLabel: string;
  uncertaintyCount: number;
}): ReportReviewHandoffDraft {
  const blockerLines =
    blockers.length > 0
      ? blockers.map((blocker) => `  - ${blocker.label}: ${blocker.detail}`)
      : ["  - No readiness blockers surfaced in the current model."];
  const jurisdictionLine =
    blockingJurisdictions.length > 0
      ? blockingJurisdictions.join(", ")
      : "None reported";
  const decisionLines =
    decisionQueue.length > 0
      ? decisionQueue.map(
          (item) =>
            `  - ${item.priority} ${item.label} (${item.owner}): ${item.detail} Basis: ${item.evidence}. Done: ${item.completion}`,
        )
      : ["  - No decision actions surfaced in the current model."];
  const uncertaintyLabel = `${uncertaintyCount.toLocaleString()} uncertainty ${
    uncertaintyCount === 1 ? "item" : "items"
  }`;

  return {
    body: [
      `**Praviar reliance handoff**`,
      `Report: ${reportReference}`,
      `Compound: ${compoundName}`,
      `Risk: ${riskLabel}`,
      `Readiness: ${statusLabel}`,
      `Reliance state: ${lifecycleState.label}`,
      `Reliance owner: ${lifecycleState.owner}`,
      `Current blocker: ${lifecycleState.blocker}`,
      `Next action: ${lifecycleState.nextAction}`,
      `Summary: ${headline}`,
      "",
      `Decision queue:`,
      ...decisionLines,
      "",
      `Readiness blockers:`,
      ...blockerLines,
      "",
      `Export readiness: ${exportReadinessLabel}`,
      `Blocking jurisdictions: ${jurisdictionLine}`,
      `Source audit: ${sourceAudit}`,
      `Reviewer progress: ${reviewerProgressLabel}`,
      `Evidence scope: ${evidenceScopeLabel} - ${evidenceScopeNote}`,
      `Uncertainty register: ${uncertaintyLabel}`,
      "",
      "Counsel next action: review blockers, source caveats, jurisdiction scope, and unresolved uncertainty before downstream reliance.",
    ].join("\n"),
    promote_to_under_review: true,
    review_note: `Reliance handoff created from report readiness console for ${compoundName}. ${statusLabel}; ${reviewerProgressLabel}.`,
    target_id: analysisId,
    target_type: "analysis",
  };
}

function buildRelianceDecisionQueue({
  blockers,
  exportReady,
  lifecycleState,
  reviewApproved,
  reviewerProgressLabel,
  sourceHealthReadiness,
}: {
  blockers: RelianceReadinessBlocker[];
  exportReady: boolean | null;
  lifecycleState: RelianceLifecycleState;
  reviewApproved: boolean;
  reviewerProgressLabel: string;
  sourceHealthReadiness: ReturnType<typeof getReportSourceHealthReadiness>;
}): RelianceDecisionQueueItem[] {
  const items: RelianceDecisionQueueItem[] = [
    {
      completion:
        lifecycleState.tone === "success"
          ? "Governed packet or review handoff is ready to proceed."
          : "Readiness check returns no P1 blockers.",
      detail: lifecycleState.nextAction,
      evidence: `Gate: ${lifecycleState.label}`,
      label: "Next required action",
      owner: lifecycleState.owner,
      priority: lifecycleState.tone === "danger" ? "P1" : "P2",
      tone: lifecycleState.tone,
    },
  ];
  const materialBlocker =
    blockers.find((blocker) => blocker.tone === "danger") ??
    blockers.find((blocker) => blocker.tone === "warning");

  if (materialBlocker) {
    items.push({
      completion:
        materialBlocker.tone === "danger"
          ? "Blocking signal is cleared or explicitly accepted by counsel."
          : "Caveat is resolved or travels in the governed packet.",
      detail: materialBlocker.detail,
      evidence: "Signal: readiness blockers",
      label: materialBlocker.label,
      owner: materialBlocker.label.includes("Counsel")
        ? "Reviewer / counsel"
        : "Report owner",
      priority: materialBlocker.tone === "danger" ? "P1" : "P2",
      tone: materialBlocker.tone,
    });
  }

  if (!reviewApproved) {
    items.push({
      completion:
        "Reviewer status is approved and material findings are closed.",
      detail: reviewerProgressLabel,
      evidence: "Reviewer ledger",
      label: "Counsel review",
      owner: "Reviewer / counsel",
      priority: "P1",
      tone: "danger",
    });
  }

  if (sourceHealthReadiness.hasCaveats) {
    items.push({
      completion:
        "Skipped or failed sources are resolved or caveated in export.",
      detail: sourceHealthReadiness.detail,
      evidence: `Source audit: ${sourceHealthReadiness.value}`,
      label: "Source audit",
      owner: "Report owner",
      priority: sourceHealthReadiness.tone === "danger" ? "P1" : "P2",
      tone: sourceHealthReadiness.tone,
    });
  } else if (exportReady === true && reviewApproved) {
    items.push({
      completion: "Generated export includes the manifest receipt and caveats.",
      detail: "Generate the governed export or create a controlled share link.",
      evidence: "Backend readiness cleared",
      label: "Governed export",
      owner: "Report owner",
      priority: "P3",
      tone: "success",
    });
  }

  const seen = new Set<string>();
  return items
    .filter((item) => {
      const key = `${item.label}:${item.detail}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 3);
}

function formatReadinessBlockersForAi(
  blockers: RelianceReadinessBlocker[],
): string {
  if (blockers.length === 0) return "none surfaced";
  const label = blockers
    .map((blocker) => `${blocker.label}: ${blocker.detail}`)
    .join("; ");
  return label.length <= 500 ? label : `${label.slice(0, 497)}...`;
}

function formatDecisionQueueForAi(
  decisionQueue: RelianceDecisionQueueItem[],
): string {
  if (decisionQueue.length === 0) return "none surfaced";
  const label = decisionQueue
    .map(
      (item) =>
        `${item.priority} ${item.label} (${item.owner}): ${item.detail} Basis: ${item.evidence}. Done: ${item.completion}`,
    )
    .join("; ");
  return label.length <= 500 ? label : `${label.slice(0, 497)}...`;
}

function getWorkspaceJurisdictions(
  workspaceSummary: ReportWorkspaceSummaryResponse | undefined,
  report: FTOReport,
): string[] {
  const reportWithJurisdictions = report as FTOReport & {
    jurisdiction_decisions?: Array<{ jurisdiction?: string | null }>;
  };
  const values = [
    ...(workspaceSummary?.target_jurisdictions ?? []),
    ...(reportWithJurisdictions.jurisdiction_decisions?.map(
      (entry) => entry.jurisdiction,
    ) ?? []),
  ];
  const seen = new Set<string>();
  return values.flatMap((value) => {
    const jurisdiction = String(value ?? "")
      .trim()
      .toUpperCase();
    if (!jurisdiction || seen.has(jurisdiction)) return [];
    seen.add(jurisdiction);
    return [jurisdiction];
  });
}
