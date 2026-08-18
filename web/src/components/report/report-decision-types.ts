import type { FTOReport } from "@praviar/shared-types";

export type ClearanceOutcome = "clear" | "unclear" | "blocked";

export interface DecisionEvidenceReference {
  category:
    | "blocking_patent"
    | "clearance_support"
    | "source_failure"
    | "coverage_gap"
    | "verification_gap"
    | "future_risk"
    | "prosecution_signal";
  summary: string;
  patent_id?: string;
  jurisdiction?: string;
  source_name?: string;
  signal?: string;
}

export interface EvidenceCoverageSummary {
  queried_source_names: string[];
  successful_source_names: string[];
  failed_source_names: string[];
  reviewed_patent_ids: string[];
  reviewed_us_patent_ids: string[];
  reviewed_ep_patent_ids: string[];
  patents_missing_claims: string[];
  patents_missing_family_context: string[];
  us_patents_missing_prosecution_context: string[];
  ep_patents_missing_register_context: string[];
  failed_analysis_patent_ids: string[];
  verification_gaps: string[];
}

export interface ClearanceDecisionAudit {
  queried_sources_count: number;
  successful_sources_count: number;
  material_patents_reviewed: number;
  material_us_patents: number;
  material_ep_patents: number;
  patents_with_claims: number;
  patents_with_family: number;
  us_patents_with_prosecution_context: number;
  ep_patents_with_register_context: number;
  analysis_failures_count: number;
  failed_sources: string[];
  evidence_sufficient_for_clearance: boolean;
  insufficiency_reasons: string[];
  evidence_warnings: string[];
  search_iterations: number;
  coverage_summary: EvidenceCoverageSummary;
  decisive_references: DecisionEvidenceReference[];
}

export interface ClearanceDecision {
  decision: ClearanceOutcome;
  decision_confidence: number;
  evidence_quality: number;
  decision_reasoning: string[];
  decision_audit: ClearanceDecisionAudit;
}

export interface JurisdictionDecision {
  jurisdiction: string;
  decision: ClearanceOutcome;
  decision_confidence: number;
  evidence_quality: number;
  reviewed_patent_ids: string[];
  blocking_patent_ids: string[];
  reasoning: string[];
}

export interface CommercialExposure {
  damages_injunction_risk: string;
  business_severity: string;
  blocking_patent_ids: string[];
  rationale: string[];
  summary: string;
}

export interface FutureRiskFinding {
  patent_id: string;
  jurisdiction: string;
  risk_type: string;
  severity: string;
  summary: string;
}

export interface ExtendedFTOReport extends FTOReport {
  clearance_decision?: ClearanceDecision | Record<string, never>;
  jurisdiction_decisions?: JurisdictionDecision[];
  commercial_exposure?: CommercialExposure | Record<string, never>;
  future_risk?: FutureRiskFinding[];
}
