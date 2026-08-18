import type { AnalysisReviewStatusResponse } from "@/hooks/use-analysis-review-status";
import type { ReportWorkspaceSummaryResponse } from "@/hooks/use-report-workspace-summary";

export type RelianceReadinessTone =
  | "success"
  | "warning"
  | "danger"
  | "neutral";

export interface RelianceReadinessBlocker {
  detail: string;
  label: string;
  tone: RelianceReadinessTone;
}

export interface RelianceReadinessInput {
  additionalBlockers?: RelianceReadinessBlocker[];
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewStatusLoading?: boolean;
  workspaceSummary?: ReportWorkspaceSummaryResponse;
  workspaceSummaryLoading?: boolean;
}

export type RelianceLifecycleStageId =
  | "not_reviewable"
  | "ready_for_qa"
  | "counsel_approved"
  | "exportable"
  | "externally_shareable";

export interface RelianceLifecycleState {
  blocker: string;
  detail: string;
  id: RelianceLifecycleStageId;
  label: string;
  nextAction: string;
  owner: string;
  tone: RelianceReadinessTone;
}

export interface RelianceLifecycleInput extends RelianceReadinessInput {
  report?: SourceHealthReportLike;
  shareActive?: boolean;
  shareRecipientBound?: boolean;
}

export type RelianceExportActionTone =
  | "blocked"
  | "caveat"
  | "ready"
  | "verify";

export interface RelianceExportAction {
  ariaLabel: string;
  detail?: string;
  label: string;
  tone: RelianceExportActionTone;
}

export interface SourceHealthEntryLike {
  source?: string | null;
  status?: string | null;
}

export interface SourceHealthReportLike {
  analyses?: unknown[] | null;
  claim_source_span_map?: {
    entries?: unknown[] | null;
  } | null;
  patent_analyses?: unknown[] | null;
  patents?: unknown[] | null;
  search_sources_used?: unknown[] | null;
  source_health?: {
    entries?: SourceHealthEntryLike[] | null;
  } | null;
}

export interface ReviewerDecisionLike {
  decision?: string | null;
  finding_ref?: string | null;
  finding_type?: string | null;
  reviewer_user_id?: string | null;
}

export interface ReviewerDecisionListLike {
  items?: ReviewerDecisionLike[] | null;
}

interface ExportRequiredFindingReview {
  displayRef: string;
  findingRef: string;
  findingType: "patent" | "claim_element";
  requiredReviews: number;
  riskLevel: "high" | "medium";
}

export interface SourceHealthReadiness {
  detail: string;
  hasCaveats: boolean;
  okCount: number;
  status: "Included" | "Caveated" | "Verify";
  tone: Exclude<RelianceReadinessTone, "neutral">;
  totalCount: number;
  value: string;
}

type NormalizedSourceHealthStatus =
  | "healthy"
  | "failed"
  | "skipped"
  | "not_configured"
  | "unknown";

export function normalizeSourceHealthStatus(
  status?: string | null,
): NormalizedSourceHealthStatus {
  const normalized = String(status ?? "")
    .trim()
    .toLowerCase();

  if (["ok", "success", "healthy", "available"].includes(normalized)) {
    return "healthy";
  }
  if (["failed", "error", "unavailable"].includes(normalized)) {
    return "failed";
  }
  if (normalized === "skipped") {
    return "skipped";
  }
  if (normalized === "not_configured" || normalized === "not configured") {
    return "not_configured";
  }
  return "unknown";
}

export function isHealthySourceStatus(status?: string | null) {
  return normalizeSourceHealthStatus(status) === "healthy";
}

export function getWorkspaceExportReady(
  workspaceSummary?: ReportWorkspaceSummaryResponse,
): boolean | null {
  const value = workspaceSummary?.opinion_readiness?.export_ready;
  return typeof value === "boolean" ? value : null;
}

