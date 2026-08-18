import type { PatentAnalysis } from "@praviar/shared-types";

const JURISDICTION_CODES = new Set([
  "US",
  "EP",
  "WO",
  "JP",
  "KR",
  "CN",
  "IN",
  "CA",
  "AU",
]);

export function getPatentJurisdictionCode(patentId: string): string {
  const code = patentId.slice(0, 2).toUpperCase();
  return JURISDICTION_CODES.has(code) ? code : "";
}

export function getRiskBorderClass(
  riskLevel: PatentAnalysis["risk_level"],
): string {
  if (riskLevel === "high") return "border-error/20";
  if (riskLevel === "medium") return "border-warning/20";
  return "border-[var(--border-default)]";
}
