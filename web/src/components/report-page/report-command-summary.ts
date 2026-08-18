import type { FTOReport, RiskLevel } from "@praviar/shared-types";

export function getReportReference(
  report: Pick<FTOReport, "report_id">,
): string {
  const reportId = report.report_id.trim();
  if (!reportId) {
    throw new Error("Report identifier is unavailable");
  }
  return reportId;
}

export function formatReportRiskLabel(value: string): string {
  const risk = value.toLowerCase() as RiskLevel;

  if (risk === "medium") return "Moderate Risk";
  if (risk === "high") return "High Risk";
  if (risk === "low") return "Low Risk";
  if (risk === "clear") return "No Blockers";

  return "Risk Recorded";
}

export function getReportRiskToneClass(value: string): string {
  const risk = value.toLowerCase() as RiskLevel;

  if (risk === "high") return "border-error/25 bg-error/10 text-error";
  if (risk === "medium") return "border-warning/25 bg-warning/10 text-warning";
  if (risk === "low") return "border-success/25 bg-success/10 text-success";
  if (risk === "clear") return "border-info/25 bg-info/10 text-info";

  return "border-[var(--border-subtle)] bg-[var(--surface-muted)] text-[var(--text-tertiary)]";
}