function hasMalformedWorkspaceExportReady(
  workspaceSummary?: ReportWorkspaceSummaryResponse,
): boolean {
  const value = workspaceSummary?.opinion_readiness?.export_ready;
  return value !== undefined && typeof value !== "boolean";
}

export function getWorkspaceOpinionSummary(
  workspaceSummary?: ReportWorkspaceSummaryResponse,
): string | null {
  const value = workspaceSummary?.opinion_readiness?.summary;
  return typeof value === "string" && value.trim() ? value : null;
}

export function getWorkspaceBlockingJurisdictions(
  workspaceSummary?: ReportWorkspaceSummaryResponse,
): string[] {
  const value =
    workspaceSummary?.opinion_readiness?.jurisdictions_blocking_export;
  return Array.isArray(value)
    ? value
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean)
    : [];
}

export function getKnownExportReadinessBlockers({
  reviewStatus,
  reviewStatusLoading,
  workspaceSummary,
  workspaceSummaryLoading,
}: RelianceReadinessInput): RelianceReadinessBlocker[] {
  const exportReady = getWorkspaceExportReady(workspaceSummary);
  const blockingJurisdictions =
    getWorkspaceBlockingJurisdictions(workspaceSummary);
  const trustMode =
    typeof workspaceSummary?.trust_mode === "string"
      ? workspaceSummary.trust_mode.trim().toLowerCase()
      : null;
  const blockers: RelianceReadinessBlocker[] = [];
  const workspaceVerificationPending =
    Boolean(workspaceSummaryLoading) && !workspaceSummary;
  const reviewVerificationPending =
    Boolean(reviewStatusLoading) && !reviewStatus;
  const malformedExportReady =
    hasMalformedWorkspaceExportReady(workspaceSummary);

  if (!workspaceSummary) {
    blockers.push({
      label: workspaceVerificationPending
        ? "Readiness verification in progress"
        : "Export readiness unavailable",
      detail: workspaceVerificationPending
        ? "Wait for readiness verification before exporting."
        : "Readiness verification has not loaded yet.",
      tone: "warning",
    });
  } else if (trustMode !== "counsel") {
    blockers.push({
      label: "Counsel export mode required",
      detail: `Current trust mode is ${trustMode || "explorer"}, not counsel.`,
      tone: "danger",
    });
  } else if (malformedExportReady) {
    blockers.push({
      label: "Export readiness malformed",
      detail:
        "Backend export readiness did not return a boolean value, so export remains blocked.",
      tone: "danger",
    });
  }

  if (
    !workspaceVerificationPending &&
    !malformedExportReady &&
    (exportReady !== true || blockingJurisdictions.length > 0)
  ) {
    blockers.push({
      label:
        exportReady === false
          ? "Export blocked"
          : "Export readiness incomplete",
      detail:
        blockingJurisdictions.length > 0
          ? `${blockingJurisdictions.join(", ")} ${
              blockingJurisdictions.length === 1 ? "lane blocks" : "lanes block"
            } export.`
          : exportReady === false
            ? (getWorkspaceOpinionSummary(workspaceSummary) ??
              "Opinion readiness is not cleared for export.")
            : "Lane certification or clearance-grade evidence is still incomplete for export.",
      tone: exportReady === false ? "danger" : "warning",
    });
  }

  if (!reviewStatus) {
    blockers.push({
      label: reviewVerificationPending
        ? "Review status verification in progress"
        : "Persisted legal review required",
      detail: reviewVerificationPending
        ? "Wait for persisted legal review verification before exporting."
        : "Persisted legal review status is pending, not approved.",
      tone: reviewVerificationPending ? "warning" : "danger",
    });
  } else if (reviewStatus.status !== "approved") {
    blockers.push({
      label: "Counsel review required",
      detail: `${reviewStatus.findings_reviewed.toLocaleString()} / ${reviewStatus.findings_total.toLocaleString()} findings reviewed.`,
      tone: "danger",
    });
  }

  return blockers;
}

