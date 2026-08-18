"use client";

import {
  ShieldAlert,
  AlertTriangle,
  ShieldCheck,
  CheckCircle,
} from "lucide-react";
import { RiskBadge } from "@/components/shared/risk-badge";
import { Badge } from "@/components/ui/badge";
import {
  ApprovalFlow,
  type ApprovalStatus,
} from "@/components/collaboration/approval-flow";
import { cn } from "@/lib/utils";
import type { FTOReport, RiskLevel } from "@praviar/shared-types";
import {
  formatDecisionLabel,
  formatEvidenceScore,
  getClearanceDecision,
  getDecisionBadgeVariant,
  getDecisionSentence,
} from "./report-decision-helpers";

interface VerdictBannerProps {
  report: FTOReport;
  embedded?: boolean;
  approvalStatus?: ApprovalStatus;
  approvalApprover?: string | null;
  approvalApprovedAt?: string | null;
  canApprove?: boolean;
  onApprove?: (comment?: string) => void;
  onRequestChanges?: (comment?: string) => void;
}

const RISK_BORDER_COLORS: Record<RiskLevel, string> = {
  high: "border-l-error",
  medium: "border-l-warning",
  low: "border-l-success",
  clear: "border-l-info",
};

const RISK_ICONS: Record<RiskLevel, React.ReactNode> = {
  high: <ShieldAlert className="h-5 w-5 text-error" />,
  medium: <AlertTriangle className="h-5 w-5 text-warning" />,
  low: <ShieldCheck className="h-5 w-5 text-success" />,
  clear: <CheckCircle className="h-5 w-5 text-info" />,
};

const DECISION_BORDER_COLORS = {
  clear: "border-l-success",
  unclear: "border-l-warning",
  blocked: "border-l-error",
} as const;

function getVerdictSentence(report: FTOReport): string {
  const risk = report.risk_summary.overall_risk.toLowerCase() as RiskLevel;
  const blocking = report.risk_summary.blocking_patents_count;
  const analyzed = report.risk_summary.total_patents_analyzed;
  const sourceCount = report.search_sources_used?.length ?? 0;
  const jurisdictionCount = report.jurisdiction_decisions?.length ?? 0;

  switch (risk) {
    case "high":
      return `${blocking} blocking patent${blocking !== 1 ? "s" : ""} identified. Expert review required before proceeding.`;
    case "medium":
      return `${blocking} patent${blocking !== 1 ? "s" : ""} require${blocking === 1 ? "s" : ""} attention. Design-around options may be available.`;
    case "low":
      return `Lower-risk screening result across ${analyzed} patent${analyzed !== 1 ? "s" : ""} analyzed; attorney review is still required before relying on it.`;
    case "clear":
      return jurisdictionCount > 0
        ? `No blockers identified in the reviewed record across ${analyzed} patent${analyzed !== 1 ? "s" : ""} and ${jurisdictionCount} jurisdiction${jurisdictionCount !== 1 ? "s" : ""}; this is not a legal opinion.`
        : `No blockers identified in the reviewed record across ${analyzed} patent${analyzed !== 1 ? "s" : ""} and ${sourceCount} source${sourceCount !== 1 ? "s" : ""}; this is not a legal opinion.`;
    default:
      return "Risk assessment complete.";
  }
}

export function VerdictBanner({
  report,
  embedded = false,
  approvalStatus = "pending",
  approvalApprover,
  approvalApprovedAt,
  canApprove = false,
  onApprove,
  onRequestChanges,
}: VerdictBannerProps) {
  const structuredDecision = getClearanceDecision(report);
  const risk = report.risk_summary.overall_risk.toLowerCase() as RiskLevel;
  const isHighRisk = risk === "high";
  const borderColor = structuredDecision
    ? DECISION_BORDER_COLORS[structuredDecision.decision]
    : RISK_BORDER_COLORS[risk];

  const analyzed = report.risk_summary.total_patents_analyzed;
  const blocking = report.risk_summary.blocking_patents_count;
  const sources = report.search_sources_used?.length ?? 0;
  const auditedSources =
    structuredDecision?.decision_audit.queried_sources_count ?? sources;
  const materialPatents =
    structuredDecision?.decision_audit.material_patents_reviewed ?? analyzed;
  const bannerSentence =
    getDecisionSentence(report) ?? getVerdictSentence(report);

  return (
    <div
      role={
        structuredDecision?.decision === "blocked" || isHighRisk
          ? "alert"
          : "status"
      }
      aria-live="polite"
      className={cn(
        "w-full border-l-4",
        borderColor,
        embedded
          ? "bg-[var(--surface-muted)]/45 px-4 py-4 sm:px-5"
          : "rounded-lg border border-[var(--border-default)] bg-[var(--surface-glass)] p-4 shadow-[var(--shadow-sm)] backdrop-blur-xl",
      )}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        {/* Left: Risk badge + icon */}
        <div className="flex items-center gap-3">
          {structuredDecision ? (
            <div className="flex items-center gap-2">
              {structuredDecision.decision === "clear" ? (
                <CheckCircle className="h-5 w-5 text-success" />
              ) : structuredDecision.decision === "blocked" ? (
                <ShieldAlert className="h-5 w-5 text-error" />
              ) : (
                <AlertTriangle className="h-5 w-5 text-warning" />
              )}
              <Badge
                variant={getDecisionBadgeVariant(structuredDecision.decision)}
              >
                {formatDecisionLabel(structuredDecision.decision)}
              </Badge>
              <RiskBadge risk={risk} size="lg" animated />
            </div>
          ) : (
            <div className="flex items-center gap-2">
              {RISK_ICONS[risk]}
              <RiskBadge risk={risk} size="lg" animated />
            </div>
          )}
        </div>

        {/* Center: Verdict sentence */}
        <p className="flex-1 text-sm font-medium text-[var(--text-primary)] sm:text-center">
          {bannerSentence}
        </p>

        {/* Right: Metric pills */}
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{materialPatents} Reviewed</Badge>
          <Badge variant={blocking > 0 ? "destructive" : "secondary"}>
            {blocking} Blocking
          </Badge>
          <Badge variant="secondary">{auditedSources} Sources</Badge>
          {structuredDecision ? (
            <Badge variant="secondary">
              {formatEvidenceScore(structuredDecision.evidence_quality)}{" "}
              Evidence-completeness score
            </Badge>
          ) : null}
        </div>
      </div>
      <div className="border-t border-[var(--border-subtle)] pt-3 mt-3">
        <ApprovalFlow
          status={approvalStatus}
          approver={approvalApprover ?? undefined}
          approvedAt={approvalApprovedAt ?? undefined}
          canApprove={canApprove}
          onApprove={onApprove}
          onRequestChanges={onRequestChanges}
        />
      </div>
    </div>
  );
}
