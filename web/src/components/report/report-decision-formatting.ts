import type { FTOReport } from "@praviar/shared-types";

import type {
  ClearanceDecision,
  ClearanceOutcome,
  CommercialExposure,
  ExtendedFTOReport,
  FutureRiskFinding,
  JurisdictionDecision,
} from "./report-decision-types";

export function getExtendedReport(report: FTOReport): ExtendedFTOReport {
  return report as ExtendedFTOReport;
}

export function formatDecisionLabel(outcome: ClearanceOutcome): string {
  switch (outcome) {
    case "clear":
      return "No blockers in reviewed evidence";
    case "blocked":
      return "Potential blocker";
    case "unclear":
    default:
      return "Unclear";
  }
}

export function getDecisionBadgeVariant(outcome: ClearanceOutcome) {
  switch (outcome) {
    case "clear":
      return "success" as const;
    case "blocked":
      return "destructive" as const;
    case "unclear":
    default:
      return "warning" as const;
  }
}

export function getDecisionIconTone(outcome: ClearanceOutcome): string {
  switch (outcome) {
    case "clear":
      return "text-success";
    case "blocked":
      return "text-error";
    case "unclear":
    default:
      return "text-warning";
  }
}

export function formatPercent(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "—";
  }
  const percent = value <= 1 ? value * 100 : value;
  return `${Math.round(percent)}%`;
}

export function formatEvidenceScore(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "—";
  }
  const score = value <= 1 ? value * 100 : value;
  return `${Math.round(Math.max(0, Math.min(100, score)))} / 100`;
}

export function getJurisdictionDecisionList(
  report: FTOReport,
): JurisdictionDecision[] {
  const decisions = getExtendedReport(report).jurisdiction_decisions;
  return Array.isArray(decisions) ? decisions : [];
}

export function getFutureRiskList(report: FTOReport): FutureRiskFinding[] {
  const futureRisk = getExtendedReport(report).future_risk;
  return Array.isArray(futureRisk) ? futureRisk : [];
}

export function getCommercialExposurePayload(
  report: FTOReport,
): CommercialExposure | Record<string, never> | undefined {
  return getExtendedReport(report).commercial_exposure;
}

export function getClearanceDecisionPayload(
  report: FTOReport,
): ClearanceDecision | Record<string, never> | undefined {
  return getExtendedReport(report).clearance_decision;
}

export function buildDecisionSentence(decision: ClearanceDecision): string {
  const audit = decision.decision_audit;
  const sources = `${audit.successful_sources_count}/${audit.queried_sources_count || 0} sources`;
  const patents = `${audit.material_patents_reviewed} material patent${
    audit.material_patents_reviewed === 1 ? "" : "s"
  }`;

  switch (decision.decision) {
    case "clear":
      return `Screening status: no blockers identified in ${patents} reviewed, with ${sources} succeeding. Counsel review is still required.`;
    case "blocked":
      return `Screening status: potential blocking exposure identified in ${patents}. The automated target-to-claim mapping requires counsel review before reliance.`;
    case "unclear":
    default:
      return `Screening status: unresolved, because the reviewed record remains mixed or incomplete across ${patents}.`;
  }
}