export function getCombinedExportReadinessBlockers(
  input: RelianceReadinessInput,
): RelianceReadinessBlocker[] {
  return [
    ...getKnownExportReadinessBlockers(input),
    ...(input.additionalBlockers ?? []),
  ];
}

export function isKnownExportBlocked(input: RelianceReadinessInput): boolean {
  return getCombinedExportReadinessBlockers(input).length > 0;
}

export function getExportDisabledReason(
  input: RelianceReadinessInput,
): string | null {
  const blockers = getCombinedExportReadinessBlockers(input);
  if (blockers.length === 0) return null;
  return blockers.map((blocker) => blocker.detail).join(" ");
}

export function getReviewerDecisionExportBlockers({
  report,
  reviewStatus,
  reviewerDecisions,
  reviewerDecisionsLoading,
}: {
  report?: SourceHealthReportLike | null;
  reviewStatus?: AnalysisReviewStatusResponse;
  reviewerDecisions?: ReviewerDecisionListLike | null;
  reviewerDecisionsLoading?: boolean;
}): RelianceReadinessBlocker[] {
  if (reviewStatus?.status !== "approved") return [];

  const requiredReviews = getExportRequiredFindingReviews(report);
  if (requiredReviews.length === 0) return [];

  if (reviewerDecisionsLoading && !reviewerDecisions) {
    return [
      {
        label: "Reviewer decision ledger loading",
        detail:
          "Wait for material-finding reviewer decisions before exporting.",
        tone: "warning",
      },
    ];
  }

  if (!reviewerDecisions) {
    return [
      {
        label: "Reviewer decisions unavailable",
        detail:
          "Material findings need reviewer decisions before export readiness can be trusted.",
        tone: "danger",
      },
    ];
  }

  const decisionsByFinding = new Map<string, Set<string>>();
  for (const decision of reviewerDecisions.items ?? []) {
    const decisionValue = normalizeDecisionText(decision.decision);
    if (!["accept", "reject", "edit"].includes(decisionValue)) continue;

    const findingType = normalizeDecisionText(decision.finding_type);
    const findingRef = normalizeKeyText(decision.finding_ref);
    const reviewerId = normalizeDecisionText(decision.reviewer_user_id);
    if (!findingType || !findingRef || !reviewerId) continue;

    const key = `${findingType}:${findingRef}`;
    const reviewerIds = decisionsByFinding.get(key) ?? new Set<string>();
    reviewerIds.add(reviewerId);
    decisionsByFinding.set(key, reviewerIds);
  }

  const missing = requiredReviews.flatMap((finding) => {
    const reviewerIds =
      decisionsByFinding.get(`${finding.findingType}:${finding.findingRef}`) ??
      new Set<string>();
    if (reviewerIds.size === 0) {
      return [
        `${finding.riskLevel.toUpperCase()} finding ${finding.displayRef} has no reviewer decision.`,
      ];
    }
    if (reviewerIds.size < finding.requiredReviews) {
      return [
        `${finding.riskLevel.toUpperCase()} finding ${finding.displayRef} requires dual review before export.`,
      ];
    }
    return [];
  });

  if (missing.length === 0) return [];

  const visibleMissing = missing.slice(0, 2).join(" ");
  const remainingCount = missing.length - 2;
  const remainder =
    remainingCount > 0
      ? ` ${remainingCount} more material ${
          remainingCount === 1 ? "finding needs" : "findings need"
        } review.`
      : "";

  return [
    {
      label: "Reviewer decisions incomplete",
      detail: `${visibleMissing}${remainder}`,
      tone: "danger",
    },
  ];
}

