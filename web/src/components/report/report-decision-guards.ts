import type {
  ClearanceDecision,
  CommercialExposure,
} from "./report-decision-types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((entry) => typeof entry === "string")
  );
}

export function isClearanceDecision(
  value: unknown,
): value is ClearanceDecision {
  return (
    isRecord(value) &&
    typeof value.decision === "string" &&
    typeof value.decision_confidence === "number" &&
    typeof value.evidence_quality === "number" &&
    isStringArray(value.decision_reasoning) &&
    isRecord(value.decision_audit)
  );
}

export function isCommercialExposure(
  value: unknown,
): value is CommercialExposure {
  return (
    isRecord(value) &&
    typeof value.damages_injunction_risk === "string" &&
    typeof value.business_severity === "string" &&
    isStringArray(value.blocking_patent_ids) &&
    isStringArray(value.rationale) &&
    typeof value.summary === "string"
  );
}
