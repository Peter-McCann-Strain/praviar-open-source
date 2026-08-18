import type { FTOReport } from "@praviar/shared-types";

import {
  getCommercialExposurePayload,
  getClearanceDecisionPayload,
  getFutureRiskList,
  getJurisdictionDecisionList,
  buildDecisionSentence,
  formatDecisionLabel,
  formatEvidenceScore,
  formatPercent,
  getDecisionBadgeVariant,
  getDecisionIconTone,
  getExtendedReport,
} from "./report-decision-formatting";
import {
  isClearanceDecision,
  isCommercialExposure,
} from "./report-decision-guards";
import type {
  ClearanceDecision,
  ClearanceDecisionAudit,
  ClearanceOutcome,
  CommercialExposure,
  DecisionEvidenceReference,
  EvidenceCoverageSummary,
  ExtendedFTOReport,
  FutureRiskFinding,
  JurisdictionDecision,
} from "./report-decision-types";

export type {
  ClearanceDecision,
  ClearanceDecisionAudit,
  ClearanceOutcome,
  CommercialExposure,
  DecisionEvidenceReference,
  EvidenceCoverageSummary,
  ExtendedFTOReport,
  FutureRiskFinding,
  JurisdictionDecision,
};

export {
  formatDecisionLabel,
  formatEvidenceScore,
  formatPercent,
  getDecisionBadgeVariant,
  getDecisionIconTone,
  getExtendedReport,
};

export function getClearanceDecision(
  report: FTOReport,
): ClearanceDecision | null {
  const decision = getClearanceDecisionPayload(report);
  if (!isClearanceDecision(decision)) {
    return null;
  }
  return decision;
}

export function getDecisionAudit(
  report: FTOReport,
): ClearanceDecisionAudit | null {
  return getClearanceDecision(report)?.decision_audit ?? null;
}

export function getJurisdictionDecisions(
  report: FTOReport,
): JurisdictionDecision[] {
  return getJurisdictionDecisionList(report);
}

export function getCommercialExposure(
  report: FTOReport,
): CommercialExposure | null {
  const exposure = getCommercialExposurePayload(report);
  if (!isCommercialExposure(exposure)) {
    return null;
  }
  return exposure;
}

export function getFutureRisk(report: FTOReport): FutureRiskFinding[] {
  return getFutureRiskList(report);
}

export function getDecisionSentence(report: FTOReport): string | null {
  const decision = getClearanceDecision(report);
  return decision ? buildDecisionSentence(decision) : null;
}

export function getDecisionCoverageRatio(report: FTOReport): number | null {
  const audit = getDecisionAudit(report);
  if (!audit || audit.queried_sources_count <= 0) {
    return null;
  }
  return audit.successful_sources_count / audit.queried_sources_count;
}

export function getDecisionWarnings(report: FTOReport): string[] {
  return getDecisionAudit(report)?.evidence_warnings ?? [];
}

export function getCoverageSummary(
  report: FTOReport,
): EvidenceCoverageSummary | null {
  return getDecisionAudit(report)?.coverage_summary ?? null;
}

export function getDecisionReferences(
  report: FTOReport,
): DecisionEvidenceReference[] {
  return getDecisionAudit(report)?.decisive_references ?? [];
}

export function getDecisionMetricItems(report: FTOReport) {
  const decision = getClearanceDecision(report);
  const audit = decision?.decision_audit;
  if (!decision || !audit) {
    return [];
  }

  return [
    {
      label: "Evidence completeness",
      value: formatEvidenceScore(decision.evidence_quality),
    },
    {
      label: "Patents Reviewed",
      value: String(audit.material_patents_reviewed),
    },
    {
      label: "Search Iterations",
      value: String(audit.search_iterations),
    },
  ];
}