function getExportRequiredFindingReviews(
  report?: SourceHealthReportLike | null,
): ExportRequiredFindingReview[] {
  if (!report || typeof report !== "object") return [];

  const findingsByKey = new Map<string, ExportRequiredFindingReview>();
  const patentCandidates = Array.isArray(report.patent_analyses)
    ? report.patent_analyses
    : Array.isArray(report.patents)
      ? report.patents
      : Array.isArray(report.analyses)
        ? report.analyses
        : [];

  for (const entry of patentCandidates) {
    if (!entry || typeof entry !== "object") continue;
    const record = entry as Record<string, unknown>;
    const riskLevel = normalizeDecisionText(record.risk_level);
    if (riskLevel !== "high" && riskLevel !== "medium") continue;

    const findingRef =
      recordString(record, "patent_id") ||
      recordString(record, "id") ||
      recordString(record, "publication_number") ||
      recordString(record, "patent_number");
    if (!findingRef) continue;

    const key = `patent:${findingRef}`;
    const existing = findingsByKey.get(key);
    if (existing && existing.riskLevel === "high") continue;

    findingsByKey.set(key, {
      displayRef: findingRef,
      findingRef,
      findingType: "patent",
      requiredReviews: riskLevel === "high" ? 2 : 1,
      riskLevel,
    });
  }

  const sourceEntries = Array.isArray(report.claim_source_span_map?.entries)
    ? report.claim_source_span_map.entries
    : [];
  for (const entry of sourceEntries) {
    if (!entry || typeof entry !== "object") continue;
    const record = entry as Record<string, unknown>;
    const findingRef = recordString(record, "assertion_id");
    if (!findingRef) continue;

    const supportStatus = normalizeDecisionText(record.support_status);
    const customerVisible = record.customer_visible !== false;
    const reviewRequired =
      record.review_required === true || supportStatus === "needs_review";
    if (!customerVisible || !reviewRequired) continue;

    const key = `claim_element:${findingRef}`;
    if (findingsByKey.has(key)) continue;
    findingsByKey.set(key, {
      displayRef: findingRef,
      findingRef,
      findingType: "claim_element",
      requiredReviews: 1,
      riskLevel: "medium",
    });
  }

  return Array.from(findingsByKey.values()).sort((left, right) => {
    const typeCompare = left.findingType.localeCompare(right.findingType);
    if (typeCompare !== 0) return typeCompare;
    return left.findingRef.localeCompare(right.findingRef);
  });
}

function normalizeDecisionText(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase();
}

function normalizeKeyText(value: unknown): string {
  return String(value ?? "").trim();
}

function recordString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value.trim() : "";
}

export function getRelianceExportAction({
  additionalBlockers,
  report,
  ...input
}: RelianceReadinessInput & {
  report?: SourceHealthReportLike;
}): RelianceExportAction {
  const blockers = getCombinedExportReadinessBlockers({
    ...input,
    additionalBlockers,
  });
  const firstBlocker = blockers[0];
  const firstDangerBlocker = blockers.find(
    (blocker) => blocker.tone === "danger",
  );
  const sourceHealth = getReportSourceHealthReadiness(report);

  if (firstDangerBlocker) {
    return {
      ariaLabel: "Review export blockers before exporting evidence packet",
      detail: firstDangerBlocker.label,
      label: "Review export blockers",
      tone: "blocked",
    };
  }

  if (firstBlocker) {
    return {
      ariaLabel: "Verify export readiness before exporting evidence packet",
      detail: firstBlocker.label,
      label: "Verify export readiness",
      tone: "verify",
    };
  }

  if (sourceHealth.hasCaveats) {
    return {
      ariaLabel: "Prepare evidence packet export with source caveat",
      detail: sourceHealth.detail,
      label: "Prepare export with source caveat",
      tone: "caveat",
    };
  }

  return {
    ariaLabel: "Export evidence packet",
    detail: "Source audit complete",
    label: "Export evidence packet",
    tone: "ready",
  };
}

export function getRelianceLifecycleState({
  report,
  shareActive,
  shareRecipientBound,
  ...input
}: RelianceLifecycleInput): RelianceLifecycleState {
  const blockers = getCombinedExportReadinessBlockers(input);
  const exportReady = getWorkspaceExportReady(input.workspaceSummary);
  const sourceHealth = getReportSourceHealthReadiness(report);
  const workspaceVerificationPending =
    Boolean(input.workspaceSummaryLoading) && !input.workspaceSummary;
  const reviewVerificationPending =
    Boolean(input.reviewStatusLoading) && !input.reviewStatus;
  const verificationPending =
    workspaceVerificationPending || reviewVerificationPending;
  const gateBlockers = blockers.filter(
    (blocker) =>
      blocker.label !== "Counsel review required" &&
      blocker.label !== "Persisted legal review required",
  );
  const firstDangerBlocker = gateBlockers.find(
    (blocker) => blocker.tone === "danger",
  );
  const firstBlocker = firstDangerBlocker ?? gateBlockers[0] ?? blockers[0];
  const reviewApproved = input.reviewStatus?.status === "approved";

  if (verificationPending) {
    return {
      blocker: "Readiness verification is still loading.",
      detail:
        "The packet is visible, but reliance state is pending live workspace and review checks.",
      id: "not_reviewable",
      label: "Not reviewable",
      nextAction: "Wait for readiness verification before export or sharing.",
      owner: "Praviar verification",
      tone: "warning",
    };
  }

  if (firstDangerBlocker || exportReady === false) {
    return {
      blocker:
        firstBlocker?.detail ??
        getWorkspaceOpinionSummary(input.workspaceSummary) ??
        "One or more reliance gates are blocked.",
      detail:
        "The packet should stay in internal review until blockers are cleared.",
      id: "not_reviewable",
      label: "Not reviewable",
      nextAction: "Resolve the blocker, then rerun export readiness checks.",
      owner: "Report owner",
      tone: "danger",
    };
  }

  if (!reviewApproved) {
    const reviewDetail = input.reviewStatus
      ? `${input.reviewStatus.findings_reviewed.toLocaleString()} / ${input.reviewStatus.findings_total.toLocaleString()} findings reviewed.`
      : "Persisted legal review has not started.";

    return {
      blocker: reviewDetail,
      detail:
        "The evidence packet is assembled for QA, but it is not cleared for downstream reliance.",
      id: "ready_for_qa",
      label: "Ready for QA",
      nextAction: "Assign counsel review and close material findings.",
      owner: "Reviewer / counsel",
      tone: "warning",
    };
  }

  if (exportReady !== true) {
    return {
      blocker: "Backend export readiness has not cleared.",
      detail:
        "Counsel approval is recorded, but export-grade readiness still needs confirmation.",
      id: "counsel_approved",
      label: "Counsel-approved",
      nextAction:
        "Confirm export readiness and jurisdiction lane certification.",
      owner: "Report owner",
      tone: "warning",
    };
  }

  if (sourceHealth.hasCaveats) {
    return {
      blocker: sourceHealth.detail,
      detail:
        "Counsel approval is recorded, but source caveats must travel with any downstream packet.",
      id: "counsel_approved",
      label: "Counsel-approved",
      nextAction: "Acknowledge source caveats before export or sharing.",
      owner: "Report owner",
      tone: sourceHealth.tone,
    };
  }

  if (shareActive && shareRecipientBound) {
    return {
      blocker: "No active blocker.",
      detail:
        "The packet is counsel-approved, exportable, and protected for external sharing.",
      id: "externally_shareable",
      label: "Externally shareable",
      nextAction: "Monitor recipients, views, expiry, and revocation posture.",
      owner: "Report owner",
      tone: "success",
    };
  }

  if (shareActive && !shareRecipientBound) {
    return {
      blocker: "Active share is not confirmed as recipient-bound.",
      detail:
        "The packet is exportable, but external sharing should be strengthened before broad distribution.",
      id: "exportable",
      label: "Exportable",
      nextAction: "Reissue the share to a named, mailbox-verified recipient.",
      owner: "Report owner",
      tone: "warning",
    };
  }

  return {
    blocker: "No active blocker.",
    detail:
      "The packet is counsel-approved and ready to generate a governed export.",
    id: "exportable",
    label: "Exportable",
    nextAction: "Generate the export or create a governed share link.",
    owner: "Report owner",
    tone: "success",
  };
}

export function getReportSourceHealthReadiness(
  report?: SourceHealthReportLike,
): SourceHealthReadiness {
  const entries = report?.source_health?.entries ?? [];
  const listedSourceCount = Array.isArray(report?.search_sources_used)
    ? report.search_sources_used.length
    : 0;
  const expectedSourceCount = Math.max(entries.length, listedSourceCount);
  const unreportedSourceCount = Math.max(
    expectedSourceCount - entries.length,
    0,
  );

  if (entries.length === 0) {
    return {
      detail:
        listedSourceCount > 0
          ? "Source health not reported; verify coverage before relying on it."
          : "Source health not reported.",
      hasCaveats: true,
      okCount: 0,
      status: "Verify",
      tone: "warning",
      totalCount: expectedSourceCount,
      value:
        listedSourceCount > 0
          ? `${listedSourceCount.toLocaleString()} sources listed`
          : "Source audit pending",
    };
  }

  const statusCounts = entries.map((entry) =>
    normalizeSourceHealthStatus(entry.status),
  );
  const okCount = statusCounts.filter((status) => status === "healthy").length;
  const failedSources = statusCounts.filter(
    (status) => status === "failed",
  ).length;
  const skippedSources = statusCounts.filter(
    (status) => status === "skipped",
  ).length;
  const notConfiguredSources = entries.filter(
    (entry) => normalizeSourceHealthStatus(entry.status) === "not_configured",
  ).length;
  const unknownSourceCount = statusCounts.filter(
    (status) => status === "unknown",
  ).length;
  const hasCaveats =
    failedSources > 0 ||
    skippedSources > 0 ||
    notConfiguredSources > 0 ||
    unknownSourceCount > 0 ||
    unreportedSourceCount > 0;

  if (hasCaveats) {
    return {
      detail: formatSourceHealthGapDetail({
        failedSources,
        notConfiguredSources,
        skippedSources,
        unknownSourceCount,
        unreportedSourceCount,
      }),
      hasCaveats,
      okCount,
      status: "Caveated",
      tone: failedSources > 0 || unknownSourceCount > 0 ? "danger" : "warning",
      totalCount: expectedSourceCount,
      value: `${okCount.toLocaleString()}/${expectedSourceCount.toLocaleString()} sources`,
    };
  }

  return {
    detail: `${okCount.toLocaleString()}/${expectedSourceCount.toLocaleString()} sources completed.`,
    hasCaveats: false,
    okCount,
    status: "Included",
    tone: "success",
    totalCount: expectedSourceCount,
    value: `${okCount.toLocaleString()}/${expectedSourceCount.toLocaleString()} sources`,
  };
}

export function formatSourceHealthGapDetail({
  failedSources,
  skippedSources,
  notConfiguredSources,
  unknownSourceCount = 0,
  unreportedSourceCount = 0,
}: {
  failedSources: number;
  skippedSources: number;
  notConfiguredSources: number;
  unknownSourceCount?: number;
  unreportedSourceCount?: number;
}): string {
  const parts = [
    failedSources > 0 ? `${failedSources.toLocaleString()} failed` : null,
    skippedSources > 0 ? `${skippedSources.toLocaleString()} skipped` : null,
    notConfiguredSources > 0
      ? `${notConfiguredSources.toLocaleString()} not configured`
      : null,
    unknownSourceCount > 0
      ? `${unknownSourceCount.toLocaleString()} unknown`
      : null,
    unreportedSourceCount > 0
      ? `${unreportedSourceCount.toLocaleString()} not reported`
      : null,
  ].filter(Boolean);

  return `${parts.join(", ")}; coverage may be incomplete.`;
}
